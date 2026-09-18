"""Load native QGIS C++ core plugins whose logic is not available from PyQGIS.

QgsPluginRegistry is not exposed to Python and QgisPlugin is marked SIP_NO_FILE,
so neither loadCppPlugin() nor a typed pointer exists here. The plugin ABI is
still reachable: the DLL exports classFactory( QgisInterface * ), and QgisPlugin
declares exactly three virtuals, so the returned object's vtable gives initGui()
at slot 1 and unload() at slot 2 (qgisplugin.h: ~QgisPlugin, initGui, unload).
The ported QgisAppInterface is a real QgisInterface, so classFactory accepts it.
"""
import ctypes
from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt import sip

# Slot 1 of QgisPlugin's vtable, per src/plugins/qgisplugin.h declaration order.
INIT_GUI_SLOT = 1
UNLOAD_SLOT = 2


class NativePlugin:
    """One loaded native plugin, keeping its library alive for its lifetime."""

    def __init__(self, name, library, pointer):
        self.name = name
        self.mLibrary = library
        self.mPointer = pointer

    def initGui(self):
        return self._invoke(INIT_GUI_SLOT)

    def unload(self):
        if self.mPointer is None:
            return
        try:
            self._invoke(UNLOAD_SLOT)
        finally:
            self.mPointer = None

    def _invoke(self, slot):
        vtable = ctypes.cast(ctypes.c_void_p(self.mPointer), ctypes.POINTER(ctypes.c_void_p))[0]
        function = ctypes.cast(vtable, ctypes.POINTER(ctypes.c_void_p))[slot]
        if not function:
            raise RuntimeError(f'{self.name}: vtable slot {slot} is empty')
        ctypes.CFUNCTYPE(None, ctypes.c_void_p)(function)(ctypes.c_void_p(self.mPointer))


def pluginLibraryPath(name):
    """Absolute path of the native plugin binary for the running build."""
    return str(Path(QgsApplication.pluginPath()) / f'plugin_{name}.dll')


def loadNativePlugin(name, iface, messageLog=None):
    """Create the plugin instance through its exported classFactory."""
    path = pluginLibraryPath(name)
    if not Path(path).is_file():
        return None
    library = ctypes.CDLL(path)
    factory = library.classFactory
    factory.restype = ctypes.c_void_p
    factory.argtypes = [ctypes.c_void_p]
    interface = sip.unwrapinstance(iface)
    pointer = factory(ctypes.c_void_p(interface))
    if not pointer:
        if messageLog:
            messageLog(f'{name}: classFactory 未返回插件实例')
        return None
    return NativePlugin(name, library, pointer)
