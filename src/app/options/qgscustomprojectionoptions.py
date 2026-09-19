"""User CRS editor using the original form and native CRS definition widget."""
from pathlib import Path
from dataclasses import dataclass, replace
import re
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QTreeWidgetItem, QAbstractItemView, QMessageBox, QDialog, QVBoxLayout, QDialogButtonBox
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem
from qgis.gui import QgsOptionsPageWidget, QgsGui


@dataclass
class Definition:
    id: int
    name: str
    definition: str
    format: object


class QgsCustomProjectionOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/qgscustomprojectiondialogbase.ui'), self)
        self.setObjectName('QgsCustomProjectionOptionsWidget')
        if not Path(QgsApplication.qgisUserDatabaseFilePath()).exists():
            result = QgsApplication.createDatabase()
            if not (result[0] if isinstance(result, tuple) else result): raise RuntimeError('无法创建用户坐标参考系数据库')
        self.mRegistry = QgsApplication.coordinateReferenceSystemRegistry()
        self.mDefinitions, self.mExistingCRS, self.mDeletedCRSs = [], {}, set()
        self.mBlockUpdates = False
        self.leNameList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.leNameList.hideColumn(1)
        self.pbnAdd.setIcon(QgsApplication.getThemeIcon('/symbologyAdd.svg'))
        self.pbnRemove.setIcon(QgsApplication.getThemeIcon('/symbologyRemove.svg'))
        self.pbnAdd.clicked.connect(self.pbnAdd_clicked)
        self.pbnRemove.clicked.connect(lambda: self.pbnRemove_clicked())
        self.leNameList.currentItemChanged.connect(self.leNameList_currentItemChanged)
        self.leName.textChanged.connect(self.updateListFromCurrentItem)
        self.mCrsDefinitionWidget.crsChanged.connect(self.updateListFromCurrentItem)
        self.populateList()

    def populateList(self):
        self.mBlockUpdates = True
        try:
            self.leNameList.clear()
            self.mDefinitions.clear()
            self.mExistingCRS.clear()
            self.mDeletedCRSs.clear()
            for details in sorted(self.mRegistry.userCrsList(), key=lambda entry: entry.name.casefold()):
                definition = Definition(details.id, details.name, details.wkt or details.proj,
                    Qgis.CrsDefinitionFormat.Wkt if details.wkt else Qgis.CrsDefinitionFormat.Proj)
                self.mDefinitions.append(definition)
                self.mExistingCRS[details.id] = replace(definition)
                self.appendItem(definition)
        finally: self.mBlockUpdates = False
        if self.leNameList.topLevelItemCount(): self.leNameList.setCurrentItem(self.leNameList.topLevelItem(0))
        else: self.leNameList_currentItemChanged(None, None)

    @staticmethod
    def multiLineWktToSingleLine(value): return re.sub(r'\s*\n\s*', '', value)

    def appendItem(self, definition):
        return QTreeWidgetItem(self.leNameList, [definition.name, str(definition.id) if definition.id else '',
                                               self.multiLineWktToSingleLine(definition.definition)])

    def pbnAdd_clicked(self):
        definition = Definition(0, '新建坐标参考系', '', Qgis.CrsDefinitionFormat.Wkt)
        self.mDefinitions.append(definition)
        item = self.appendItem(definition)
        self.leNameList.setCurrentItem(item)
        self.leName.selectAll()
        self.leName.setFocus()

    def pbnRemove_clicked(self, confirm=True):
        rows = sorted({self.leNameList.indexOfTopLevelItem(item) for item in self.leNameList.selectedItems()}, reverse=True)
        if not rows: return
        if confirm and QMessageBox.question(self, QCoreApplication.translate('QgsCustomProjectionOptionsWidget', 'Delete Projections'), f'删除选中的 {len(rows)} 个坐标参考系？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        self.mBlockUpdates = True
        try:
            for row in rows:
                definition = self.mDefinitions.pop(row)
                if definition.id: self.mDeletedCRSs.add(definition.id)
                self.leNameList.takeTopLevelItem(row)
        finally: self.mBlockUpdates = False
        self.leNameList_currentItemChanged(self.leNameList.currentItem(), None)

    def leNameList_currentItemChanged(self, current, previous):
        if self.mBlockUpdates: return
        self.mBlockUpdates = True
        try:
            self.leName.setEnabled(current is not None)
            self.mCrsDefinitionWidget.setEnabled(current is not None)
            self.pbnRemove.setEnabled(current is not None)
            definition = self.mDefinitions[self.leNameList.indexOfTopLevelItem(current)] if current else None
            self.leName.setText(definition.name if definition else '')
            self.mCrsDefinitionWidget.setFormat(definition.format if definition else Qgis.CrsDefinitionFormat.Wkt)
            self.mCrsDefinitionWidget.setDefinitionString(definition.definition if definition else '')
        finally: self.mBlockUpdates = False

    def updateListFromCurrentItem(self, *args):
        if self.mBlockUpdates: return
        item = self.leNameList.currentItem()
        if item is None: return
        definition = self.mDefinitions[self.leNameList.indexOfTopLevelItem(item)]
        definition.name = self.leName.text()
        definition.format = self.mCrsDefinitionWidget.format()
        definition.definition = self.mCrsDefinitionWidget.definitionString()
        item.setText(0, definition.name)
        item.setText(2, self.multiLineWktToSingleLine(definition.definition))

    @staticmethod
    def crsForDefinition(definition):
        crs = QgsCoordinateReferenceSystem()
        if definition.format == Qgis.CrsDefinitionFormat.Wkt: crs.createFromWkt(definition.definition)
        else: crs.createFromProj(definition.definition)
        return crs

    def isValid(self, showErrors=True):
        self.updateListFromCurrentItem()
        for row, definition in enumerate(self.mDefinitions):
            crs = self.crsForDefinition(definition)
            error = ''
            if not definition.name.strip(): error = '名称不能为空。'
            elif not crs.isValid(): error = f'“{definition.name}”的坐标参考系定义无效。'
            elif crs.authid() and not crs.authid().upper().startswith('USER:'):
                error = f'“{definition.name}”与 {crs.authid()} 等价，不能重复保存；请修改定义，或检查 WKT 中的权威机构 ID。'
            if error:
                self.leNameList.setCurrentItem(self.leNameList.topLevelItem(row))
                if showErrors: QMessageBox.warning(self, QCoreApplication.translate('QgisApp', 'Custom Projections'), error)
                return False
        return True

    def saveCrs(self, crs, name, existingId, newEntry, format):
        if newEntry:
            identifier = self.mRegistry.addUserCrs(crs, name, format)
            return identifier if identifier >= 0 else None
        return existingId if self.mRegistry.updateUserCrs(existingId, crs, name, format) else None

    def apply(self):
        if not self.isValid(): return False
        # Record each successful write immediately: another Apply after a failed
        # registry write must neither duplicate additions nor redo deletions.
        for row, definition in enumerate(self.mDefinitions):
            if self.mExistingCRS.get(definition.id) == definition: continue
            identifier = self.saveCrs(self.crsForDefinition(definition), definition.name, definition.id,
                                     not bool(definition.id), definition.format)
            if identifier is None:
                QMessageBox.warning(self, QCoreApplication.translate('QgisApp', 'Custom Projections'), f'无法保存“{definition.name}”，请检查用户数据库是否可写。')
                return False
            definition.id = identifier
            self.mExistingCRS[identifier] = replace(definition)
            self.leNameList.topLevelItem(row).setText(1, str(identifier))
        for identifier in list(self.mDeletedCRSs):
            if not self.mRegistry.removeUserCrs(identifier):
                QMessageBox.warning(self, QCoreApplication.translate('QgisApp', 'Custom Projections'), f'无法删除 USER:{identifier}。')
                return False
            self.mDeletedCRSs.remove(identifier)
            self.mExistingCRS.pop(identifier, None)
        return True

    def helpKey(self): return 'working_with_projections/working_with_projections'


class QgsCustomProjectionDialog(QDialog):
    """Hosts this action while the application's full Options port is paused."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('QgsCustomProjectionDialog')
        self.setWindowTitle('自定义坐标参考系')
        self.resize(680, 700)
        layout = QVBoxLayout(self)
        self.mWidget = QgsCustomProjectionOptionsWidget(self)
        layout.addWidget(self.mWidget)
        self.mButtonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        layout.addWidget(self.mButtonBox)
        self.mButtonBox.accepted.connect(self.accept)
        self.mButtonBox.rejected.connect(self.reject)
        self.mButtonBox.button(QDialogButtonBox.Apply).clicked.connect(self.mWidget.apply)
        self.mButtonBox.helpRequested.connect(lambda: QDesktopServices.openUrl(QUrl(
            'https://docs.qgis.org/3.34/en/docs/user_manual/working_with_projections/working_with_projections.html#custom-coordinate-reference-system')))
        QgsGui.enableAutoGeometryRestore(self)

    def accept(self):
        if self.mWidget.apply(): super().accept()
