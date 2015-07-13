# This is an example of an simple instrument.

from chimera.instruments.camera import CameraBase



class AVT(CameraBase):
    __config__ = {"param1": "a string parameter"}

    def __init__(self):
        CameraBase.__init__(self)

