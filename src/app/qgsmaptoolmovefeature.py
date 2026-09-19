"""QgsMapToolMoveFeature: click source, then destination; Escape cancels.

Corresponds to src/app/qgsmaptoolmovefeature.cpp. Uses the native CAD event
pipeline, snapping, feature edit buffer and a single undo command per move.
"""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle,
    QgsPointLocator, QgsProject, QgsTolerance, QgsVectorLayer,
)
from qgis.gui import QgsMapToolAdvancedDigitizing, QgsRubberBand, QgsSnapIndicator


class QgsMapToolMoveFeature(QgsMapToolAdvancedDigitizing):
    Move, CopyMove = range(2)

    def __init__(self, canvas, mode=Move, cadDock=None):
        super().__init__(canvas, cadDock)
        self.mMode = mode
        self.mStartPointMapCoords = None
        self.mMovedFeatures = []
        self.mRubberBand = None
        self.mLayer = None
        self.mGeom = QgsGeometry()
        self.mSnapIndicator = QgsSnapIndicator(canvas)

    def cadCanvasReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self.deleteRubberband()
            self.mSnapIndicator.setMatch(QgsPointLocator.Match())
            return
        if event.button() != Qt.LeftButton: return
        layer = self.canvas().currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable():
            self.deleteRubberband()
            self.mSnapIndicator.setMatch(QgsPointLocator.Match())
            return
        if self.mStartPointMapCoords is None:
            mapPoint = QgsPointXY(event.mapPoint())
            layerPoint = self.toLayerCoordinates(layer, mapPoint)
            tolerance = QgsTolerance.vertexSearchRadius(layer, self.canvas().mapSettings())
            rect = QgsRectangle(layerPoint.x() - tolerance, layerPoint.y() - tolerance,
                                layerPoint.x() + tolerance, layerPoint.y() + tolerance)
            features = list(layer.getSelectedFeatures())
            if not features:
                request = QgsFeatureRequest().setFilterRect(rect).setNoAttributes()
                pointGeometry = QgsGeometry.fromPointXY(layerPoint)
                candidates = [(pointGeometry.distance(feature.geometry()), feature)
                              for feature in layer.getFeatures(request) if feature.hasGeometry()]
                if candidates:
                    distance, feature = min(candidates, key=lambda item: item[0])
                    if distance <= tolerance:
                        features = [feature]
            if not features:
                self.deleteRubberband()
                return
            self.mLayer = layer
            self.mMovedFeatures = [feature.id() for feature in features]
            self.mGeom = QgsGeometry.collectGeometry([feature.geometry() for feature in features])
            self.mStartPointMapCoords = mapPoint
            self.mRubberBand = QgsRubberBand(self.canvas(), layer.geometryType())
            self.mRubberBand.setColor(QColor(255, 100, 50, 100))
            self.mRubberBand.setToGeometry(self.mGeom, layer)
        else:
            if layer is self.mLayer:
                start = self.toLayerCoordinates(layer, self.mStartPointMapCoords)
                end = self.toLayerCoordinates(layer, event.mapPoint())
                self.moveFeatures(layer, self.mMovedFeatures, end.x() - start.x(), end.y() - start.y())
            self.deleteRubberband()
            self.mSnapIndicator.setMatch(QgsPointLocator.Match())

    def moveFeatures(self, layer, features, dx, dy):
        if not layer.isEditable(): return False
        featureIds = [feature.id() if hasattr(feature, 'id') else feature for feature in features]
        request = QgsFeatureRequest().setFilterFids(featureIds).setNoAttributes()
        features = list(layer.getFeatures(request))
        layer.beginEditCommand(QCoreApplication.translate('MainWindow', 'Copy and Move Feature(s)') if self.mMode == self.CopyMove else QCoreApplication.translate('QgsMapToolMoveFeature', 'Move feature'))
        success = True
        for feature in features:
            if self.mMode == self.CopyMove:
                from qgis.core import QgsVectorLayerUtils, QgsFieldConstraints
                geometry = feature.geometry()
                geometry.translate(dx, dy)
                attributes = {i: value for i, value in enumerate(feature.attributes()) if not layer.fields().at(i).constraints().constraints() & QgsFieldConstraints.ConstraintUnique}
                copied = QgsVectorLayerUtils.createFeature(layer, geometry, attributes, layer.createExpressionContext())
                success = layer.addFeature(copied)
            else:
                geometry = feature.geometry()
                success = geometry.translate(dx, dy) == Qgis.GeometryOperationResult.Success
                if success:
                    success = layer.changeGeometry(feature.id(), geometry)
                    if success and QgsProject.instance().topologicalEditing():
                        layer.addTopologicalPoints(geometry)
            if not success: break
        if success: layer.endEditCommand()
        else: layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def cadCanvasMoveEvent(self, event):
        self.mSnapIndicator.setMatch(event.mapPointMatch())
        if self.mRubberBand is not None:
            point = QgsPointXY(event.mapPoint())
            layer = self.canvas().currentLayer()
            if isinstance(layer, QgsVectorLayer) and layer.crs() == self.canvas().mapSettings().destinationCrs():
                self.mRubberBand.setTranslationOffset(
                    point.x() - self.mStartPointMapCoords.x(),
                    point.y() - self.mStartPointMapCoords.y())
            elif isinstance(layer, QgsVectorLayer):
                start = self.toLayerCoordinates(layer, self.mStartPointMapCoords)
                end = self.toLayerCoordinates(layer, point)
                geometry = QgsGeometry(self.mGeom)
                if geometry.translate(end.x() - start.x(), end.y() - start.y()) == Qgis.GeometryOperationResult.Success:
                    self.mRubberBand.setToGeometry(geometry, layer)
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Escape: self.deleteRubberband()
        else: super().keyReleaseEvent(event)
    def deleteRubberband(self):
        if self.mRubberBand is not None:
            from qgis.PyQt import sip
            sip.delete(self.mRubberBand)
        self.mRubberBand = None
        self.mStartPointMapCoords = None
        self.mMovedFeatures = []
        self.mLayer = None
        self.mGeom = QgsGeometry()
    def deactivate(self):
        self.deleteRubberband()
        self.mSnapIndicator.setMatch(QgsPointLocator.Match())
        super().deactivate()
