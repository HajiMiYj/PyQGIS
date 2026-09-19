"""Canvas feature actions with native QgsAction execution and click context."""
from qgis.PyQt.QtCore import QCoreApplication, Qt, QPoint
from qgis.PyQt.QtWidgets import QMenu
from qgis.core import Qgis, QgsVectorLayer, QgsFeatureRequest, QgsRectangle, QgsCsException, QgsExpression, QgsExpressionContextUtils, QgsExpressionContextScope
from qgis.gui import QgsMapTool, QgsGui, QgsMapLayerActionContext


class QgsMapToolFeatureAction(QgsMapTool):
    def __init__(self, canvas, app=None):
        super().__init__(canvas)
        self.mApp = app

    def canvasReleaseEvent(self, event):
        if event.button() != Qt.LeftButton: return
        layer = self.canvas().currentLayer()
        if not isinstance(layer, QgsVectorLayer) or layer not in self.canvas().layers(): return
        if not self.doAction(layer, event.pos().x(), event.pos().y()):
            self.messageEmitted.emit('此位置没有要素，或未设置默认要素动作', Qgis.Info)

    def doAction(self, layer, x, y):
        point = self.canvas().getCoordinateTransform().toMapCoordinates(x, y)
        radius = self.searchRadiusMU(self.canvas())
        try: rectangle = self.toLayerCoordinates(layer, QgsRectangle(point.x()-radius, point.y()-radius, point.x()+radius, point.y()+radius))
        except QgsCsException: return False
        features = list(layer.getFeatures(QgsFeatureRequest().setFilterRect(rectangle).setFlags(QgsFeatureRequest.ExactIntersect)))
        if not features: return False
        if len(features) == 1: return self.doActionForFeature(layer, features[0], point)
        context = layer.createExpressionContext()
        expression = QgsExpression(layer.displayExpression())
        expression.prepare(context)
        menu = QMenu(self.canvas())
        for feature in features:
            context.setFeature(feature)
            action = menu.addAction(str(expression.evaluate(context) or feature.id()))
            action.triggered.connect(lambda checked=False, f=feature: self.doActionForFeature(layer, f, point))
        menu.addAction(QCoreApplication.translate('QgsMapToolFeatureAction', 'All Features'), lambda: [self.doActionForFeature(layer, f, point) for f in features])
        menu.exec_(self.canvas().mapToGlobal(QPoint(x+5, y+5)))
        menu.deleteLater()
        return True

    def doActionForFeature(self, layer, feature, point):
        action = layer.actions().defaultAction('Canvas')
        if action.isValid():
            if action.isEnabledOnlyWhenEditable() and not layer.isEditable():
                self.messageEmitted.emit('默认动作仅在图层编辑状态下可用', Qgis.Info)
                return False
            context = layer.createExpressionContext()
            context.setFeature(feature)
            context.appendScope(QgsExpressionContextUtils.mapSettingsScope(self.canvas().mapSettings()))
            scope = QgsExpressionContextScope()
            for name, value in [('click_x', point.x()), ('click_y', point.y()), ('action_scope', 'Canvas')]: scope.setVariable(name, value)
            context.appendScope(scope)
            if action.type() == Qgis.AttributeActionType.GenericPython:
                # QGIS Desktop installs a C++ QgsPythonRunner; a standalone
                # PyQGIS process supplies the equivalent Python execution here.
                import qgis.utils
                command = QgsExpression.replaceExpressionText(action.command(), context)
                namespace = {'iface': qgis.utils.iface, 'qgis': qgis, '__name__': '__qgis_action__'}
                try: exec(compile(command, '<QGIS feature action>', 'exec'), namespace, namespace)
                except Exception as error:
                    self.messageEmitted.emit(str(error), Qgis.Critical)
                    return False
            else: action.run(layer, feature, context)
            return True
        action = QgsGui.mapLayerActionRegistry().defaultActionForLayer(layer)
        if action:
            context = self.mApp.createMapLayerActionContext() if self.mApp else QgsMapLayerActionContext()
            available = QgsGui.mapLayerActionRegistry().mapLayerActions(layer, Qgis.MapLayerActionTarget.SingleFeature, context)
            if action not in available or not action.isEnabled(): return False
            action.triggerForFeature(layer, feature)
            action.triggerForFeature(layer, feature, context)
            return True
        self.messageEmitted.emit('请在要素动作下拉菜单中选择默认动作', Qgis.Info)
        return False
