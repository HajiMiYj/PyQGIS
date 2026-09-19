"""QgsMapToolFillRing: add-and-fill, or Shift-click an existing hole, atomically."""
from qgis.PyQt.QtCore import Qt
from qgis.core import Qgis, QgsGeometry, QgsFeatureRequest, QgsPointXY, QgsVectorLayerUtils, QgsVectorLayer, QgsVectorDataProvider, QgsCurvePolygon
from qgis.gui import QgsMapToolCapture, QgsAttributeDialog, QgsAttributeEditorContext
from .qgsmaptoolsplitfeatures import _GeometryEditCapture


class QgsMapToolFillRing(_GeometryEditCapture):
    def __init__(self, canvas, cadDock, app):
        super().__init__(canvas, cadDock, 'fillRing', QgsMapToolCapture.CapturePolygon)
        self.mApp, self.mModifiers = app, Qt.NoModifier

    def cadCanvasReleaseEvent(self, event):
        self.mModifiers = event.modifiers()
        if event.button() == Qt.LeftButton and self.mModifiers == Qt.ShiftModifier:
            self.fillRingUnderPoint(event.mapPoint())
        else: super().cadCanvasReleaseEvent(event)

    def getCheckLayer(self, layer=None):
        layer = layer or self.canvas().currentLayer()
        if isinstance(layer, QgsVectorLayer) and layer.isEditable() and layer.geometryType() == Qgis.GeometryType.Polygon:
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.ChangeGeometries and caps & QgsVectorDataProvider.AddFeatures: return layer
        return None

    def applyGeometry(self, layer, geometry, showForm=None):
        layer = self.getCheckLayer(layer)
        if not layer: return False
        layer.beginEditCommand('添加并填充环')
        try:
            result, fid = layer.addCurvedRing(geometry.constGet().exteriorRing().clone())
            if result != Qgis.GeometryOperationResult.Success:
                layer.destroyEditCommand()
                self.messageEmitted.emit(f'无法添加环（{int(result)}）：检查闭合、自相交、包含关系及已有内环。', Qgis.Warning)
                return False
            return self.createFeature(layer, geometry, fid, showForm)
        except Exception:
            layer.destroyEditCommand()
            raise

    def createFeature(self, layer, geometry, fid, showForm=None):
        source = layer.getFeature(fid)
        if not source.isValid():
            layer.destroyEditCommand()
            return False
        context = layer.createExpressionContext()
        feature = QgsVectorLayerUtils.createFeature(layer, geometry, dict(enumerate(source.attributes())), context)
        showForm = not bool(self.mModifiers & Qt.ControlModifier) if showForm is None else showForm
        if showForm:
            editorContext = QgsAttributeEditorContext()
            editorContext.setVectorLayerTools(self.mApp.mVectorLayerTools)
            dialog = QgsAttributeDialog(layer, feature, False, self.mApp, True, editorContext)
            dialog.setMode(QgsAttributeEditorContext.AddFeatureMode)
            success = bool(dialog.exec_())
        else: success = layer.addFeature(feature)
        if success: layer.endEditCommand()
        else: layer.destroyEditCommand()
        layer.triggerRepaint()
        return success

    def fillRingUnderPoint(self, point, showForm=None):
        layer = self.getCheckLayer()
        if not layer: return False
        local = self.toLayerCoordinates(layer, point)
        request = QgsFeatureRequest().setFilterRect(self.toLayerCoordinates(layer, self.canvas().extent()))
        best = None
        for feature in layer.getFeatures(request):
            geometry = feature.geometry()
            polygons = geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
            for polygon in polygons:
                shape = polygon.constGet()
                # A geometry collection can hold bare curves (curve capture); those
                # have no interior rings and cannot hold a fillable ring.
                if not isinstance(shape, QgsCurvePolygon): continue
                for index in range(shape.numInteriorRings()):
                    ring = QgsCurvePolygon()
                    ring.setExteriorRing(shape.interiorRing(index).clone())
                    ringGeometry = QgsGeometry(ring)
                    if ringGeometry.contains(local) and (best is None or ringGeometry.area() < best[0]):
                        best = ringGeometry.area(), feature.id(), ringGeometry
        if best is None:
            self.messageEmitted.emit('此位置没有可填充的内环', Qgis.Info)
            return False
        layer.beginEditCommand('填充现有环')
        try: return self.createFeature(layer, best[2], best[1], showForm)
        except Exception:
            layer.destroyEditCommand()
            raise
