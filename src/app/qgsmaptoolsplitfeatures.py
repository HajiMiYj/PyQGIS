"""Application geometry editing capture with the native CAD/snapping pipeline."""
from qgis.core import Qgis, QgsGeometry, QgsFeatureRequest, QgsLineString, QgsVectorLayer, QgsProject, QgsCurvePolygon, QgsPointXY, QgsWkbTypes
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapToolCapture


class _GeometryEditCapture(QgsMapToolCapture):
    def __init__(self, canvas, cadDock, operation, mode=QgsMapToolCapture.CaptureLine):
        super().__init__(canvas, cadDock, mode)
        self.mOperation = operation

    def supportsTechnique(self, technique):
        if self.mOperation in ('addRing', 'fillRing', 'addPart'):
            return technique in (Qgis.CaptureTechnique.StraightSegments, Qgis.CaptureTechnique.Streaming) or (
                self.mode() != self.CapturePoint and technique in (Qgis.CaptureTechnique.CircularString, Qgis.CaptureTechnique.Shape))
        return super().supportsTechnique(technique)

    def cadCanvasReleaseEvent(self, event):
        geometry = None
        if self.mode() == self.CapturePoint and event.button() == Qt.LeftButton:
            geometry = QgsGeometry.fromPointXY(self.toLayerCoordinates(self.canvas().currentLayer(), event.mapPoint()))
        elif event.button() == Qt.RightButton and self.size() >= (3 if self.mode() == self.CapturePolygon else 2):
            if self.mode() == self.CapturePolygon:
                self.closePolygon()
                polygon = QgsCurvePolygon()
                polygon.setExteriorRing(self.captureCurve().clone())
                geometry = QgsGeometry(polygon)
            else: geometry = QgsGeometry(self.captureCurve().clone())
        # Keep the native CAD event handling and capture cleanup. Apply through
        # this exposed virtual handler instead of an app-private completion hook.
        super().cadCanvasReleaseEvent(event)
        if geometry is not None:
            self.applyGeometry(self.canvas().currentLayer(), geometry)

    def applyGeometry(self, layer, geometry):
        if not isinstance(layer, QgsVectorLayer) or not layer.isEditable(): return False
        labels = {'splitFeatures': '分割要素', 'splitParts': '分割部件', 'addRing': '添加环', 'addPart': '添加部件', 'reshape': '重塑要素'}
        label = labels[self.mOperation]
        layer.beginEditCommand(label)
        try:
            points = list(geometry.vertices())
            if self.mOperation in ('splitFeatures', 'splitParts'):
                result = getattr(layer, self.mOperation)([QgsPointXY(point) for point in points], QgsProject.instance().topologicalEditing())
                success = result == Qgis.GeometryOperationResult.Success
            elif self.mOperation == 'addRing':
                # The captured ring arrives as a surface with the polygon capture
                # technique, but as a bare curve (QgsCompoundCurve) with the curve
                # techniques, which has no exteriorRing().
                captured = geometry.constGet()
                ring = captured.exteriorRing().clone() if isinstance(captured, QgsCurvePolygon) else captured.clone()
                result = layer.addCurvedRing(ring)
                success = (result[0] if isinstance(result, tuple) else result) == Qgis.GeometryOperationResult.Success
            elif self.mOperation == 'addPart':
                # The two point-list SIP overloads are ambiguous in 3.34. Pass
                # the full native geometry to preserve curves, Z and M instead.
                selected = list(layer.getSelectedFeatures())
                success = False
                if len(selected) == 1:
                    feature = selected[0]
                    edited = feature.geometry()
                    parts = geometry.coerceToType(QgsWkbTypes.singleType(layer.wkbType()))
                    result = edited.addPart(parts[0].constGet().clone(), layer.geometryType()) if parts else None
                    if result == Qgis.GeometryOperationResult.Success:
                        if not feature.hasGeometry() and QgsWkbTypes.isSingleType(layer.wkbType()) and layer.dataProvider().doesStrictFeatureTypeCheck():
                            edited.convertToSingleType()
                        success = layer.changeGeometry(feature.id(), edited)
                        if success and QgsProject.instance().topologicalEditing(): layer.addTopologicalPoints(geometry)
            else:
                candidates = layer.getSelectedFeatures() if layer.selectedFeatureCount() else layer.getFeatures(QgsFeatureRequest().setFilterRect(geometry.boundingBox()))
                success = False
                for feature in candidates:
                    edited = feature.geometry()
                    if edited.reshapeGeometry(QgsLineString(points)) == Qgis.GeometryOperationResult.Success:
                        if not layer.changeGeometry(feature.id(), edited): raise RuntimeError('图层拒绝几何修改')
                        success = True
            if success: layer.endEditCommand()
            else:
                layer.destroyEditCommand()
                self.messageEmitted.emit(label + '未完成：请检查图层类型、选择的要素及绘制范围', Qgis.Warning)
            layer.triggerRepaint()
            return success
        except Exception:
            layer.destroyEditCommand()
            raise


class QgsMapToolSplitFeatures(_GeometryEditCapture):
    def __init__(self, canvas, cadDock): super().__init__(canvas, cadDock, 'splitFeatures')
