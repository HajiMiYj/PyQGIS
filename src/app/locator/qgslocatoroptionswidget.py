"""Locator options; the SIP-unbound prefix setter remains read-only."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem, QPushButton
from qgis.core import QgsSettings


class QgsLocatorOptionsWidget(QTableWidget):
    def __init__(self, locator, parent=None):
        super().__init__(parent)
        self.mLocatorWidget = locator
        self.mFilters = [f for f in locator.locator().filters() if not f.name().startswith('__')]
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(['过滤器', '启用', '不使用前缀', '前缀', '配置'])
        self.setRowCount(len(self.mFilters))
        for row, filter in enumerate(self.mFilters):
            for col, value in enumerate((filter.displayName(), filter.enabled(), filter.useWithoutPrefix(), filter.activePrefix())):
                item = QTableWidgetItem(str(value) if col in (0, 3) else '')
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if col in (1, 2):
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if value else Qt.Unchecked)
                self.setItem(row, col, item)
            if filter.hasConfigWidget():
                button = QPushButton('配置', self)
                button.clicked.connect(lambda checked=False, f=filter: f.openConfigWidget(self))
                self.setCellWidget(row, 4, button)
        self.resizeColumnsToContents()
    def commitChanges(self):
        self.mLocatorWidget.locator().cancel()
        # QgsLocator::settingsLocatorFilterEnabled/Default are QgsSettingsEntry
        # class attributes that are not exposed to Python; they live under the
        # "locator-filters" named list node (src/core/locator/qgslocator.h).
        settings = QgsSettings()
        for row, filter in enumerate(self.mFilters):
            enabled, default = [self.item(row, col).checkState() == Qt.Checked for col in (1, 2)]
            settings.setValue('locator-filters/' + filter.name() + '/enabled', enabled)
            settings.setValue('locator-filters/' + filter.name() + '/default', default)
            filter.setEnabled(enabled)
            filter.setUseWithoutPrefix(default)
        self.mLocatorWidget.invalidateResults()
