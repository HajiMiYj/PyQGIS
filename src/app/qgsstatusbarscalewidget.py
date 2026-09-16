"""Counterpart of src/app/qgsstatusbarscalewidget.cpp."""
from qgis.PyQt.QtCore import Qt, QLocale
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel
from qgis.core import QgsProject
from qgis.gui import QgsScaleComboBox


class QgsStatusBarScaleWidget(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.mMapCanvas = canvas
        self.mLabel = QLabel('比例尺', self)
        self.mLabel.setObjectName('mScaleLabel')
        self.mLabel.setMargin(3)
        self.mLabel.setAlignment(Qt.AlignCenter)
        self.mLabel.setMinimumWidth(10)
        self.mLabel.setToolTip('当前地图比例尺')
        self.mScale = QgsScaleComboBox(self)
        self.mScale.setObjectName('mScaleEdit')
        self.mScale.setToolTip('当前地图比例尺')
        self.mScale.setMinimumWidth(10)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.mLabel)
        layout.addWidget(self.mScale)
        self.mScale.scaleChanged.connect(self.userScale)
        canvas.scaleChanged.connect(self.setScale)
        canvas.scaleLockChanged.connect(self.setLocked)
        QgsProject.instance().viewSettings().mapScalesChanged.connect(self.updateScales)
        self.updateScales()
        self.setScale(canvas.scale())
        self.setLocked(canvas.scaleLocked())

    def setScale(self, scale):
        self.mScale.blockSignals(True)
        self.mScale.setScale(scale)
        self.mScale.blockSignals(False)
    def setLocked(self, locked): self.mScale.setDisabled(locked)
    def isLocked(self): return not self.mScale.isEnabled()
    def userScale(self): self.mMapCanvas.zoomScale(self.mScale.scale())
    def updateScales(self):
        settings = QgsProject.instance().viewSettings()
        if settings.useProjectScales(): self.mScale.updateScales(['1:' + QLocale().toString(scale, 'f', 0) for scale in settings.mapScales()])
        else: self.mScale.updateScales()
