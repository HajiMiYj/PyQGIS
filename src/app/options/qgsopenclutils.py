"""OpenCL device discovery for the Acceleration page.

QgsOpenClUtils is not exported to PyQGIS, but the running build *does* link
OpenCL (qgis_core.dll imports OpenCL.dll) and the driver exposes the hardware,
so the class is reproduced here over the OpenCL C API. The stored settings and
the device identifier format match native exactly, so QGIS core - which has the
real QgsOpenClUtils - reads the same selection back:

  core/OpenClEnabled        (QgsOpenClUtils::SETTINGS_GLOBAL_ENABLED_KEY)
  core/OpenClDefaultDevice  (QgsOpenClUtils::SETTINGS_DEFAULT_DEVICE_KEY)
  device id = "<Name>|<Vendor>|<Version>|<Type>"   (Type: CPU|GPU|Other)
"""
import ctypes
from qgis.core import QgsSettings

ENABLED_KEY = 'core/OpenClEnabled'
DEVICE_KEY = 'core/OpenClDefaultDevice'

# OpenCL constants (CL/cl.h).
CL_SUCCESS = 0
CL_DEVICE_TYPE_CPU = 1 << 1
CL_DEVICE_TYPE_GPU = 1 << 2
CL_DEVICE_TYPE_ACCELERATOR = 1 << 3
CL_DEVICE_TYPE_ALL = 0xFFFFFFFF
CL_DEVICE_NAME = 0x102B
CL_DEVICE_VENDOR = 0x102C
CL_DEVICE_PROFILE = 0x102E
CL_DEVICE_VERSION = 0x102F
CL_DEVICE_TYPE = 0x1000
CL_DEVICE_IMAGE_SUPPORT = 0x1016
CL_DEVICE_IMAGE2D_MAX_WIDTH = 0x1011
CL_DEVICE_IMAGE2D_MAX_HEIGHT = 0x1012
CL_DEVICE_MAX_MEM_ALLOC_SIZE = 0x1010

# QgsOpenClUtils::Info
Name, Vendor, Version, Profile, ImageSupport = 'name', 'vendor', 'version', 'profile', 'imageSupport'
Image2dMaxWidth, Image2dMaxHeight, MaxMemAllocSize, Type = 'image2dMaxWidth', 'image2dMaxHeight', 'maxMemAllocSize', 'type'

_INTS = (CL_DEVICE_TYPE, CL_DEVICE_IMAGE_SUPPORT, CL_DEVICE_IMAGE2D_MAX_WIDTH,
         CL_DEVICE_IMAGE2D_MAX_HEIGHT, CL_DEVICE_MAX_MEM_ALLOC_SIZE)
_STRINGS = (CL_DEVICE_NAME, CL_DEVICE_VENDOR, CL_DEVICE_PROFILE, CL_DEVICE_VERSION)
_LIBRARY = None


def _library():
    """Load OpenCL once; None when the platform has no usable OpenCL driver."""
    global _LIBRARY
    if _LIBRARY is not None:
        return _LIBRARY or None

    import sys

    # 按平台选择加载方式和库名
    if sys.platform == 'win32':
        candidates = ['OpenCL', 'OpenCL.dll']
        loader = ctypes.WinDLL
    elif sys.platform == 'darwin':
        candidates = ['libOpenCL.dylib', 'OpenCL', '/System/Library/Frameworks/OpenCL.framework/OpenCL']
        loader = ctypes.CDLL
    else:  # linux / freebsd 等
        candidates = ['libOpenCL.so.1', 'libOpenCL.so', 'OpenCL']
        loader = ctypes.CDLL

    library = None
    for name in candidates:
        try:
            library = loader(name)
            break
        except (OSError, AttributeError):
            continue

    if library is None:
        _LIBRARY = False
        return None

    library.clGetPlatformIDs.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                         ctypes.POINTER(ctypes.c_uint)]
    library.clGetDeviceIDs.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    library.clGetDeviceInfo.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
    library.clGetPlatformInfo.argtypes = library.clGetDeviceInfo.argtypes
    _LIBRARY = library
    return library


_CACHE = {}


def devices():
    """Every OpenCL device across all platforms, in driver order."""
    if 'devices' in _CACHE: return _CACHE['devices']
    result = []
    library = _library()
    if library is not None:
        platforms = (ctypes.c_void_p * 16)()
        count = ctypes.c_uint()
        if library.clGetPlatformIDs(16, platforms, ctypes.byref(count)) == CL_SUCCESS:
            for index in range(count.value):
                handles = (ctypes.c_void_p * 32)()
                found = ctypes.c_uint()
                if library.clGetDeviceIDs(platforms[index], CL_DEVICE_TYPE_ALL, 32, handles,
                                          ctypes.byref(found)) != CL_SUCCESS:
                    continue
                result.extend(handles[i] for i in range(found.value))
    _CACHE['devices'] = result
    return result


