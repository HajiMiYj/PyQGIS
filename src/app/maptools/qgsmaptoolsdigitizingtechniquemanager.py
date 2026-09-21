"""Python counterpart of the application digitizing technique manager.

The 3.34 shape registry is not bound. Keep its metadata IDs and compose the
Python CAD tools with the native capture tool which owns feature completion.
"""
from functools import partial

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QActionGroup, QMenu, QToolButton
from qgis.core import Qgis, QgsApplication, QgsVectorLayer, QgsVectorDataProvider
from qgis.gui import QgsMapToolCapture
from src.gui.maptools.qgsmaptoolshapeabstract import QgsMapToolShapeAbstract
from .qgsmaptoolshapecircle2points import QgsMapToolShapeCircle2Points
from .qgsmaptoolshapecircle3points import QgsMapToolShapeCircle3Points
from .qgsmaptoolshapecircle2tangentspoint import QgsMapToolShapeCircle2TangentsPoint
from .qgsmaptoolshapecircle3tangents import QgsMapToolShapeCircle3Tangents
from .qgsmaptoolshapecircularstringradius import QgsMapToolShapeCircularStringRadius
from .qgsmaptoolshapecirclecenterpoint import QgsMapToolShapeCircleCenterPoint
from .qgsmaptoolshapeellipsecenter2points import QgsMapToolShapeEllipseCenter2Points
from .qgsmaptoolshapeellipsecenterpoint import QgsMapToolShapeEllipseCenterPoint
from .qgsmaptoolshapeellipseextent import QgsMapToolShapeEllipseExtent
from .qgsmaptoolshapeellipsefoci import QgsMapToolShapeEllipseFoci
from .qgsmaptoolshaperectangle3points import QgsMapToolShapeRectangle3Points
from .qgsmaptoolshaperectanglecenter import QgsMapToolShapeRectangleCenter
from .qgsmaptoolshaperectangleextent import QgsMapToolShapeRectangleExtent
from .qgsmaptoolshaperegularpolygon2points import QgsMapToolShapeRegularPolygon2Points
from .qgsmaptoolshaperegularpolygoncentercorner import QgsMapToolShapeRegularPolygonCenterCorner
from .qgsmaptoolshaperegularpolygoncenterpoint import QgsMapToolShapeRegularPolygonCenterPoint

# 形状菜单：上游 QgsShapeToolButton 的分组、图标与标题（对应 3.34 的
# shape registry，未绑定，按原版顺序与分组内联）。
SHAPE_MENU = (
    ('circle-from-2-points', 'Circle', '/mActionCircle2Points.svg', 'Circle from 2 points'),
    ('circle-from-2-tangents-1-point', 'Circle', '/mActionCircle2TangentsPoint.svg', 'Circle from 2 tangents and a point'),
    ('circle-from-3-points', 'Circle', '/mActionCircle3Points.svg', 'Circle from 3 points'),
    ('circle-from-3-tangents', 'Circle', '/mActionCircle3Tangents.svg', 'Circle from 3 tangents'),
    ('circle-by-a-center-point-and-another-point', 'Circle', '/mActionCircleCenterPoint.svg', 'Circle by a center point and another point'),
    ('circular-string-by-radius', 'Curve', '/mActionCircularStringRadius.svg', 'Circular string by radius'),
    ('ellipse-center-2-points', 'Ellipse', '/mActionEllipseCenter2Points.svg', 'Ellipse from center and 2 points'),
    ('ellipse-center-point', 'Ellipse', '/mActionEllipseCenterPoint.svg', 'Ellipse from center and a point'),
    ('ellipse-from-extent', 'Ellipse', '/mActionEllipseExtent.svg', 'Ellipse from Extent'),
    ('ellipse-from-foci', 'Ellipse', '/mActionEllipseFoci.svg', 'Ellipse from Foci'),
    ('rectangle-from-3-points-distance', 'Rectangle', '/mActionRectangle3PointsDistance.svg', 'Rectangle from 3 points (distance)'),
    ('rectangle-from-3-points-projected', 'Rectangle', '/mActionRectangle3PointsProjected.svg', 'Rectangle from 3 points (projected)'),
    ('rectangle-from-center-and-a-point', 'Rectangle', '/mActionRectangleCenter.svg', 'Rectangle from center and a point'),
    ('rectangle-from-extent', 'Rectangle', '/mActionRectangleExtent.svg', 'Rectangle from extent'),
    ('regular-polygon-from-2-points', 'RegularPolygon', '/mActionRegularPolygon2Points.svg', 'Regular polygon from 2 points'),
    ('regular-polygon-from-center-and-a-corner', 'RegularPolygon', '/mActionRegularPolygonCenterCorner.svg', 'Regular polygon from center and a corner'),
    ('regular-polygon-from-center-point', 'RegularPolygon', '/mActionRegularPolygonCenterPoint.svg', 'Regular polygon from center and a point'),
)


