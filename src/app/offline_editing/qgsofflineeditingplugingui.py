"""Port of src/plugins/offline_editing/offline_editing_plugin_gui.cpp."""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QMessageBox, QHeaderView
from qgis.core import QgsProject, QgsSettings, QgsApplication, QgsLayerTree, QgsLayerTreeModel, QgsOfflineEditing
from qgis.gui import QgsGui, QgsHelp

ROOT = Path(__file__).resolve().parents[3]


class QgsSelectLayerTreeModel(QgsLayerTreeModel):
    """Native QgsSelectLayerTreeModel: layer visibility drives the checkbox column."""

    def __init__(self, rootNode, parent=None):
        super().__init__(rootNode, parent)
        self.setFlag(QgsLayerTreeModel.ShowLegend, False)
        self.setFlag(QgsLayerTreeModel.AllowNodeChangeVisibility, True)

    def columnCount(self, parent=None):
        return super().columnCount(parent) + 1

    def data(self, index, role=Qt.DisplayRole):
        node = self.index2node(index)
        if index.column() == 0:
            if role == Qt.CheckStateRole and node is not None:
                if QgsLayerTree.isLayer(node) or QgsLayerTree.isGroup(node):
                    return Qt.Checked if node.isVisible() else Qt.Unchecked
                return None
        elif QgsLayerTree.isLayer(node) and index.column() > 0:
            if QgsLayerTree.toLayer(node).layer().providerType() == 'WFS':
                if role == Qt.ToolTipRole:
                    return ('该图层来自 <b>WFS</b> 服务。<br>部分 WFS 图层因主键不稳定<br>'
                            '不适合离线编辑，请与系统管理员确认<br>该 WFS 图层能否用于离线编辑。')
                if role == Qt.DecorationRole:
                    return QgsApplication.getThemeIcon('/mIconWarning.svg')
        return super().data(index, role)


class QgsOfflineEditingPluginGui(QDialog):
    def __init__(self, parent=None, flags=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'src/ui/offline_editing/offline_editing_plugin_guibase.ui'), self)
        QgsGui.enableAutoGeometryRestore(self)
        self.mSelectedLayerIds = []
        self.mBrowseButton.clicked.connect(self.browseButtonClicked)
        self.buttonBox.accepted.connect(self.buttonBoxAccepted)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.helpRequested.connect(
            lambda: QgsHelp.openHelp('plugins/core_plugins/plugins_offline_editing.html'))

        self.mOfflineDataPath = QgsSettings().value('plugins/OfflineEditing/offline_data_path', str(Path.home()))
        self.mOfflineDbFile = 'offline.gpkg'
        self.mOfflineDataPathLineEdit.setText(str(Path(self.mOfflineDataPath) / self.mOfflineDbFile))

        self.mLayerTree.setModel(QgsSelectLayerTreeModel(QgsProject.instance().layerTreeRoot().clone(), self))
        self.mLayerTree.header().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.mSelectAllButton.clicked.connect(self.selectAll)
        self.mDeselectAllButton.clicked.connect(self.deSelectAll)
        self.mSelectDatatypeCombo.currentIndexChanged.connect(self.datatypeChanged)

    def closeEvent(self, event):
        QgsSettings().setValue('plugins/OfflineEditing/offline_data_path', self.mOfflineDataPath)
        super().closeEvent(event)

    def offlineDataPath(self):
        return self.mOfflineDataPath

    def offlineDbFile(self):
        return self.mOfflineDbFile

    def selectedLayerIds(self):
        return self.mSelectedLayerIds

    def onlySelected(self):
        return self.mOnlySelectedCheckBox.checkState() == Qt.Checked

    def dbContainerType(self):
        return QgsOfflineEditing.GPKG if self.mSelectDatatypeCombo.currentIndex() == 0 else QgsOfflineEditing.SpatiaLite

    def browseButtonClicked(self):
        if self.dbContainerType() == QgsOfflineEditing.GPKG:
            title, suffix, filters = '选择离线数据的目标数据库', '.gpkg', 'GeoPackage (*.gpkg);;所有文件 (*.*)'
        else:
            title, suffix, filters = '选择离线数据的目标数据库', '.sqlite', 'SpatiaLite 数据库 (*.sqlite);;所有文件 (*.*)'
        path, _ = QFileDialog.getSaveFileName(
            self, title, str(Path(self.mOfflineDataPath) / self.mOfflineDbFile), filters)
        if not path:
            return
        if not path.lower().endswith(suffix):
            path += suffix
        self.mOfflineDbFile, self.mOfflineDataPath = Path(path).name, str(Path(path).parent)
        self.mOfflineDataPathLineEdit.setText(path)

    def buttonBoxAccepted(self):
        if (Path(self.mOfflineDataPath) / self.mOfflineDbFile).exists():
            answer = QMessageBox.question(
                self, QCoreApplication.translate('QgsOfflineEditingPluginGui', 'Offline Editing Plugin'),
                f'正在转换为离线工程。\n离线数据库文件“{self.mOfflineDbFile}”已存在。是否覆盖？',
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes:
                return
        self.mSelectedLayerIds = [node.layerId() for node in self.mLayerTree.model().rootGroup().findLayers()
                                 if node.isVisible()]
        self.accept()

    def selectAll(self):
        for node in self.mLayerTree.model().rootGroup().findLayers():
            node.setItemVisibilityCheckedParentRecursive(True)

    def deSelectAll(self):
        for node in self.mLayerTree.model().rootGroup().findLayers():
            node.setItemVisibilityCheckedParentRecursive(False)

    def datatypeChanged(self, index):
        self.mOfflineDbFile = 'offline.gpkg' if index == 0 else 'offline.sqlite'
        self.mOfflineDataPathLineEdit.setText(str(Path(self.mOfflineDataPath) / self.mOfflineDbFile))
