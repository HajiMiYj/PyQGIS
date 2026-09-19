"""QgsMapThemes app menu, backed by the native project theme collection."""
from qgis.PyQt.QtCore import QCoreApplication, QObject
from qgis.PyQt.QtWidgets import QMenu, QInputDialog, QMessageBox
from qgis.core import QgsMapThemeCollection


class QgsMapThemes(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.mApp = app
        self.mMenu = QMenu(app)
        self.mMenu.aboutToShow.connect(self.menuAboutToShow)
    def menu(self): return self.mMenu
    def collection(self): return self.mApp.mProject.mapThemeCollection()
    def currentState(self):
        return QgsMapThemeCollection.createThemeFromCurrentState(self.mApp.mProject.layerTreeRoot(), self.mApp.mLayerTreeModel)
    def addPreset(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self.mApp, '添加地图主题', QCoreApplication.translate('DBManagerPlugin', 'Name'))
            if not ok: return
        if not name: return
        if name in self.collection().mapThemes():
            QMessageBox.warning(self.mApp, QCoreApplication.translate('QgsMapThemes', 'Map Themes'), '该名称已经存在')
            return
        self.collection().insert(name, self.currentState())
        self.mApp.mProject.setDirty(True)
    def updatePreset(self, name):
        self.collection().update(name, self.currentState())
        self.mApp.mProject.setDirty(True)
    def applyState(self, name):
        self.collection().applyTheme(name, self.mApp.mProject.layerTreeRoot(), self.mApp.mLayerTreeModel)
    def renameCurrentPreset(self, name):
        newName, ok = QInputDialog.getText(self.mApp, '重命名主题', QCoreApplication.translate('DBManagerPlugin', 'Name'), text=name)
        if ok and newName:
            if not self.collection().renameMapTheme(name, newName):
                QMessageBox.warning(self.mApp, QCoreApplication.translate('QgsMapThemes', 'Map Themes'), '名称已存在或主题已被删除')
            else: self.mApp.mProject.setDirty(True)
    def removeCurrentPreset(self, name):
        self.collection().removeMapTheme(name)
        self.mApp.mProject.setDirty(True)
    def menuAboutToShow(self):
        self.mMenu.clear()
        for label, callback in [('显示所有图层', lambda: self.mApp.setLayersVisible(True)), ('隐藏所有图层', lambda: self.mApp.setLayersVisible(False)), ('显示选中图层', lambda: self.mApp.setSelectedLayersVisible(True)), ('隐藏选中图层', lambda: self.mApp.setSelectedLayersVisible(False))]:
            self.mMenu.addAction(label, callback)
        self.mMenu.addSeparator()
        state = self.currentState()
        current = None
        for name in self.collection().mapThemes():
            action = self.mMenu.addAction(name, lambda checked=False, n=name: self.applyState(n))
            action.setCheckable(True)
            matched = self.collection().mapThemeState(name) == state
            action.setChecked(matched)
            if matched: current = name
        self.mMenu.addSeparator()
        self.mMenu.addAction(QCoreApplication.translate('QgsMapThemes', 'Add Theme…'), lambda: self.addPreset())
        replace = self.mMenu.addMenu('替换主题')
        for name in self.collection().mapThemes(): replace.addAction(name, lambda checked=False, n=name: self.updatePreset(n))
        rename = self.mMenu.addAction(QCoreApplication.translate('QgsMapThemes', 'Rename Current Theme…'), lambda: self.renameCurrentPreset(current))
        remove = self.mMenu.addAction(QCoreApplication.translate('QgsMapThemes', 'Remove Current Theme'), lambda: self.removeCurrentPreset(current))
        rename.setEnabled(current is not None)
        remove.setEnabled(current is not None)
