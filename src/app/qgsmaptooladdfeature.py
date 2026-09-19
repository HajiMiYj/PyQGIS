"""Application completion policy around the native feature capture tool."""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt import sip
from qgis.core import (Qgis, QgsGeometry, QgsPoint, QgsCoordinateTransform,
                       QgsCsException, QgsExpressionContextUtils)
from qgis.gui import QgsMapToolDigitizeFeature


class QgsMapToolAddFeature(QgsMapToolDigitizeFeature):
    def __init__(self, canvas, cadDock, app):
        super().__init__(canvas, cadDock)
        self.mApp = app

    def addFeature(self, layer, feature):
        if not layer or not layer.isEditable(): return False
        # Capture matches must be read before the native parent clears its curve.
        matches = self.snappingMatches()
        context = layer.createExpressionContext()
        context.appendScope(QgsExpressionContextUtils.mapToolCaptureScope(matches))
        success, added = self.mApp.mVectorLayerTools.addFeature(layer,
            defaultGeometry=feature.geometry(), parentWidget=self.mApp, expressionContext=context)
        if not success: return False
        project = self.mApp.mProject
        if project.topologicalEditing():
            geometry = added.geometry() if added is not None else feature.geometry()
            targets = []
            if project.avoidIntersectionsMode() == Qgis.AvoidIntersectionsMode.AvoidIntersectionsLayers:
                targets = [candidate for candidate in project.avoidIntersectionsLayers()
                           if candidate.isEditable() and candidate.geometryType() == Qgis.GeometryType.Polygon]
            for target in targets:
                self.addTopologicalGeometry(layer, target, geometry)
            for index, match in enumerate(matches):
                target = match.layer()
                if target is None or sip.isdeleted(target) or target is layer or not target.isEditable(): continue
                point = feature.geometry().vertexAt(index)
                if point.isEmpty(): continue
                self.addTopologicalGeometry(layer, target, QgsGeometry(QgsPoint(point)))
            layer.addTopologicalPoints(geometry)
        layer.triggerRepaint()
        return True

    def addTopologicalGeometry(self, source, target, geometry):
        transformed = QgsGeometry(geometry)
        try:
            if source.crs() != target.crs():
                transformed.transform(QgsCoordinateTransform(source.crs(), target.crs(), self.mApp.mProject))
            target.addTopologicalPoints(transformed)
            target.triggerRepaint()
        except QgsCsException as error:
            self.mApp.mMessageBar.pushWarning(QCoreApplication.translate('QgsSnappingWidget', 'Topological Editing'), str(error))
