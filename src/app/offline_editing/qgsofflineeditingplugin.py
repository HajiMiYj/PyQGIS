"""Port of src/plugins/offline_editing/offline_editing_plugin.cpp.

The native plugin is a C++ core plugin that only wires QgsOfflineEditing to two
actions plus a progress dialog, so it is reproduced here in Python. That keeps
the two database-toolbar entry points working without loading the C++ DLL.
"""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject, QgsOfflineEditing

from .qgsofflineeditingplugingui import QgsOfflineEditingPluginGui
from .qgsofflineeditingprogressdialog import QgsOfflineEditingProgressDialog

PROGRESS_FORMATS = {
    'CopyFeatures': '%v / %m 个要素已复制',
    'ProcessFeatures': '%v / %m 个要素已处理',
    'AddFields': '%v / %m 个字段已添加',
    'AddFeatures': '%v / %m 个要素已添加',
    'RemoveFeatures': '%v / %m 个要素已删除',
    'UpdateFeatures': '%v / %m 个要素已更新',
    'UpdateGeometries': '%v / %m 个要素几何已更新',
}


class QgsOfflineEditingPlugin:
    def __init__(self, app):
        self.mApp = app
        self.mOfflineEditing = None
        self.mProgressDialog = None
        self.mActionConvertProject = None
        self.mActionSynchronize = None

    def initGui(self):
        """Native initGui(): two disabled actions on the database toolbar and menu."""
        iface = self.mApp.mQgisInterface
        self.mActionConvertProject = QAction(QIcon(), '转换为离线工程…', self.mApp)
        self.mActionConvertProject.setObjectName('mActionConvertProject')
        self.mActionConvertProject.setWhatsThis('为所选图层创建离线副本并保存为离线工程')
        self.mActionConvertProject.triggered.connect(lambda: self.convertProject())
        iface.addDatabaseToolBarIcon(self.mActionConvertProject)
        iface.addPluginToDatabaseMenu('离线编辑', self.mActionConvertProject)

        self.mActionSynchronize = QAction(QIcon(), QCoreApplication.translate('QgsOfflineEditingPlugin', 'Synchronize'), self.mApp)
        self.mActionSynchronize.setObjectName('mActionSynchronize')
        self.mActionSynchronize.setWhatsThis('将离线工程与远程图层同步')
        self.mActionSynchronize.triggered.connect(lambda: self.synchronize())
        iface.addDatabaseToolBarIcon(self.mActionSynchronize)
        iface.addPluginToDatabaseMenu('离线编辑', self.mActionSynchronize)

        self.mOfflineEditing = QgsOfflineEditing()
        self.mProgressDialog = QgsOfflineEditingProgressDialog(self.mApp)
        self.mOfflineEditing.progressStarted.connect(self.mProgressDialog.show)
        self.mOfflineEditing.layerProgressUpdated.connect(self.mProgressDialog.setCurrentLayer)
        self.mOfflineEditing.progressModeSet.connect(self.setProgressMode)
        self.mOfflineEditing.progressUpdated.connect(self.mProgressDialog.setProgressValue)
        self.mOfflineEditing.progressStopped.connect(self.mProgressDialog.hide)
        self.mOfflineEditing.warning.connect(self.mApp.mMessageBar.pushWarning)

        # Native connects both project signals and the interface's newProjectCreated.
        self.mApp.mProject.readProject.connect(self.updateActions)
        self.mApp.mQgisInterface.newProjectCreated.connect(self.updateActions)
        self.mApp.mProject.writeProject.connect(self.updateActions)
        self.mApp.mProject.layerWasAdded.connect(self.updateActions)
        self.mApp.mProject.layerWillBeRemoved.connect(self.updateActions)
        self.updateActions()
        return {'offline_editing:mActionConvertProject': self.mActionConvertProject,
                'offline_editing:mActionSynchronize': self.mActionSynchronize}

    def updateActions(self, *args):
        """Native updateActions(): convert for online projects, sync for offline ones."""
        if self.mActionConvertProject is None:
            return
        hasLayers = bool(self.mApp.mProject.count())
        offline = self.mOfflineEditing.isOfflineProject()
        self.mActionConvertProject.setEnabled(hasLayers and not offline)
        self.mActionSynchronize.setEnabled(hasLayers and offline)

    def convertProject(self):
        dialog = QgsOfflineEditingPluginGui(self.mApp)
        if dialog.exec_() != 1:
            dialog.deleteLater()
            return False
        selected = dialog.selectedLayerIds()
        if not selected:
            dialog.deleteLater()
            return False
        self.mProgressDialog.setTitle('正在转换为离线工程')
        try:
            converted = self.mOfflineEditing.convertToOfflineProject(
                dialog.offlineDataPath(), dialog.offlineDbFile(), selected,
                dialog.onlySelected(), dialog.dbContainerType(), '')
        finally:
            dialog.deleteLater()
        if converted:
            self.updateActions()
            self.mApp.mMapCanvas.refreshAllLayers()
        else:
            self.mApp.mMessageBar.pushWarning('离线编辑', '未能转换为离线工程，请检查图层与数据库路径')
        return converted

    def synchronize(self):
        self.mProgressDialog.setTitle('正在同步到远程图层')
        self.mOfflineEditing.synchronize()
        self.updateActions()

    def setProgressMode(self, mode, maximum):
        self.mProgressDialog.setupProgressBar(PROGRESS_FORMATS.get(str(mode), ''), maximum)

    def unload(self):
        """Native unload(): remove both entry points again."""
        iface = self.mApp.mQgisInterface
        for action in (self.mActionConvertProject, self.mActionSynchronize):
            if action is None:
                continue
            iface.removePluginDatabaseMenu('离线编辑', action)
            iface.removeDatabaseToolBarIcon(action)
            action.setParent(None)
            action.deleteLater()
        self.mActionConvertProject = self.mActionSynchronize = None
        self.mProgressDialog = None
        self.mOfflineEditing = None
