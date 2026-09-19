"""Two-point profile measurement, following the upstream plot tool."""
import math
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, Qt, QPointF, QLineF, pyqtSignal
from qgis.PyQt.QtGui import QPen, QColor
from qgis.PyQt.QtWidgets import QDialog, QFormLayout, QLabel, QGraphicsLineItem
from qgis.core import Qgis, QgsProject, QgsSettings, QgsUnitTypes
from qgis.gui import QgsPlotTool


class QgsProfileMeasureResultsDialog(QDialog):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool)
        self.setObjectName('QgsProfileMeasureResultsDialog')
        self.setWindowTitle(QCoreApplication.translate('QgsProfileMeasureResultsDialog', 'Profile Distance'))
        form = QFormLayout(self)
        self.mTotalLabel, self.mDistanceLabel, self.mElevationLabel = QLabel(), QLabel(), QLabel()
        for title, label in [('总长度', self.mTotalLabel), ('Δ 距离', self.mDistanceLabel), ('Δ 高程', self.mElevationLabel)]:
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            form.addRow(title, label)

    def setMeasures(self, total, distance, elevation, crs):
        self.mTotalLabel.setText(f'{total:.6g}')
        self.mElevationLabel.setText(f'{elevation:.6g}')
        unit, projectUnit = crs.mapUnits(), QgsProject.instance().distanceUnits()
        if QgsUnitTypes.unitType(unit) == Qgis.DistanceUnitType.Standard and QgsUnitTypes.unitType(projectUnit) == Qgis.DistanceUnitType.Standard:
            distance *= QgsUnitTypes.fromUnitToUnitFactor(unit, projectUnit)
            unit = projectUnit
        settings = QgsSettings()
        self.mDistanceLabel.setText(QgsUnitTypes.formatDistance(distance,
            settings.value('qgis/measure/decimalplaces', 3, type=int), unit,
            settings.value('qgis/measure/keepbaseunit', True, type=bool)))

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


class QgsElevationProfileToolMeasure(QgsPlotTool):
    measureChanged = pyqtSignal(float, float, float)
    cleared = pyqtSignal()

    def __init__(self, canvas):
        super().__init__(canvas, '剖面测量')
        self.mStartPoint = self.mEndPoint = None
        self.mMeasureInProgress = False
        self.mRubberBand = QGraphicsLineItem()
        self.mRubberBand.setZValue(1000)
        pen = QPen(QColor(222, 155, 67, 180), 2)
        pen.setCosmetic(True)
        self.mRubberBand.setPen(pen)
        self.mRubberBand.hide()
        canvas.scene().addItem(self.mRubberBand)
        self.mDialog = QgsProfileMeasureResultsDialog(canvas.window())
        self.mDialog.closed.connect(self.clear)
        canvas.plotAreaChanged.connect(self.updateRubberBand)
        self.setCursor(Qt.CrossCursor)

    def pointForEvent(self, event):
        point, area = event.snappedPoint().toQPointF(), self.canvas().plotArea()
        constrained = QPointF(max(area.left(), min(area.right(), point.x())), max(area.top(), min(area.bottom(), point.y())))
        return self.canvas().canvasPointToPlotPoint(constrained)

    def plotPressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        if not self.mMeasureInProgress and not self.canvas().plotArea().contains(QPointF(event.pos())): return
        self.mEndPoint = self.pointForEvent(event)
        if not self.mMeasureInProgress: self.mStartPoint = self.mEndPoint
        self.mMeasureInProgress = not self.mMeasureInProgress
        self.updateMeasures()

    def plotMoveEvent(self, event):
        if self.mMeasureInProgress:
            self.mEndPoint = self.pointForEvent(event)
            self.updateMeasures()

    def plotReleaseEvent(self, event):
        if event.button() == Qt.RightButton: self.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape: self.clear()
        else: super().keyPressEvent(event)

    def updateMeasures(self):
        distance = self.mEndPoint.distance() - self.mStartPoint.distance()
        elevation = self.mEndPoint.elevation() - self.mStartPoint.elevation()
        total = math.hypot(distance, elevation)
        self.mDialog.setMeasures(total, distance, elevation, self.canvas().crs())
        self.mDialog.show()
        self.measureChanged.emit(total, distance, elevation)
        self.updateRubberBand()

    def updateRubberBand(self, *args):
        if self.mStartPoint is None or self.mEndPoint is None: return
        a, b = (self.canvas().plotPointToCanvasPoint(p) for p in (self.mStartPoint, self.mEndPoint))
        line = self.clipLine(QLineF(a.toQPointF(), b.toQPointF()), self.canvas().plotArea())
        if line is None:
            self.mRubberBand.hide()
            return
        self.mRubberBand.setLine(line)
        self.mRubberBand.show()

    @staticmethod
    def clipLine(line, bounds):
        """Clip the display only; preserve the measured endpoints when zooming."""
        start, end = 0., 1.
        for direction, distance in ((-line.dx(), line.x1() - bounds.left()),
                                    (line.dx(), bounds.right() - line.x1()),
                                    (-line.dy(), line.y1() - bounds.top()),
                                    (line.dy(), bounds.bottom() - line.y1())):
            if direction == 0:
                if distance < 0: return None
                continue
            ratio = distance / direction
            if direction < 0: start = max(start, ratio)
            else: end = min(end, ratio)
            if start > end: return None
        return QLineF(line.pointAt(start), line.pointAt(end))

    def clear(self):
        self.mMeasureInProgress = False
        self.mStartPoint = self.mEndPoint = None
        self.mRubberBand.hide()
        self.mDialog.hide()
        self.cleared.emit()

    def deactivate(self):
        self.clear()
        super().deactivate()

    def dispose(self):
        self.canvas().plotAreaChanged.disconnect(self.updateRubberBand)
        self.clear()
        self.canvas().scene().removeItem(self.mRubberBand)
        sip.delete(self.mRubberBand)
        sip.delete(self.mDialog)