class QgsMapToolsDigitizingTechniqueManager:
    SHAPE_TOOLS = {
        'circle-from-2-points': QgsMapToolShapeCircle2Points,
        'circle-from-3-points': QgsMapToolShapeCircle3Points,
        'circle-from-2-tangents-1-point': QgsMapToolShapeCircle2TangentsPoint,
        'circle-from-3-tangents': QgsMapToolShapeCircle3Tangents,
        'circular-string-by-radius': QgsMapToolShapeCircularStringRadius,
        'circle-by-a-center-point-and-another-point': QgsMapToolShapeCircleCenterPoint,
        'ellipse-center-2-points': QgsMapToolShapeEllipseCenter2Points,
        'ellipse-center-point': QgsMapToolShapeEllipseCenterPoint,
        'ellipse-from-extent': QgsMapToolShapeEllipseExtent,
        'ellipse-from-foci': QgsMapToolShapeEllipseFoci,
        'rectangle-from-3-points-distance': QgsMapToolShapeRectangle3Points,
        'rectangle-from-3-points-projected': QgsMapToolShapeRectangle3Points,
        'rectangle-from-center-and-a-point': QgsMapToolShapeRectangleCenter,
        'rectangle-from-extent': QgsMapToolShapeRectangleExtent,
        'regular-polygon-from-2-points': QgsMapToolShapeRegularPolygon2Points,
        'regular-polygon-from-center-and-a-corner': QgsMapToolShapeRegularPolygonCenterCorner,
        'regular-polygon-from-center-point': QgsMapToolShapeRegularPolygonCenterPoint,
    }
    SETTINGS = 'digitizing/shape-map-tools/'

    def __init__(self, app):
        self.mApp = app
        self.mShapeActions, self.mShapeCategoryButtons = {}, {}
        self.mShapeTool = None
        self.mShapeActionGroup = QActionGroup(app)

    def setupToolBars(self):
        app = self.mApp
        self.mDigitizeModeToolButton = QToolButton(app.mDigitizeToolBar)
        self.mDigitizeModeToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(self.mDigitizeModeToolButton)
        for name in ('DigitizeWithSegment', 'DigitizeWithCurve', 'StreamDigitize', 'DigitizeShape'):
            menu.addAction(getattr(app, 'mAction' + name))
        self.mDigitizeModeToolButton.setMenu(menu)
        self.mDigitizeModeToolButton.setDefaultAction(app.mActionDigitizeWithSegment)
        actions = app.mDigitizeToolBar.actions()
        app.mDigitizeToolBar.insertWidget(actions[3] if len(actions) > 3 else None, self.mDigitizeModeToolButton)
        for toolId, category, icon, text in SHAPE_MENU:
            if toolId not in self.SHAPE_TOOLS: continue
            button = self.mShapeCategoryButtons.get(category)
            if button is None:
                button = QToolButton(app.mShapeDigitizeToolBar)
                button.setPopupMode(QToolButton.MenuButtonPopup)
                button.setMenu(QMenu(button))
                app.mShapeDigitizeToolBar.addWidget(button)
                self.mShapeCategoryButtons[category] = button
            # Upstream metadata uses QObject::tr.
            cls = self.SHAPE_TOOLS[toolId]
            title = QCoreApplication.translate('QObject', text)
            action = QAction(QgsApplication.getThemeIcon(icon), title, button.menu())
            action.setCheckable(True)
            action.setData(toolId)
            clicks = cls.pointCount - 1
            action.setToolTip(title + '：' + getattr(cls, 'instructions', f'左键确定 {clicks} 个点，移动预览，右键确定末点并完成；Esc 取消，退格退点'))
            action.triggered.connect(partial(self.setShapeTool, toolId))
            button.menu().addAction(action)
            self.mShapeActionGroup.addAction(action)
            self.mShapeActions[toolId] = action
            key = self.SETTINGS + 'categories/' + category + '/default'
            if button.defaultAction() is None or app.mSettings.value(key, '') == toolId:
                button.setDefaultAction(action)

    def parentAvailable(self, parent):
        if parent is None or sip.isdeleted(parent): return False
        if not isinstance(parent, QgsMapToolCapture) or not parent.supportsTechnique(Qgis.CaptureTechnique.Shape): return False
        layer = parent.layer()
        if layer is None or sip.isdeleted(layer) or not layer.isValid(): return False
        if isinstance(layer, QgsVectorLayer):
            if layer is not self.mApp.activeLayer() or not layer.isEditable() or layer.readOnly(): return False
            if layer.geometryType() not in (Qgis.GeometryType.Line, Qgis.GeometryType.Polygon): return False
            action = parent.action()
            if action and not action.isEnabled(): return False
            if parent is self.mApp.mMapTools['addFeature']:
                return bool(layer.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures)
        return True

    def captureTool(self):
        tool = self.mApp.mMapCanvas.mapTool()
        if isinstance(tool, QgsMapToolShapeAbstract): tool = tool.mParentTool
        if self.parentAvailable(tool): return tool
        tool = self.mApp.mMapTools['addFeature']
        return tool if self.parentAvailable(tool) else None

    def setShapeTool(self, toolId=None, checked=False):
        app, canvas = self.mApp, self.mApp.mMapCanvas
        toolId = toolId or app.mSettings.value(self.SETTINGS + 'current', 'circle-from-2-points')
        if toolId not in self.SHAPE_TOOLS: toolId = 'circle-from-2-points'
        parent = self.captureTool()
        if parent is None:
            app.mMessageBar.pushWarning(QCoreApplication.translate('MainWindow', 'Digitize Shape'), '请先使线/面矢量图层进入编辑状态，或启用支持形状的注记捕获工具')
            self.updateActions()
            return
        canvas.setMapTool(parent)
        if not self.SHAPE_TOOLS[toolId].continuePreviousCurve: parent.stopCapturing()
        parent.setCurrentCaptureTechnique(Qgis.CaptureTechnique.StraightSegments)
        if self.mShapeTool is not None:
            self.mShapeTool.dispose()
            sip.delete(self.mShapeTool)
        self.mShapeTool = self.SHAPE_TOOLS[toolId](toolId, parent, self)
        canvas.setMapTool(self.mShapeTool)
        app.mSettings.setValue(self.SETTINGS + 'current', toolId)
        for category, button in self.mShapeCategoryButtons.items():
            if self.mShapeActions[toolId] in button.menu().actions():
                button.setDefaultAction(self.mShapeActions[toolId])
                app.mSettings.setValue(self.SETTINGS + 'categories/' + category + '/default', toolId)
        self.updateActions()

    def finishShape(self, tool, curve, event):
        parent, canvas = tool.mParentTool, self.mApp.mMapCanvas
        if not self.parentAvailable(parent): return
        tool.prepareCurve(curve, parent.mapPoint(event))
        canvas.setMapTool(parent)
        parent.setCurrentCaptureTechnique(Qgis.CaptureTechnique.StraightSegments)
        if not tool.continuePreviousCurve: parent.clearCurve()
        # addCurve owns c (and deletes it after cross-CRS conversion), although
        # the QGIS 3.34 SIP declaration omits Transfer. Release before the call.
        sip.transferto(curve, None)
        result = parent.addCurve(curve)
        if result == 0:
            parent.startCapturing()
            parent.canvasReleaseEvent(event)
        else:
            parent.stopCapturing()
            self.mApp.mMessageBar.pushWarning(QCoreApplication.translate('MainWindow', 'Digitize Shape'), '无法将形状转换到目标图层坐标系')
        if canvas.mapTool() is parent and self.parentAvailable(parent):
            canvas.setMapTool(tool)
        self.updateActions()

    def setCaptureTechnique(self, technique):
        canvas = self.mApp.mMapCanvas
        tool = canvas.mapTool()
        if isinstance(tool, QgsMapToolShapeAbstract):
            canvas.setMapTool(tool.mParentTool)
            tool = tool.mParentTool
        if isinstance(tool, QgsMapToolCapture) and tool.supportsTechnique(technique):
            tool.setCurrentCaptureTechnique(technique)
        self.mApp.mMapTools['addFeature'].setCurrentCaptureTechnique(technique)
        self.updateActions()

    def updateActions(self):
        app, canvas = self.mApp, self.mApp.mMapCanvas
        tool = canvas.mapTool()
        shaping = isinstance(tool, QgsMapToolShapeAbstract)
        if shaping and not self.parentAvailable(tool.mParentTool):
            canvas.setMapTool(app.mMapTools['pan'])
            return
        available = self.captureTool() is not None
        app.mActionDigitizeShape.setEnabled(available)
        app.mActionDigitizeShape.setChecked(shaping)
        for toolId, action in self.mShapeActions.items():
            action.setEnabled(available)
            action.setChecked(shaping and tool.mId == toolId)
        parent = tool.mParentTool if shaping else tool
        for name in ('DigitizeWithSegment', 'DigitizeWithCurve', 'StreamDigitize'):
            action = getattr(app, 'mAction' + name)
            enabled = isinstance(parent, QgsMapToolCapture) and parent.supportsTechnique(action.data())
            action.setEnabled(enabled)
            action.setChecked(bool(enabled and not shaping and parent.currentCaptureTechnique() == action.data()))
        if hasattr(self, 'mDigitizeModeToolButton'):
            current = next((action for action in self.mDigitizeModeToolButton.menu().actions() if action.isChecked()), app.mActionDigitizeWithSegment)
            self.mDigitizeModeToolButton.setDefaultAction(current)

    def shutdown(self):
        if self.mShapeTool is not None:
            self.mShapeTool.dispose()
            sip.delete(self.mShapeTool)
            self.mShapeTool = None
