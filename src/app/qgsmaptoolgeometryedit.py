"""Interactive geometry editing tools built on the QGIS 3.34 geometry API."""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor, QTransform
from qgis.core import (
    Qgis, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY,
    QgsVectorDataProvider, QgsVectorLayer, QgsWkbTypes,
)
from qgis.gui import QgsMapToolAdvancedDigitizing, QgsRubberBand


class QgsMapToolGeometryEdit(QgsMapToolAdvancedDigitizing):
    DRAW_MODES = {'reshape', 'split', 'splitParts', 'addRing', 'addPart'}

    def __init__(self, canvas, cadDock, mode):
        super().__init__(canvas, cadDock)
        self.mMode = mode
        self.mPoints = []
        self.mRubberBand = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.mRubberBand.setColor(QColor(255, 90, 40, 190))
        self.mRubberBand.setWidth(2)
        self.mRubberBand.hide()

    def layer(self):
        layer = self.canvas().currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable():
            return None
        capabilities = layer.dataProvider().capabilities()
        if not capabilities & QgsVectorDataProvider.ChangeGeometries:
            return None
        return layer

    def featureAt(self, layer, point):
        tolerance = self.canvas().mapUnitsPerPixel() * 12
        rect = self.canvas().mapSettings().mapToLayerCoordinates(
            layer, self.canvas().mapSettings().visibleExtent())
        rect.setXMinimum(point.x() - tolerance)
        rect.setXMaximum(point.x() + tolerance)
        rect.setYMinimum(point.y() - tolerance)
        rect.setYMaximum(point.y() + tolerance)
        local = self.toLayerCoordinates(layer, point)
        best = None
        bestDistance = tolerance
        for feature in layer.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
            geometry = feature.geometry()
            if geometry.isNull() or geometry.isEmpty():
                continue
            distance = geometry.distance(QgsGeometry.fromPointXY(local))
            if distance <= bestDistance:
                best, bestDistance = feature, distance
        if best is not None:
            return best
        selected = list(layer.getSelectedFeatures())
        return selected[0] if len(selected) == 1 else None

    def selectedOrPicked(self, layer, point):
        selected = list(layer.getSelectedFeatures())
        if selected:
            return selected
        feature = self.featureAt(layer, point)
        return [feature] if feature else []

    def cadCanvasPressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancel()
            return
        if event.button() != Qt.LeftButton or self.mMode not in self.DRAW_MODES:
            return
        self.mPoints.append(QgsPointXY(event.snapPoint()))
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        for point in self.mPoints:
            self.mRubberBand.addPoint(point, False)
        self.mRubberBand.show()

    def cadCanvasMoveEvent(self, event):
        if not self.mPoints:
            return
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        for point in self.mPoints:
            self.mRubberBand.addPoint(point, False)
        self.mRubberBand.addPoint(event.snapPoint(), True)
        self.mRubberBand.show()

    def cadCanvasReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.cancel()

    def canvasDoubleClickEvent(self, event):
        if self.mMode in self.DRAW_MODES:
            point = QgsPointXY(event.snapPoint())
            if not self.mPoints or self.mPoints[-1] != point:
                self.mPoints.append(point)
            self.finishDrawing()

    def finishDrawing(self):
        layer = self.layer()
        points = self.mPoints[:]
        self.cancel()
        if layer is None or len(points) < 2:
            return False
        localPoints = [self.toLayerCoordinates(layer, point) for point in points]
        if self.mMode == 'addRing' and localPoints[0] != localPoints[-1]:
            localPoints.append(localPoints[0])
        if self.mMode in ('reshape', 'split'):
            return self.applyLineOperation(layer, localPoints)
        return self.applyPartOperation(layer, localPoints)

    def applyLineOperation(self, layer, points):
        features = self.selectedOrPicked(layer, self.toMapCoordinates(layer, points[0]))
        if not features:
            return False
        success = False
        for feature in features:
            geometry = QgsGeometry(feature.geometry())
            if self.mMode == 'reshape':
                result = geometry.reshapeGeometry(points)
                success = result == Qgis.GeometryOperationResult.Success
                if success:
                    layer.beginEditCommand(QCoreApplication.translate('MainWindow', 'Reshape Features'))
                    success = layer.changeGeometry(feature.id(), geometry)
            else:
                result, newGeometries, _ = geometry.splitGeometry(
                    points, False, self.mMode != 'splitParts')
                success = result == Qgis.GeometryOperationResult.Success and bool(newGeometries)
                if success:
                    layer.beginEditCommand(QCoreApplication.translate('MainWindow', 'Split Parts') if self.mMode == 'splitParts' else QCoreApplication.translate('MainWindow', 'Split Features'))
                    success = layer.changeGeometry(feature.id(), geometry)
                    copies = []
                    for newGeometry in newGeometries:
                        copy = QgsFeature(feature)
                        copy.setGeometry(newGeometry)
                        copies.append(copy)
                    success = success and layer.addFeatures(copies)
            if success:
                layer.endEditCommand()
            else:
                layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def applyPartOperation(self, layer, points):
        features = self.selectedOrPicked(layer, self.toMapCoordinates(layer, points[0]))
        if not features:
            return False
        feature = features[0]
        geometry = QgsGeometry(feature.geometry())
        if self.mMode == 'addRing':
            result = geometry.addRing(points)
            command = '添加环'
        else:
            if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                part = QgsGeometry.fromPolygonXY([points])
                result = geometry.addPartGeometry(part)
            else:
                part = QgsGeometry.fromPolylineXY(points)
                result = geometry.addPart(part.constGet(), layer.geometryType())
            command = '添加部件'
        if result != Qgis.GeometryOperationResult.Success:
            return False
        layer.beginEditCommand(command)
        success = layer.changeGeometry(feature.id(), geometry)
        if success:
            layer.endEditCommand()
        else:
            layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def applyToSelected(self, callback, command):
        layer = self.layer()
        if layer is None:
            return False
        features = list(layer.getSelectedFeatures())
        if not features:
            return False
        layer.beginEditCommand(command)
        success = True
        for feature in features:
            geometry = QgsGeometry(feature.geometry())
            try:
                result = callback(geometry)
            except Exception:
                layer.destroyEditCommand()
                raise
            if isinstance(result, QgsGeometry):
                geometry = result
            elif not result:
                success = False
                break
            success = layer.changeGeometry(feature.id(), geometry)
            if not success:
                break
        if success:
            layer.endEditCommand()
        else:
            layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def reverseLine(self):
        def reverse(geometry):
            if geometry.type() != QgsWkbTypes.LineGeometry: return False
            replacement = QgsGeometry.collectGeometry([QgsGeometry(part.constGet().reversed()) for part in geometry.asGeometryCollection()]) if geometry.isMultipart() else QgsGeometry(geometry.constGet().reversed())
            return self.replaceGeometry(geometry, replacement)
        return self.applyToSelected(reverse, QCoreApplication.translate('MainWindow', 'Reverse line'))

    def simplifyFeature(self, tolerance):
        return self.applyToSelected(lambda geometry: self.replaceGeometry(geometry, geometry.simplify(tolerance)), QCoreApplication.translate('MainWindow', 'Simplify Feature'))

    @staticmethod
    def replaceGeometry(target, replacement):
        if replacement.isNull() or replacement.isEmpty():
            return False
        return replacement

    def offsetCurve(self, distance):
        def offset(geometry):
            replacement = geometry.offsetCurve(distance, 8, Qgis.JoinStyle.Round, 2.0)
            return self.replaceGeometry(geometry, replacement)
        return self.applyToSelected(offset, QCoreApplication.translate('MainWindow', 'Offset Curve'))

    def rotateFeature(self, angle):
        def rotate(geometry):
            center = geometry.centroid().asPoint()
            return geometry.rotate(angle, QgsPointXY(center)) == Qgis.GeometryOperationResult.Success
        return self.applyToSelected(rotate, QCoreApplication.translate('QgsMapToolRotateFeature', 'Rotate feature'))

    def scaleFeature(self, factor):
        def scale(geometry):
            center = geometry.centroid().asPoint()
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.scale(factor, factor)
            transform.translate(-center.x(), -center.y())
            return geometry.transform(transform) == Qgis.GeometryOperationResult.Success
        return self.applyToSelected(scale, QCoreApplication.translate('QgsMapToolScaleFeature', 'Scale feature'))

    def deletePart(self):
        def delete_last_part(geometry):
            parts = list(geometry.constParts())
            return len(parts) > 1 and geometry.deletePart(len(parts) - 1)
        return self.applyToSelected(delete_last_part, QCoreApplication.translate('MainWindow', 'Delete Part'))

    def deleteRing(self):
        return self.applyToSelected(lambda geometry: geometry.deleteRing(1), QCoreApplication.translate('MainWindow', 'Delete Ring'))

    def mergeFeatures(self):
        layer = self.layer()
        features = list(layer.getSelectedFeatures()) if layer else []
        if layer is None or len(features) < 2:
            return False
        merged = QgsGeometry(features[0].geometry())
        for feature in features[1:]:
            merged = merged.combine(feature.geometry())
        layer.beginEditCommand(QCoreApplication.translate('QgisApp', 'Merge Features'))
        success = layer.changeGeometry(features[0].id(), merged)
        if success:
            success = all(layer.deleteFeature(feature.id()) for feature in features[1:])
        if success:
            layer.endEditCommand()
        else:
            layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def cancel(self):
        self.mPoints = []
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        self.mRubberBand.hide()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel()
        else:
            super().keyReleaseEvent(event)

    def deactivate(self):
        self.cancel()
        super().deactivate()
