from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton
from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsDoubleSpinBox


class QgsStatusBarMagnifierWidget(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        self.mLabel = QLabel('放大镜', self)
        self.mLabel.setMargin(3)
        self.mLabel.setMinimumWidth(10)
        self.mLabel.setAlignment(Qt.AlignCenter)
        self.mSpinBox = QgsDoubleSpinBox(self)
        self.mMagnifierSpinBox = self.mSpinBox
        self.mMagnifierSpinBox.setRange(10, 1600)
        self.mMagnifierSpinBox.setMaximumWidth(120)
        self.mMagnifierSpinBox.setSingleStep(50)
        self.mMagnifierSpinBox.setClearValue(100 * QgsSettings().value('qgis/magnifier_factor_default', 1.0, type=float))
        self.mMagnifierSpinBox.setDecimals(0)
        self.mMagnifierSpinBox.setSuffix('%')
        self.mMagnifierSpinBox.setValue(canvas.magnificationFactor() * 100)
        self.mMagnifierSpinBox.setKeyboardTracking(False)
        self.mMagnifierSpinBox.setToolTip('放大镜：调整符号及标签显示倍率')
        self.mLockButton = QToolButton()
        self.mLockButton.setIcon(QgsApplication.getThemeIcon('/lockedGray.svg'))
        self.mLockButton.setAutoRaise(True)
        self.mLockButton.setCheckable(True)
        self.mLockButton.setToolTip('锁定比例尺，使用放大镜缩放地图')
        self.mLockButton.setChecked(canvas.scaleLocked())
        self.mMagnifierSpinBox.valueChanged.connect(lambda n: canvas.setMagnificationFactor(n / 100))
        self.mLockButton.toggled.connect(canvas.setScaleLocked)
        canvas.magnificationChanged.connect(self.updateMagnification)
        canvas.scaleLockChanged.connect(self.mLockButton.setChecked)
        box.addWidget(self.mLockButton)
        box.addWidget(self.mLabel)
        box.addWidget(self.mMagnifierSpinBox)

    def setDefaultFactor(self, factor): self.mSpinBox.setClearValue(100 * factor)

    def updateMagnification(self, factor):
        self.mMagnifierSpinBox.blockSignals(True)
        self.mMagnifierSpinBox.setValue(factor * 100)
        self.mMagnifierSpinBox.blockSignals(False)
