"""Raster attribute table dialogs corresponding to src/gui/raster
qgsloadrasterattributetabledialog.cpp and qgscreaterasterattributetabledialog.cpp.

The upstream dialogs are GUI_EXPORT but not exposed to PyQGIS, so they are
rebuilt here against the bound QgsRasterAttributeTable / provider APIs.
"""
from qgis.PyQt.QtCore import QFile
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QCheckBox, QRadioButton, QButtonGroup,
    QDialogButtonBox, QMessageBox, QLabel,
)
from qgis.core import Qgis, QgsRasterAttributeTable, QgsRasterDataProvider
from qgis.gui import QgsRasterBandComboBox, QgsFileWidget


class QgsLoadRasterAttributeTableDialog(QDialog):
    def __init__(self, rasterLayer, parent=None):
        super().__init__(parent)
        self.mRasterLayer = rasterLayer
        self.mMessageBar = None
        self.setWindowTitle('从 VAT.DBF 加载栅格属性表')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mRasterBand = QgsRasterBandComboBox()
        self.mRasterBand.setLayer(rasterLayer)
        form.addRow('栅格波段', self.mRasterBand)
        self.mDbfPathWidget = QgsFileWidget()
        self.mDbfPathWidget.setFilter('VAT DBF 文件 (*.vat.dbf)')
        form.addRow('VAT.DBF 文件', self.mDbfPathWidget)
        layout.addLayout(form)
        self.mOpenRat = QCheckBox('完成后打开栅格属性表')
        self.mOpenRat.setChecked(True)
        layout.addWidget(self.mOpenRat)
        self.mButtonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.mButtonBox.accepted.connect(self.accept)
        self.mButtonBox.rejected.connect(self.reject)
        layout.addWidget(self.mButtonBox)
        self.mDbfPathWidget.fileChanged.connect(lambda *_args: self.updateButtons())
        self.updateButtons()

    def setMessageBar(self, bar): self.mMessageBar = bar
    def filePath(self): return self.mDbfPathWidget.filePath()
    def rasterBand(self): return self.mRasterBand.currentBand()
    def openWhenDone(self): return self.mOpenRat.isChecked()

    def updateButtons(self):
        path = self.mDbfPathWidget.filePath()
        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(bool(path) and QFile.exists(path))

    def notify(self, title, message, level=Qgis.Info):
        if self.mMessageBar:
            self.mMessageBar.pushMessage(title, message, level=level)
            return
        handlers = {Qgis.Critical: QMessageBox.critical, Qgis.Warning: QMessageBox.warning,
                    Qgis.Info: QMessageBox.information, Qgis.Success: QMessageBox.information}
        handlers.get(level, QMessageBox.information)(self, title, message)

    def accept(self):
        if self.rasterBand() < 1:
            self.notify('无效栅格波段', f'所选栅格波段 {self.rasterBand()} 无效。', Qgis.Critical)
            return
        rat = QgsRasterAttributeTable()
        if not rat.readFromFile(self.filePath()):
            self.notify('加载栅格属性表失败', '无法加载栅格属性表。', Qgis.Critical)
            return
        if not rat.isValid():
            answer = QMessageBox.warning(self, '无效栅格属性表',
                                         '该栅格属性表无效。仍然加载吗？',
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                return
            if answer != QMessageBox.Yes:
                return
        existing = self.mRasterLayer.attributeTable(self.rasterBand())
        if existing and existing.filePath():
            answer = QMessageBox.warning(self, '确认替换属性表',
                                         f'栅格波段 {self.rasterBand()} 已有关联属性表（来自 {existing.filePath()}）。确定替换吗？',
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                return
            if answer != QMessageBox.Yes:
                return
        self.mRasterLayer.dataProvider().setAttributeTable(self.rasterBand(), rat)
        self.notify('栅格属性表已加载', '新栅格属性表加载成功。', Qgis.Success)
        super().accept()


class QgsCreateRasterAttributeTableDialog(QDialog):
    def __init__(self, rasterLayer, parent=None):
        super().__init__(parent)
        self.mRasterLayer = rasterLayer
        self.mMessageBar = None
        self.setWindowTitle('创建栅格属性表')
        layout = QVBoxLayout(self)
        nativeSupported = bool(rasterLayer.dataProvider().providerCapabilities()
                               & QgsRasterDataProvider.NativeRasterAttributeTable)
        self.mNativeRadioButton = QRadioButton('以本机格式存储')
        self.mDbfRadioButton = QRadioButton('保存到 DBF 文件')
        self.mNativeRadioButton.setEnabled(nativeSupported)
        self.mDbfRadioButton.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.mNativeRadioButton)
        group.addButton(self.mDbfRadioButton)
        layout.addWidget(self.mNativeRadioButton)
        layout.addWidget(self.mDbfRadioButton)
        form = QFormLayout()
        self.mDbfPathWidget = QgsFileWidget()
        self.mDbfPathWidget.setFilter('VAT DBF 文件 (*.vat.dbf)')
        providerUri = rasterLayer.dataProvider().dataSourceUri()
        if nativeSupported and QFile.exists(providerUri):
            self.mDbfPathWidget.setFilePath(providerUri + '.vat.dbf')
        form.addRow('DBF 文件路径', self.mDbfPathWidget)
        layout.addLayout(form)
        self.mOpenRat = QCheckBox('完成后打开栅格属性表')
        self.mOpenRat.setChecked(True)
        layout.addWidget(self.mOpenRat)
        info = QLabel('从当前 Paletted / SingleBandPseudoColor 渲染器创建栅格属性表。')
        info.setWordWrap(True)
        layout.addWidget(info)
        self.mButtonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.mButtonBox.accepted.connect(self.accept)
        self.mButtonBox.rejected.connect(self.reject)
        layout.addWidget(self.mButtonBox)
        self.mNativeRadioButton.toggled.connect(self.updateButtons)
        self.updateButtons()

    def setMessageBar(self, bar): self.mMessageBar = bar
    def filePath(self): return self.mDbfPathWidget.filePath()
    def saveToFile(self): return self.mDbfRadioButton.isChecked()
    def openWhenDone(self): return self.mOpenRat.isChecked()

    def updateButtons(self):
        self.mDbfPathWidget.setEnabled(self.mDbfRadioButton.isChecked())

    def notify(self, title, message, level=Qgis.Info):
        if self.mMessageBar:
            self.mMessageBar.pushMessage(title, message, level=level)
            return
        handlers = {Qgis.Critical: QMessageBox.critical, Qgis.Warning: QMessageBox.warning,
                    Qgis.Info: QMessageBox.information, Qgis.Success: QMessageBox.information}
        handlers.get(level, QMessageBox.information)(self, title, message)

    def accept(self):
        renderer = self.mRasterLayer.renderer()
        bandNumber = renderer.band() if renderer is not None and hasattr(renderer, 'band') else 1
        rat = QgsRasterAttributeTable.createFromRaster(self.mRasterLayer)
        if rat is None:
            self.notify('创建栅格属性表失败', '无法创建栅格属性表（渲染器需为 Paletted 或 SingleBandPseudoColor）。', Qgis.Critical)
            return
        self.mRasterLayer.dataProvider().setAttributeTable(bandNumber, rat)
        success = False
        if self.saveToFile():
            destinationPath = self.filePath()
            if not QFile.exists(destinationPath) or QMessageBox.warning(
                    self, '确认覆盖', f'确定覆盖 {destinationPath} 处的现有属性表吗？',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                success = rat.writeToFile(destinationPath)
                if not success:
                    self.notify('保存栅格属性表失败', '无法写入属性表文件。', Qgis.Critical)
                    self.mRasterLayer.dataProvider().setAttributeTable(bandNumber, None)
        else:
            success = self.mRasterLayer.dataProvider().writeNativeAttributeTable()
            if not success:
                self.notify('保存栅格属性表失败', '无法写入本机属性表。', Qgis.Critical)
                self.mRasterLayer.dataProvider().setAttributeTable(bandNumber, None)
        if success:
            self.notify('栅格属性表已保存', '新栅格属性表创建成功。', Qgis.Success)
        super().accept()
