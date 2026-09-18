"""Counterpart of options/qgsfontoptions.cpp, using its original form.

The page was missing from the port: it manages font family replacements, the
fonts registered from user files, and whether QGIS may download missing fonts.
"""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidgetItem, QAbstractItemView, QHeaderView
from qgis.core import QgsApplication, QgsSettings
from qgis.gui import QgsOptionsPageWidget

ROOT = Path(__file__).resolve().parents[2]
# QgsFontManager::settingsDownloadMissingFonts lives on the "fonts" tree node.
DOWNLOAD_KEY = 'fonts/downloadMissingFonts'


class QgsFontOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgsfontoptionswidgetbase.ui'), self)
        self.setObjectName('mOptionsPageFonts')
        manager = QgsApplication.fontManager()

        self.mTableReplacements.setHorizontalHeaderLabels(['字体族', '替换字体族'])
        self.mTableReplacements.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mTableUserFonts.setHorizontalHeaderLabels(['文件', '字体族'])
        self.mTableUserFonts.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        replacements = manager.fontFamilyReplacements()
        self.mTableReplacements.setRowCount(len(replacements))
        for row, (original, replacement) in enumerate(replacements.items()):
            self.mTableReplacements.setItem(row, 0, QTableWidgetItem(original))
            self.mTableReplacements.setItem(row, 1, QTableWidgetItem(replacement))
        self.mButtonAddReplacement.clicked.connect(self.addReplacement)
        self.mButtonRemoveReplacement.clicked.connect(
            lambda: self.removeSelectedRows(self.mTableReplacements))

        self.mCheckBoxDownloadFonts.setChecked(
            QgsSettings().value(DOWNLOAD_KEY, True, type=bool))

        userFonts = manager.userFontToFamilyMap()
        self.mTableUserFonts.setRowCount(len(userFonts))
        self.mTableUserFonts.setSelectionBehavior(QAbstractItemView.SelectRows)
        for row, (filePath, families) in enumerate(userFonts.items()):
            item = QTableWidgetItem(str(Path(filePath)))
            # The file name is not editable; the removal is driven by Qt.UserRole,
            # which keeps the original path even when it is displayed natively.
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setData(Qt.UserRole, filePath)
            self.mTableUserFonts.setItem(row, 0, item)
            families = QTableWidgetItem('、'.join(families))
            families.setFlags(families.flags() & ~Qt.ItemIsEditable)
            self.mTableUserFonts.setItem(row, 1, families)
        self.mButtonRemoveUserFont.clicked.connect(
            lambda: self.removeSelectedRows(self.mTableUserFonts))

    @staticmethod
    def removeSelectedRows(table):
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()}, reverse=True)
        for row in rows: table.removeRow(row)

    def addReplacement(self):
        self.mTableReplacements.setRowCount(self.mTableReplacements.rowCount() + 1)
        self.mTableReplacements.setFocus()
        self.mTableReplacements.setCurrentCell(self.mTableReplacements.rowCount() - 1, 0)

    def apply(self):
        manager = QgsApplication.fontManager()
        replacements = {}
        for row in range(self.mTableReplacements.rowCount()):
            original = (self.mTableReplacements.item(row, 0).text() if self.mTableReplacements.item(row, 0) else '').strip()
            replacement = (self.mTableReplacements.item(row, 1).text() if self.mTableReplacements.item(row, 1) else '').strip()
            if original and replacement: replacements[original] = replacement
        manager.setFontFamilyReplacements(replacements)

        QgsSettings().setValue(DOWNLOAD_KEY, self.mCheckBoxDownloadFonts.isChecked())

        # Any user font whose row was removed is unregistered from the manager.
        remaining = set()
        for row in range(self.mTableUserFonts.rowCount()):
            item = self.mTableUserFonts.item(row, 0)
            if item is not None and item.data(Qt.UserRole):
                remaining.add(item.data(Qt.UserRole))
        for filePath in QgsApplication.fontManager().userFontToFamilyMap():
            if filePath not in remaining:
                QgsApplication.fontManager().removeUserFont(filePath)
