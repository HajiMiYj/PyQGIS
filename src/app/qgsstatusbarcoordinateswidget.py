import math
import re
from qgis.PyQt.QtCore import Qt, QLocale, QElapsedTimer

from qgis.core import (Qgis, QgsPointXY, QgsApplication, QgsProject, QgsCoordinateTransform,
                       QgsCoordinateReferenceSystemUtils, QgsCoordinateFormatter, QgsNumericFormatContext,
                       QgsGeographicCoordinateNumericFormat)
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QToolButton, QLabel, QSizePolicy

class QgsStatusBarCoordinatesWidget(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.mMapCanvas = canvas
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        self.mLastCoordinate = None
        self.mMousePrecisionDecimalPlaces = 0
        self.mLastSizeChangeTimer = QElapsedTimer()
        self.mLabel = QLabel('坐标', self)
        self.mLabel.setObjectName('mCoordsLabel')
        self.mLabel.setMargin(3)
        self.mLabel.setMinimumWidth(10)
        self.mLabel.setAlignment(Qt.AlignCenter)
        self.mToggleExtentsViewButton = QToolButton()
        self.mToggleExtentsViewButton.setCheckable(True)
        self.mToggleExtentsViewButton.setIcon(QgsApplication.getThemeIcon('/tracking.svg'))
        self.mToggleExtentsViewButton.setAutoRaise(True)
        self.mToggleExtentsViewButton.setToolTip('切换坐标/范围；输入坐标后按回车定位')
        self.mLineEdit = QLineEdit()
        self.mLineEdit.setAlignment(Qt.AlignCenter)
        self.mLineEdit.setMinimumWidth(10)
        box.addStretch()
        box.addWidget(self.mLabel)
        box.addWidget(self.mLineEdit)
        box.addWidget(self.mToggleExtentsViewButton)
        box.setAlignment(Qt.AlignRight)
        self.mToggleExtentsViewButton.toggled.connect(self.extentsViewToggled)
        canvas.extentsChanged.connect(self.coordinateDisplaySettingsChanged)
        canvas.destinationCrsChanged.connect(self.coordinateDisplaySettingsChanged)
        canvas.xyCoordinates.connect(self.showCoordinates)
        self.mLineEdit.returnPressed.connect(self.validateCoordinates)
        display = QgsProject.instance().displaySettings()
        for signal in (display.coordinateCrsChanged, display.geographicCoordinateFormatChanged,
                       display.coordinateTypeChanged, display.coordinateAxisOrderChanged):
            signal.connect(self.coordinateDisplaySettingsChanged)
        QgsProject.instance().readProject.connect(self.coordinateDisplaySettingsChanged)
        self.coordinateDisplaySettingsChanged()

    def displayCrs(self):
        crs = QgsProject.instance().displaySettings().coordinateCrs()
        return crs if crs.isValid() else self.mMapCanvas.mapSettings().destinationCrs()

    def coordinateOrder(self, crs):
        order = QgsProject.instance().displaySettings().coordinateAxisOrder()
        return QgsCoordinateReferenceSystemUtils.defaultCoordinateOrderForCrs(crs) if order == Qgis.CoordinateOrder.Default else order

    def setMouseCoordinatesPrecision(self, precision):
        self.mMousePrecisionDecimalPlaces = max(0, int(precision))

    def coordinateDisplaySettingsChanged(self, *unused):
        project = QgsProject.instance()
        precision = project.readNumEntry('PositionPrecision', '/DecimalPlaces', 6)[0]
        if project.readBoolEntry('PositionPrecision', '/Automatic', True)[0]:
            if self.mMapCanvas.mapSettings().destinationCrs().isGeographic() or not self.displayCrs().isGeographic():
                units = self.mMapCanvas.mapUnitsPerPixel()
                precision = math.ceil(-math.log10(units)) if units > 0 else 0
            else:
                angle = project.displaySettings().geographicCoordinateFormat().angleFormat()
                precision = 4 if angle == QgsGeographicCoordinateNumericFormat.AngleFormat.DecimalDegrees else 2
        self.setMouseCoordinatesPrecision(precision)
        labels = ('经度', '纬度') if self.displayCrs().isGeographic() else ('东坐标', '北坐标')
        if self.coordinateOrder(self.displayCrs()) == Qgis.CoordinateOrder.YX: labels = labels[::-1]
        self.mLineEdit.setToolTip('当前地图范围' if self.mToggleExtentsViewButton.isChecked() else
                                  '当前地图坐标（' + '，'.join(labels) + '）；输入坐标后按回车定位')
        self.showExtent()
        if self.mLastCoordinate is not None: self.showCoordinates(self.mLastCoordinate)

    def formatCoordinate(self, point):
        project, crs = QgsProject.instance(), self.displayCrs()
        if not crs.isValid(): return ''
        source = self.mMapCanvas.mapSettings().destinationCrs()
        try:
            if source != crs: point = QgsCoordinateTransform(source, crs, project).transform(point)
        except Exception: return ''
        precision = self.mMousePrecisionDecimalPlaces
        if crs.isGeographic():
            formatter = project.displaySettings().geographicCoordinateFormat().clone()
            formatter.setNumberDecimalPlaces(precision)
            context = QgsNumericFormatContext()
            context.setInterpretation(QgsNumericFormatContext.Interpretation.Longitude)
            x = formatter.formatDouble(point.x(), context)
            context.setInterpretation(QgsNumericFormatContext.Interpretation.Latitude)
            y = formatter.formatDouble(point.y(), context)
        else:
            x = QgsCoordinateFormatter.formatX(point.x(), QgsCoordinateFormatter.FormatPair, precision)
            y = QgsCoordinateFormatter.formatY(point.y(), QgsCoordinateFormatter.FormatPair, precision)
        if self.coordinateOrder(crs) == Qgis.CoordinateOrder.YX: x, y = y, x
        return x + QgsCoordinateFormatter.separator() + ' ' + y

    def ensureCoordinatesVisible(self):
        metric = self.mLineEdit.fontMetrics()
        width = max(metric.horizontalAdvance(self.mLineEdit.text())+16, metric.horizontalAdvance('O')*4)
        current = self.mLineEdit.minimumWidth()
        if (not self.mLastSizeChangeTimer.isValid() or width > current or
                (current-width > metric.horizontalAdvance('O') and self.mLastSizeChangeTimer.hasExpired(2000))):
            self.mLineEdit.setFixedWidth(width)
            self.mLastSizeChangeTimer.start()

    def showCoordinates(self, point):
        self.mLastCoordinate = point
        if not self.mToggleExtentsViewButton.isChecked() and not self.mLineEdit.hasFocus():
            self.mLineEdit.setText(self.formatCoordinate(point))
            self.ensureCoordinatesVisible()
    showMouseCoordinates = showCoordinates
    def showExtent(self, *args):
        if self.mToggleExtentsViewButton.isChecked():
            extent = self.mMapCanvas.extent()
            self.mLineEdit.setText(self.formatCoordinate(QgsPointXY(extent.xMinimum(), extent.yMinimum())) + ' : ' +
                                   self.formatCoordinate(QgsPointXY(extent.xMaximum(), extent.yMaximum())))
            self.ensureCoordinatesVisible()
    def extentsViewToggled(self, checked):
        self.mLabel.setText('范围' if checked else '坐标')
        self.mToggleExtentsViewButton.setIcon(QgsApplication.getThemeIcon('/extents.svg' if checked else '/tracking.svg'))
        self.mLineEdit.setReadOnly(checked)
        if checked: self.showExtent()
        elif self.mLastCoordinate is not None: self.showCoordinates(self.mLastCoordinate)
        else: self.mLineEdit.clear()
        self.coordinateDisplaySettingsChanged()

    def validateCoordinates(self):
        if self.mLineEdit.isReadOnly(): return
        text = re.sub(r'\s+', ' ', self.mLineEdit.text().replace('°', '').strip())
        values = None
        for parts, localized in ((text.split(','), False), (text.split(' '), False), (text.split(' '), True)):
            if len(parts) != 2: continue
            try:
                if localized:
                    parsed = [QLocale().toDouble(part) for part in parts]
                    if not all(ok for value, ok in parsed): continue
                    values = [value for value, ok in parsed]
                else: values = [float(part) for part in parts]
                if all(math.isfinite(value) for value in values): break
                values = None
            except ValueError: continue
        if values is None: return
        canvasCrs = self.mMapCanvas.mapSettings().destinationCrs()
        # Native input resolves Default against the canvas CRS.
        if self.coordinateOrder(canvasCrs) == Qgis.CoordinateOrder.YX: values.reverse()
        point = QgsPointXY(*values)
        try:
            if self.displayCrs() != canvasCrs:
                point = QgsCoordinateTransform(self.displayCrs(), canvasCrs, QgsProject.instance()).transform(point)
        except Exception: return
        self.mMapCanvas.setCenter(point)
        self.mMapCanvas.refresh()
