import math
import re
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QToolButton, QMessageBox
from qgis.core import QgsPointXY, QgsCoordinateTransform, QgsApplication
from qgis.gui import QgsMapToolEmitPoint


class QgsMapCoordsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/georeferencer/qgsmapcoordsdialogbase.ui'), self)
        self.mWindow = window
        self.mCanvas = window.mApp.mMapCanvas
        self.mPreviousTool = None
        self.mPickTool = QgsMapToolEmitPoint(self.mCanvas)
        self.mPickTool.canvasClicked.connect(self.pointPicked)
        self.mProjectionSelector.setCrs(window.mSettings['crs'])
        self.mMinimizeWindowCheckBox.setChecked(True)
        self.mPointFromCanvasButton = QToolButton(self)
        self.mPointFromCanvasButton.setIcon(QgsApplication.getThemeIcon('/mActionCapturePoint.svg'))
        self.mPointFromCanvasButton.setToolTip('从 QGIS 地图画布拾取坐标')
        self.coordinatesLayout.addWidget(self.mPointFromCanvasButton, 0, 2, 2, 1)
        self.mPointFromCanvasButton.clicked.connect(self.pickFromCanvas)
        self.finished.connect(self.restoreMapTool)
        self.mPoint = None

    @staticmethod
    def coordinate(text):
        text = text.strip().upper()
        negative = text.startswith('-') or text.endswith(('W', 'S'))
        values = [value for value in re.split(r'[\s°\'"′″]+', text.rstrip('NSEW').strip()) if value]
        if not 1 <= len(values) <= 3: raise ValueError('坐标格式无效')
        numbers = [float(value) for value in values]
        if not all(math.isfinite(n) for n in numbers): raise ValueError('坐标必须是有限数值')
        if any(not 0 <= n < 60 for n in numbers[1:]): raise ValueError('分和秒必须在 0 到 60 之间')
        result = abs(numbers[0]) + sum(n / 60**i for i, n in enumerate(numbers[1:], 1))
        return -result if negative else result

    def pickFromCanvas(self):
        self.mPreviousTool = self.mCanvas.mapTool()
        self.mCanvas.setMapTool(self.mPickTool)
        self.hide()
        if self.mMinimizeWindowCheckBox.isChecked(): self.mWindow.hide()
        self.mWindow.mApp.raise_()

    def pointPicked(self, point, button):
        if button != Qt.LeftButton:
            self.restoreMapTool()
        else:
            try:
                crs = self.mProjectionSelector.crs()
                point = QgsCoordinateTransform(self.mCanvas.mapSettings().destinationCrs(), crs, self.mWindow.mApp.mProject).transform(point)
                self.leXCoord.setText(format(point.x(), '.17g'))
                self.leYCoord.setText(format(point.y(), '.17g'))
            except Exception as error: QMessageBox.warning(self, '拾取坐标', str(error))
            self.restoreMapTool()
        self.mWindow.show()
        self.show()
        self.raise_()

    def restoreMapTool(self, *unused):
        if self.mCanvas.mapTool() is self.mPickTool:
            self.mCanvas.setMapTool(self.mPreviousTool or self.mWindow.mApp.mMapTools['pan'])
        self.mPreviousTool = None

    def accept(self):
        try:
            if not self.mProjectionSelector.crs().isValid(): raise ValueError('请选择目标点的 CRS')
            self.mPoint = QgsPointXY(self.coordinate(self.leXCoord.text()), self.coordinate(self.leYCoord.text()))
        except ValueError as error:
            QMessageBox.warning(self, QCoreApplication.translate('QgsStatusBarCoordinatesWidget', 'Coordinate'), str(error)); return
        super().accept()