def available():
    """QgsOpenClUtils::available()."""
    return bool(devices())


def enabled():
    return QgsSettings().value(ENABLED_KEY, False, type=bool)


def setEnabled(value):
    QgsSettings().setValue(ENABLED_KEY, bool(value))


def preferredDevice():
    return QgsSettings().value(DEVICE_KEY, '', type=str)


def storePreferredDevice(deviceId):
    QgsSettings().setValue(DEVICE_KEY, deviceId)


def activeDevice():
    """QgsOpenClUtils::activeDevice() - cl::Device::getDefault(), the first device."""
    allDevices = devices()
    return allDevices[0] if allDevices else None


def _info(device, parameter):
    library = _library()
    if library is None or device is None: return None
    size = ctypes.c_size_t()
    if library.clGetDeviceInfo(device, parameter, 0, None, ctypes.byref(size)) != CL_SUCCESS:
        return None
    buffer = ctypes.create_string_buffer(max(1, size.value))
    if library.clGetDeviceInfo(device, parameter, size.value, buffer, None) != CL_SUCCESS:
        return None
    return buffer.raw


def deviceInfo(infoType, device):
    """QgsOpenClUtils::deviceInfo(): the same strings native puts on screen."""
    if infoType in (Name, Vendor, Version, Profile):
        parameter = {Name: CL_DEVICE_NAME, Vendor: CL_DEVICE_VENDOR,
                     Version: CL_DEVICE_VERSION, Profile: CL_DEVICE_PROFILE}[infoType]
        raw = _info(device, parameter)
        return raw.split(b'\x00')[0].decode('utf-8', 'replace') if raw else ''
    if infoType == ImageSupport:
        value = _number(device, CL_DEVICE_IMAGE_SUPPORT)
        return 'True' if value else 'False'
    if infoType == Image2dMaxWidth: return str(_number(device, CL_DEVICE_IMAGE2D_MAX_WIDTH))
    if infoType == Image2dMaxHeight: return str(_number(device, CL_DEVICE_IMAGE2D_MAX_HEIGHT))
    if infoType == MaxMemAllocSize: return str(_number(device, CL_DEVICE_MAX_MEM_ALLOC_SIZE))
    if infoType == Type:
        value = _number(device, CL_DEVICE_TYPE)
        if value & CL_DEVICE_TYPE_GPU: return 'GPU'
        if value & CL_DEVICE_TYPE_CPU: return 'CPU'
        return 'Other'
    return ''


def _number(device, parameter):
    raw = _info(device, parameter)
    if not raw: return 0
    if parameter in _INTS and len(raw) >= 8:
        return int.from_bytes(raw[:8], 'little')
    return int.from_bytes(raw[:4].ljust(4, b'\x00'), 'little')


def deviceId(device):
    """QgsOpenClUtils::deviceId(): name|vendor|version|type."""
    return '|'.join(deviceInfo(part, device) for part in (Name, Vendor, Version, Type))


def deviceByIdentifier(identifier):
    for device in devices():
        if deviceId(device) == identifier: return device
    return None


def deviceDescription(identifier):
    """QgsOpenClUtils::deviceDescription(): the device detail HTML."""
    device = deviceByIdentifier(identifier) if isinstance(identifier, str) else identifier
    if device is None: return ''
    return ('类型：<b>{type}</b><br>名称：<b>{name}</b><br>厂商：<b>{vendor}</b><br>'
            '配置：<b>{profile}</b><br>版本：<b>{version}</b><br>图像支持：<b>{image}</b><br>'
            '最大 image2d 宽：<b>{width}</b><br>最大 image2d 高：<b>{height}</b><br>'
            '最大内存分配：<b>{memory}</b><br>').format(
        type=deviceInfo(Type, device), name=deviceInfo(Name, device),
        vendor=deviceInfo(Vendor, device), profile=deviceInfo(Profile, device),
        version=deviceInfo(Version, device), image=deviceInfo(ImageSupport, device),
        width=deviceInfo(Image2dMaxWidth, device), height=deviceInfo(Image2dMaxHeight, device),
        memory=deviceInfo(MaxMemAllocSize, device))
