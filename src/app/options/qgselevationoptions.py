"""Counterpart of options/qgselevationoptions.cpp, using its original form.

The page was missing from the port. The colour is consumed by the native
QgsElevationProfileCanvas, which the port already uses, so setting it here takes
effect in the elevation profile dock.
"""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsSettings
from qgis.gui import QgsOptionsPageWidget

ROOT = Path(__file__).resolve().parents[2]
# QgsElevationProfileWidget::settingBackgroundColor lives on the
# "elevation-profile" settings tree node.
KEY = 'elevation-profile/background-color'


class QgsElevationOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgselevationoptionswidgetbase.ui'), self)
        self.setObjectName('mOptionsPageElevation')
        self.mButtonBackgroundColor.setShowNull(True, '使用默认值')
        self.mButtonBackgroundColor.setColorDialogTitle('图表背景颜色')
        # An unset/empty value means "use the default chart colour".
        stored = QgsSettings().value(KEY, '', type=str)
        color = QColor(stored) if stored else QColor()
        if color.isValid():
            self.mButtonBackgroundColor.setColor(color)
        else:
            self.mButtonBackgroundColor.setToNull()

    def apply(self):
        settings = QgsSettings()
        if self.mButtonBackgroundColor.isNull():
            settings.setValue(KEY, '')
        else:
            settings.setValue(KEY, self.mButtonBackgroundColor.color().name(QColor.HexArgb))
