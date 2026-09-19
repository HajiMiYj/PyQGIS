"""Shape capture adapter, corresponding to gui/maptools/qgsmaptoolshapeabstract.

QGIS 3.34 does not bind QgsMapToolShapeAbstract or its registry. This adapter
uses native CAD events, geometry constructors and a native capture parent.
"""
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor
from math import isfinite
from qgis.core import Qgis, QgsGeometry, QgsPoint, QgsPointXY, QgsSettings, QgsWkbTypes, QgsVectorLayer, QgsVertexId
from qgis.gui import QgsMapToolAdvancedDigitizing, QgsRubberBand, QgsSpinBox


class QgsMapToolShapeAbstract(QgsMapToolAdvancedDigitizing):
    pointCount = 2
    regularPolygon = False
    keepFirstSnappedZ = False
    continuePreviousCurve = False

    def __init__(self, toolId, parentTool, manager):
        super().__init__(parentTool.canvas(), manager.mApp.mAdvancedDigitizingDockWidget)
        self.mId, self.mParentTool, self.mManager = toolId, parentTool, manager
        self.mPoints, self.mLastPoint = [], None
        self.mNumberSidesSpinBox = None
        self.mNumberSides = 6
        self.mTempRubberBand = QgsRubberBand(self.canvas(), Qgis.GeometryType.Line)
        self.mTempRubberBand.setColor(QColor(255, 100, 30, 220))
        self.mTempRubberBand.setWidth(2)
        self.mTempRubberBand.hide()
        self.setCursor(Qt.CrossCursor)
        self.setAutoSnapEnabled(True)

    def layer(self): return self.mParentTool.layer()

    def activate(self):
        super().activate()
        if self.regularPolygon:
            self.mNumberSidesSpinBox = QgsSpinBox()
            self.mNumberSidesSpinBox.setRange(3, 99999999)
            self.mNumberSidesSpinBox.setPrefix(QCoreApplication.translate('QgsMapToolShapeRegularPolygonAbstract', 'Number of sides: '))
            self.mNumberSidesSpinBox.setValue(self.mNumberSides)
            self.mNumberSidesSpinBox.valueChanged.connect(self.setNumberSides)
            self.mManager.mApp.addUserInputWidget(self.mNumberSidesSpinBox)

    def setNumberSides(self, count):
        self.mNumberSides = count
        self.updatePreview()

    def segments(self):
        return max(12, QgsSettings().value('qgis/digitizing/offset_quad_seg', 8, type=int) * 12)

    def shapeCurve(self, points): raise NotImplementedError

    def prepareCurve(self, curve, finalPoint=None):
        """Apply the upstream planar-Z rule before the parent takes ownership."""
        points = list(self.mPoints)
        if finalPoint is not None: points.append(finalPoint)
        defaultZ = QgsSettings().value('qgis/digitizing/default_z_value', 0., type=float)
        defaultM = QgsSettings().value('qgis/digitizing/default_m_value', 0., type=float)
        if hasattr(self.mParentTool, 'defaultZValue'): defaultZ = self.mParentTool.defaultZValue()
        if hasattr(self.mParentTool, 'defaultMValue'): defaultM = self.mParentTool.defaultMValue()
        elevations = [p.z() for p in points if QgsWkbTypes.hasZ(p.wkbType()) and isfinite(p.z())]
        measures = [p.m() for p in points if QgsWkbTypes.hasM(p.wkbType()) and isfinite(p.m())]
        if self.keepFirstSnappedZ:
            snappedZ = next((z for z in elevations if z != defaultZ), None)
            if snappedZ is not None:
                curve.dropZValue()
                curve.addZValue(snappedZ)
        layer = self.layer()
        if isinstance(layer, QgsVectorLayer):
            if QgsWkbTypes.hasZ(layer.wkbType()):
                if not curve.is3D(): curve.addZValue(elevations[0] if elevations else defaultZ)
            else: curve.dropZValue()
            if QgsWkbTypes.hasM(layer.wkbType()):
                if not curve.isMeasure(): curve.addMValue(measures[0] if measures else defaultM)
            else: curve.dropMValue()
            # Mixed 2D/3D control points may leave NaN ordinates in a 3D curve.
            # Preserve the constructor's finite values; fill only missing ones.
            for index in range(curve.numPoints()):
                point = curve.vertexAt(QgsVertexId(0, 0, index))
                changed = False
                if curve.is3D() and not isfinite(point.z()):
                    point.setZ(defaultZ)
                    changed = True
                if curve.isMeasure() and not isfinite(point.m()):
                    point.setM(defaultM)
                    changed = True
                if changed: curve.moveVertex(QgsVertexId(0, 0, index), point)
        return curve

    def updatePreview(self):
        self.mTempRubberBand.hide()
        if not self.mPoints or self.mLastPoint is None: return
        points = self.mPoints + [self.mLastPoint]
        if len(points) != self.pointCount: return
        curve = self.shapeCurve(points)
        if curve is None or curve.isEmpty(): return
        self.prepareCurve(curve, self.mLastPoint)
        self.mTempRubberBand.setToGeometry(QgsGeometry(curve), None)
        self.mTempRubberBand.show()

    def cadCanvasMoveEvent(self, event):
        self.mLastPoint = self.mParentTool.mapPoint(event)
        self.updatePreview()

    def cadCanvasReleaseEvent(self, event):
        if not self.mManager.parentAvailable(self.mParentTool):
            self.clean()
            self.mManager.mApp.mMessageBar.pushWarning(QCoreApplication.translate('MainWindow', 'Digitize Shape'), '目标图层或捕获工具已不可用')
            return
        point = self.mParentTool.mapPoint(event)
        if event.button() == Qt.LeftButton:
            if len(self.mPoints) < self.pointCount - 1: self.mPoints.append(point)
            self.mLastPoint = point
            self.updatePreview()
        elif event.button() == Qt.RightButton:
            if len(self.mPoints) != self.pointCount - 1:
                self.clean()
                return
            curve = self.shapeCurve(self.mPoints + [point])
            if curve is None or curve.isEmpty():
                self.mManager.mApp.mMessageBar.pushWarning(QCoreApplication.translate('MainWindow', 'Digitize Shape'), '无法构造形状，请调整位置（避免重合点或共线点）')
                return
            if curve.length() <= 0: return
            self.mManager.finishShape(self, curve, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clean()
            self.cadDockWidget().clearPoints()
            event.ignore()
        elif event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            if self.mPoints: self.mPoints.pop()
            self.updatePreview()
            event.ignore()
        else: super().keyPressEvent(event)

    def clean(self):
        self.mPoints.clear()
        self.mLastPoint = None
        self.mTempRubberBand.reset(Qgis.GeometryType.Line)
        self.mTempRubberBand.hide()

    def deactivate(self):
        self.clean()
        if self.mNumberSidesSpinBox and not sip.isdeleted(self.mNumberSidesSpinBox):
            self.mNumberSidesSpinBox.deleteLater()
        self.mNumberSidesSpinBox = None
        super().deactivate()

    def dispose(self):
        self.clean()
        if not sip.isdeleted(self.mTempRubberBand):
            self.canvas().scene().removeItem(self.mTempRubberBand)
            sip.delete(self.mTempRubberBand)
