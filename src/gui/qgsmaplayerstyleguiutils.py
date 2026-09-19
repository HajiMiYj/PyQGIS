"""Application-side style manager menu from QGIS 3.34."""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import QAction, QActionGroup, QInputDialog, QLineEdit, QMessageBox
from qgis.core import QgsProject


class QgsMapLayerStyleGuiUtils:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None: cls._instance = cls()
        return cls._instance

    def addStyleManagerActions(self, menu, layer, changed=None):
        def finish(operation):
            if sip.isdeleted(layer): return
            if operation():
                layer.triggerRepaint()
                QgsProject.instance().setDirty(True)
                if changed: changed()
        menu.addAction('添加样式…', lambda: finish(lambda: self.addStyle(layer, menu)))
        remove = menu.addAction(QCoreApplication.translate('QgsMapLayerStyleGuiUtils', 'Remove Current'), lambda: finish(lambda: self.removeStyle(layer)))
        remove.setEnabled(len(layer.styleManager().styles()) > 1)
        menu.addAction('重命名当前样式…', lambda: finish(lambda: self.renameStyle(layer, menu)))
        menu.addSeparator()
        group = QActionGroup(menu)
        for name in layer.styleManager().styles():
            action = QAction(name or '默认样式', group)
            action.setCheckable(True)
            action.setChecked(name == layer.styleManager().currentStyle())
            action.setData(name)
            action.triggered.connect(lambda _=False, n=name: finish(lambda: layer.styleManager().setCurrentStyle(n)))
            menu.addAction(action)
        return group

    def addStyle(self, layer, parent=None, name=None):
        if name is None:
            name, ok = QInputDialog.getText(parent, QCoreApplication.translate('QgsMapLayerStyleGuiUtils', 'New Style'), QCoreApplication.translate('QgsMapLayerStyleGuiUtils', 'Style name:'), QLineEdit.Normal, '新样式')
            if not ok: return False
        if not name: return False
        manager = layer.styleManager()
        if not manager.addStyleFromLayer(name):
            QMessageBox.warning(parent, QCoreApplication.translate('DlgRenderingStyles', 'Style'), '无法添加样式，请使用不重复的名称')
            return False
        return manager.setCurrentStyle(name)

    def removeStyle(self, layer):
        manager = layer.styleManager()
        return len(manager.styles()) > 1 and manager.removeStyle(manager.currentStyle())

    def renameStyle(self, layer, parent=None, name=None):
        manager = layer.styleManager()
        if name is None:
            name, ok = QInputDialog.getText(parent, QCoreApplication.translate('QgsMapLayerStyleGuiUtils', 'Rename Style'), QCoreApplication.translate('QgsMapLayerStyleGuiUtils', 'Style name:'), QLineEdit.Normal, manager.currentStyle())
            if not ok: return False
        if name == manager.currentStyle(): return True
        if not name or not manager.renameStyle(manager.currentStyle(), name):
            QMessageBox.warning(parent, QCoreApplication.translate('DlgRenderingStyles', 'Style'), '无法重命名，请使用不重复的名称')
            return False
        return True
