"""Raster display coordinates and pixel coordinates, including rotated rasters."""
from osgeo import gdal
from qgis.core import QgsPointXY


class QgsRasterChangeCoords:
    def __init__(self):
        self.mGeoTransform = (0, 1, 0, 0, 0, -1)
        self.mInverse = self.mGeoTransform

    def loadRaster(self, path):
        source = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
        if source is None: raise ValueError(gdal.GetLastErrorMsg() or '无法读取栅格')
        transform = source.GetGeoTransform(can_return_null=True)
        self.mHasExistingGeoreference = transform is not None
        self.mGeoTransform = transform or (0, 1, 0, 0, 0, -1)
        self.mInverse = gdal.InvGeoTransform(self.mGeoTransform)
        source = None
        if self.mInverse is None: raise ValueError('源栅格的坐标变换不可逆')

    def toColumnLine(self, point):
        col, line = gdal.ApplyGeoTransform(self.mInverse, point.x(), point.y())
        return QgsPointXY(col, -line)  # QGIS georeferencer uses an upward source Y axis.

    def toXY(self, point):
        return QgsPointXY(*gdal.ApplyGeoTransform(self.mGeoTransform, point.x(), -point.y()))
