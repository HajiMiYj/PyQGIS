"""Counterpart of options/qgsadvancedoptions.cpp, using its original form.

The page was missing from the port entirely. Native offers two editors: the new
QgsSettingsTreeWidget and the legacy QgsSettingsTreeWidgetOld. Only the new tree
is exposed to PyQGIS, so that is the editor created here; the stored
"use-new-widget" preference is still read and written so it round-trips with
native exactly as before.
"""
from pathlib import Path
from qgis.PyQt import uic
from qgis.core import QgsSettings
from qgis.gui import QgsOptionsPageWidget, QgsSettingsTreeWidget

ROOT = Path(__file__).resolve().parents[2]
# QgsAdvancedSettingsWidget::settingsUseNewTreeWidget / settingsShowWarning use
# the app tree's "settings" node.
USE_NEW_WIDGET = 'app/settings/use-new-widget'
SHOW_WARNING = 'app/settings/show-warning'


class QgsAdvancedSettingsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgsadvancedsettingswidget.ui'), self)
        self.setObjectName('mOptionsPageAdvanced')
        settings = QgsSettings()
        useNew = settings.value(USE_NEW_WIDGET, True, type=bool)
        showWarning = settings.value(SHOW_WARNING, True, type=bool)
        self.mTreeWidget = None
        self.mUseNewSettingsTree.setChecked(useNew)
        self.layout().setContentsMargins(0, 0, 0, 0)
        if not showWarning:
            self.mAdvancedSettingsWarning.hide()
            self.createSettingsTreeWidget()
        else:
            self.createSettingsTreeWidget(hide=True)
            self.mAdvancedSettingsEnableButton.clicked.connect(self.enableTree)

    def createSettingsTreeWidget(self, hide=False):
        # QgsSettingsTreeWidgetOld is not exported to PyQGIS, so the legacy editor
        # cannot be offered; the new tree is created in both cases.
        self.mTreeWidget = QgsSettingsTreeWidget(self)
        self.mGroupBox.layout().addWidget(self.mTreeWidget)
        if hide: self.mTreeWidget.hide()

    def enableTree(self):
        QgsSettings().setValue(USE_NEW_WIDGET, self.mUseNewSettingsTree.isChecked())
        self.mAdvancedSettingsWarning.hide()
        self.mTreeWidget.show()

    def apply(self):
        # The new settings tree performs its changes on apply, like native.
        if self.mTreeWidget is not None: self.mTreeWidget.applyChanges()
        QgsSettings().setValue(USE_NEW_WIDGET, self.mUseNewSettingsTree.isChecked())
