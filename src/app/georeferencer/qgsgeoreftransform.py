"""Fit and evaluate using the native analysis GCP transformers."""
import math
from qgis.core import QgsPointXY, QgsCoordinateTransform
from qgis.analysis import QgsGcpTransformerInterface


class QgsGeorefTransform:
    Method = QgsGcpTransformerInterface.TransformMethod

    def __init__(self):
        self.mTransformer = None
        self.mError = ''

    def updateParametersFromGcps(self, points, method, crs, context, rasterChangeCoords=None):
        self.mTransformer = None
        self.mError = ''
        transformer = QgsGcpTransformerInterface.create(method)
        enabled = [p for p in points if p.isEnabled()]
        if len(enabled) < transformer.minimumGcpCount():
            self.mError = f'此变换至少需要 {transformer.minimumGcpCount()} 个启用的控制点'
            return False
        source, destination = [], []
        try:
            for point in enabled:
                source.append(rasterChangeCoords.toColumnLine(point.sourcePoint()) if rasterChangeCoords else point.sourcePoint())
                target = point.destinationPoint()
                if point.destinationPointCrs().isValid() and point.destinationPointCrs() != crs:
                    target = QgsCoordinateTransform(point.destinationPointCrs(), crs, context).transform(target)
                destination.append(target)
            if not transformer.updateParametersFromGcps(source, destination, False):
                raise ValueError('控制点布局退化或不足以拟合所选变换')
            self.mTransformer = transformer
            return True
        except Exception as error:
            self.mError = str(error)
            return False

    def transform(self, point, inverse=False):
        if self.mTransformer is None: raise ValueError(self.mError or '变换尚未初始化')
        ok, x, y = self.mTransformer.transform(point.x(), point.y(), inverse)
        if not ok or not math.isfinite(x) or not math.isfinite(y): raise ValueError('坐标变换失败')
        return QgsPointXY(x, y)

    def providesAccurateInverseTransformation(self):
        """Native QgsGeorefTransform::providesAccurateInverseTransformation()."""
        if self.mTransformer is None: return False
        method = self.Method
        return self.mTransformer.method() in (method.Linear, method.Helmert, method.PolynomialOrder1)

    def geoTransform(self):
        origin = self.transform(QgsPointXY(0, 0))
        x = self.transform(QgsPointXY(1, 0))
        y = self.transform(QgsPointXY(0, -1))
        return (origin.x(), x.x()-origin.x(), y.x()-origin.x(), origin.y(), x.y()-origin.y(), y.y()-origin.y())

    def getOriginScaleRotation(self):
        """Native getOriginScaleRotation(): origin, scales and radians for Linear/Helmert.

        Only the two world-file capable methods report parameters, matching
        QgsLinearGeorefTransform::getOriginScale() and
        QgsHelmertGeorefTransform::getOriginScaleRotation().
        """
        method = self.Method
        if self.mTransformer is None or self.mTransformer.method() not in (method.Linear, method.Helmert):
            return False, QgsPointXY(), 0.0, 0.0, 0.0
        origin = self.transform(QgsPointXY(0, 0))
        xAxis = self.transform(QgsPointXY(1, 0))
        yAxis = self.transform(QgsPointXY(0, -1))
        scaleX = math.hypot(xAxis.x()-origin.x(), xAxis.y()-origin.y())
        scaleY = math.hypot(yAxis.x()-origin.x(), yAxis.y()-origin.y())
        if self.mTransformer.method() == method.Linear:
            return True, origin, scaleX, scaleY, 0.0
        # Helmert is a single uniform scale plus a rotation; native reports the
        # angle of the transformed x axis in radians.
        rotation = math.atan2(xAxis.y()-origin.y(), xAxis.x()-origin.x())
        return True, origin, scaleX, scaleX, rotation
