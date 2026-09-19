"""Selection predicates and modifier behavior from qgsmaptoolselectutils.cpp."""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.core import Qgis, QgsApplication, QgsCsException, QgsGeometry, QgsFeatureRequest, QgsVectorLayer


class QgsMapToolSelectUtils:
    @staticmethod
    def setSelectedFeatures(canvas, selectGeometry, modifiers=Qt.NoModifier, single=False):
        layer = canvas.currentLayer()
        if not isinstance(layer, QgsVectorLayer) or selectGeometry.isEmpty(): return
        geometry = QgsGeometry(selectGeometry)
        transform = canvas.mapSettings().layerTransform(layer)
        try:
            if not transform.isShortCircuited():
                geometry = geometry.densifyByCount(9)
            geometry.transform(transform, Qgis.TransformDirection.Reverse)
        except QgsCsException as error:
            QgsApplication.messageLog().logMessage(str(error), QCoreApplication.translate('MainWindow', 'Select'), Qgis.Warning)
            return
        contains = bool(modifiers & Qt.AltModifier) and not single
        predicate = geometry.contains if contains else geometry.intersects
        request = QgsFeatureRequest().setFilterRect(geometry.boundingBox()).setNoAttributes()
        matches = [feature for feature in layer.getFeatures(request) if predicate(feature.geometry())]
        shift, ctrl = bool(modifiers & Qt.ShiftModifier), bool(modifiers & Qt.ControlModifier)
        if single:
            # Prefer nearest geometry, then smallest area when polygons overlap.
            matches.sort(key=lambda f: (f.geometry().distance(geometry.centroid()), f.geometry().area(), f.id()))
            ids = [matches[0].id()] if matches else []
            if shift or ctrl:
                for fid in ids:
                    if fid in layer.selectedFeatureIds(): layer.deselect([fid])
                    else: layer.select([fid])
                return
        else: ids = [feature.id() for feature in matches]
        behavior = (Qgis.SelectBehavior.IntersectSelection if shift and ctrl else
                    Qgis.SelectBehavior.AddToSelection if shift else
                    Qgis.SelectBehavior.RemoveFromSelection if ctrl else Qgis.SelectBehavior.SetSelection)
        layer.selectByIds(ids, behavior)
