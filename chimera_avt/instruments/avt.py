# This is an example of an simple instrument.

from __future__ import division

import time
import datetime as dt
import numpy as np

from chimera.interfaces.camera import (CCD, CameraFeature,
                                       ReadoutMode,
                                       CameraStatus)

from chimera.instruments.camera import CameraBase

from chimera.core.lock import lock

import pymba

class NoAVTCameraFound(Exception):
    pass

class AVT(CameraBase):
    __config__ = {"cameraId": 'None',
                  "PixelFormat": "Mono8",
                  "GVSPDriver" : "Socket",
                  "vimba_version" : "0.0.0"}

    def __init__(self):
        CameraBase.__init__(self)

        self.lastTemp = 0

        self.lastFrameStartTime = 0
        self.lastFrameTemp = None
        self.lastFrameFilename = ""

        self._supports = {CameraFeature.TEMPERATURE_CONTROL: False,
                          CameraFeature.PROGRAMMABLE_GAIN: True,
                          CameraFeature.PROGRAMMABLE_OVERSCAN: False,
                          CameraFeature.PROGRAMMABLE_FAN: False,
                          CameraFeature.PROGRAMMABLE_LEDS: False,
                          CameraFeature.PROGRAMMABLE_BIAS_LEVEL: False}

        self.ccd = 0

        self._ccds = {0 : CCD.TRACKING}

        self._adcs = {"12 bits": 0}

        self._binnings = {"1x1" : 0}

        self._binning_factors = {"1x1" : 1}

    def __start__(self):

        self.open()

        self["camera_model"] = self.camera0.DeviceModelName
        self["device"] = "Ethernet"
        self["ccd_model"] = self.camera0.SensorType
        # self["CCD"] = CCD.TRACKING
        self.camera0.DeviceTemperatureSelector = "Sensor"

        readoutMode = ReadoutMode()
        readoutMode.mode = 0
        readoutMode.gain = 1.0
        readoutMode.width = self.camera0.WidthMax
        readoutMode.height = self.camera0.HeightMax
        readoutMode.pixelWidth = 5.5
        readoutMode.pixelHeight = 5.5


        self.readOutModes = {self.ccd : {0 : readoutMode}}

    def __stop__(self):

        try:
            self.close()
        except:
            pass

    def open(self):

        self.vimba = pymba.Vimba()

        self.vimba.startup()

        self["vimba_version"] = self.vimba.getVersion()

        # get system object

        self.system = self.vimba.getSystem()

        # Enable discovery for GigE cameras and get list of available cameras
        if self.system.GeVTLIsPresent:
            self.system.runFeatureCommand("GeVDiscoveryAllOnce")
            time.sleep(0.2)

        cameraIds = self.vimba.getCameraIds()

        self.camera0 = None

        if self["cameraId"] != 'None' and self["cameraId"] in cameraIds:
            self.camera0 = self.vimba.getCamera(self["cameraId"])
        elif len(cameraIds) > 0:
            self.camera0 = self.vimba.getCamera(cameraIds[0])
            self["cameraId"] = cameraIds[0]
        else:
            raise NoAVTCameraFound("No AVT camera found on this network.")

        self.camera0.openCamera()
        # Setup camera

        self.camera0.AcquisitionMode = "SingleFrame"
        self.camera0.GainAuto = "Off"
        self.camera0.ExposureAuto = "Off"
        self.camera0.PixelFormat = self["PixelFormat"]
        self.camera0.GVSPDriver = self["GVSPDriver"]

        return True

    def close(self):
        self.camera0.endCapture()
        self.camera0.revokeAllFrames()
        self.vimba.shutdown()

    def isCooling(self):
        return False

    def isFanning(self):
        return False

    @lock
    def getTemperature(self):
        return self.camera0.DeviceTemperature

    def getCCDs(self):
        return self._ccds

    def getCurrentCCD(self):
        return self.ccd

    def getBinnings(self):
        return self._binnings

    def getADCs(self):
        return self._adcs

    def getPhysicalSize(self):
        return -1,-1

    def getPixelSize(self):
        return -1,-1

    def getOverscanSize(self, ccd=None):
        return (0,0)

    def getReadoutModes(self):
        return self.readOutModes

    def supports(self, feature=None):
        return self._supports[feature]

    def _expose(self,imageRequest):

        # setup exposure time
        self.camera0.ExposureTimeAbs = imageRequest["exptime"] * 1e6 # In microseconds!

        # create a new frame
        self.frame0 = self.camera0.getFrame()

        # announce frame
        self.frame0.announceFrame()

        self.exposeBegin(imageRequest)

        self.camera0.startCapture()
        start = time.time()
        self.frame0.queueFrameCapture()
        self.camera0.runFeatureCommand("AcquisitionStart")

        # save time exposure started
        self.lastFrameStartTime = dt.datetime.utcnow()
        self.lastFrameTemp = self.getTemperature()

        status = CameraStatus.OK
        self.abort.clear()

        while time.time() < start + imageRequest["exptime"]:
            if self.abort.isSet():
                status = self._abortExposure()
                break
            time.sleep(0.01)

        self.camera0.runFeatureCommand("AcquisitionStop")

        return self.exposeComplete(imageRequest,status)

    def _abortExposure(self):

        self.frame0.revokeFrame()
        self.camera0.runFeatureCommand("AcquisitionStop")
        self.camera0.endCapture()

        return CameraStatus.ABORTED

    def _readout(self,imageRequest):

        (mode, binning, top, left,
         width, height) = self._getReadoutModeInfo(imageRequest["binning"],
                                                   imageRequest["window"])

        self.frame0.waitFrameCapture()

        self.readoutBegin(imageRequest)

        img = np.ndarray(buffer = self.frame0.getBufferByteData(),
                         dtype=np.uint8,
                         shape = (self.frame0.height,
                                  self.frame0.width,
                                  1))[:,:,0]

        proxy = self._saveImage(imageRequest,img,
            {"frame_temperature" : self.lastFrameTemp,
             "frame_start_time" : self.lastFrameStartTime,
             "binning_factor": self._binning_factors[binning]})

        return self._endReadout(proxy,CameraStatus.OK)

    def _endReadout(self,proxy,status):
        # Clean up after capture

        self.camera0.endCapture()
        self.camera0.revokeAllFrames()

        self.readoutComplete(proxy,status)

        return proxy

