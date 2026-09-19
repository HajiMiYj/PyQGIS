"""Delete the clicked multipart component; uses native geometry and edit buffer."""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.core import QgsVectorLayer, QgsGeometry, QgsFeatureRequest, QgsRectangle, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsMapToolEdit


class QgsMapToolDeletePart(QgsMapToolEdit):
    def __init__(self, canvas, deleteRing=False):
        super().__init__(canvas)
        self.mDeleteRing = deleteRing
    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton: return
        self.deleteAt(event.mapPoint())
    def deleteAt(self, point):
        layer = self.canvas().currentLayer()
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable(): return False
        tolerance = self.canvas().mapUnitsPerPixel() * 8
        rect = QgsRectangle(point.x()-tolerance, point.y()-tolerance, point.x()+tolerance, point.y()+tolerance)
        if self.mDeleteRing: rect = self.canvas().extent()
        request = QgsFeatureRequest().setFilterRect(self.toLayerCoordinates(layer, rect))
        local = QgsGeometry.fromPointXY(self.toLayerCoordinates(layer, point))
        candidates = []
        for feature in layer.getFeatures(request):
            if layer.selectedFeatureCount() and feature.id() not in layer.selectedFeatureIds(): continue
            geometry = feature.geometry()
            if self.mDeleteRing:
                polygons = geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]
                for partIndex, polygon in enumerate(polygons):
                    for ringIndex, ring in enumerate(polygon[1:], 1):
                        ringGeometry = QgsGeometry.fromPolygonXY([ring])
                        if ringGeometry.contains(local): candidates.append((ringGeometry.area(), feature, partIndex, ringIndex))
            elif geometry.isMultipart():
                for index, part in enumerate(geometry.asGeometryCollection()):
                    part.transform(self.canvas().mapSettings().layerTransform(layer))
                    distance = part.distance(QgsGeometry.fromPointXY(point))
                    if distance <= tolerance: candidates.append((distance, feature, index, None))
        if not candidates: return False
        _, feature, partIndex, ringIndex = min(candidates, key=lambda candidate: candidate[0])
        geometry = feature.geometry()
        success = geometry.deleteRing(ringIndex, partIndex) if self.mDeleteRing else geometry.deletePart(partIndex)
        if not success: return False
        layer.beginEditCommand(QCoreApplication.translate('MainWindow', 'Delete Ring') if self.mDeleteRing else QCoreApplication.translate('QgsMapToolDeletePart', 'Delete part'))
        success = layer.changeGeometry(feature.id(), geometry)
        if success: layer.endEditCommand()
        else: layer.destroyEditCommand()
        layer.triggerRepaint()
        return success
