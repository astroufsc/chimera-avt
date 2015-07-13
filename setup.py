from distutils.core import setup

setup(
    name='chimera-avt',
    version='0.0.1',
    packages=['chimera-avt', 'chimera-avt.instruments'],
    scripts=[],
    url='http://github.com/astroufsc/chimera-avt',
    license='GPL v2',
    author='Tiago Ribeiro',
    author_email='tribeiro@ufs.br',
    description='Chimera driver for AVT camera',
    install_requires=['pymba']
)
