"""Application layer-tree context menu; upstream class/file names retained."""
from qgis.PyQt.QtWidgets import QMenu, QInputDialog, QAction
from qgis.core import (QgsLayerTreeLayer, QgsLayerTreeGroup, QgsMapLayerType,
                       QgsVectorLayer, QgsVectorTileLayer, QgsAbstractVectorLayerLabeling, QgsVectorLayerSimpleLabeling)
from qgis.gui import QgsLayerTreeViewMenuProvider


class QgsAppLayerTreeViewMenuProvider(QgsLayerTreeViewMenuProvider):
    def __init__(self, view, canvas, app):
        super().__init__()
        self.mView, self.mCanvas, self.mApp = view, canvas, app
        self.mContextActions = {}
        defaults = view.defaultActions()
        for name, label in [('actionZoomToGroup', '缩放至组'), ('actionMoveOutOfGroup', '移出组'),
                            ('actionMoveToTop', '移到顶部'), ('actionMoveToBottom', '移到底部'),
                            ('actionCheckAndAllChildren', '选中组及所有子项'),
                            ('actionUncheckAndAllChildren', '取消选中组及所有子项'),
                            ('actionCheckAndAllParents', '选中图层及所有父组')]:
            action = QAction(label, app)
            action.setObjectName(name)
            def invoke(checked=False, factory=name):
                native = (defaults.actionZoomToGroup(canvas, app) if factory == 'actionZoomToGroup'
                          else getattr(defaults, factory)(app))
                if native:
                    native.trigger()
                    native.deleteLater()
            action.triggered.connect(invoke)
            self.mContextActions[name] = action
            app.mDynamicActions['layertree:'+name] = dict(action=action, handler=name,
                note='图层树右键菜单调用原生默认动作；使用当前选择与节点。', inInterface=True)
        self.actionShowLabels = QAction('显示标注', app)
        self.actionShowLabels.setObjectName('actionShowLabels')
        self.actionShowLabels.setCheckable(True)
        self.actionShowLabels.toggled.connect(self.toggleLabels)
        app.mDynamicActions['layertree:actionShowLabels'] = dict(action=self.actionShowLabels, handler='toggleLabels',
            note='所选矢量/矢量瓦片标注显隐；无配置时使用原生默认标注设置。', inInterface=True)

    def toggleLabels(self, enabled):
        for node in self.mView.selectedLayerNodes():
            layer = node.layer()
            if isinstance(layer, QgsVectorLayer):
                if not layer.isSpatial(): continue
                if enabled and not layer.labeling():
                    layer.setLabeling(QgsVectorLayerSimpleLabeling(QgsAbstractVectorLayerLabeling.defaultSettingsForLayer(layer)))
            elif not isinstance(layer, QgsVectorTileLayer): continue
            layer.setLabelsEnabled(enabled)
            layer.emitStyleChanged()
            layer.triggerRepaint()
        self.mApp.mProject.setDirty(True)

    def createContextMenu(self):
        menu = QMenu(self.mView)
        defaults = self.mView.defaultActions()
        node = self.mView.currentNode()
        menu.addAction(defaults.actionAddGroup(menu))
        menu.addAction('展开全部', self.mView.expandAll)
        menu.addAction('折叠全部', self.mView.collapseAll)
        if node is None:
            return menu
        menu.addSeparator()
        menu.addAction(defaults.actionRenameGroupOrLayer(menu))
        menu.addAction('移除图层/组', self.mApp.removeLayer)
        if isinstance(node, QgsLayerTreeGroup):
            for name in ('actionZoomToGroup', 'actionCheckAndAllChildren', 'actionUncheckAndAllChildren',
                         'actionMoveToTop', 'actionMoveToBottom'):
                menu.addAction(self.mContextActions[name])
            menu.addAction(defaults.actionMutuallyExclusiveGroup(menu))
            menu.addAction(defaults.actionGroupSelected(menu))
            menu.addAction('保存为图层定义文件…', self.mApp.saveAsLayerDefinition)
        if not isinstance(node, QgsLayerTreeLayer):
            return menu
        layer = node.layer()
        self.mApp.setActiveLayer(layer)
        if isinstance(layer, (QgsVectorLayer, QgsVectorTileLayer)):
            blocked = self.actionShowLabels.blockSignals(True)
            self.actionShowLabels.setChecked(layer.labelsEnabled())
            self.actionShowLabels.blockSignals(blocked)
            menu.addAction(self.actionShowLabels)
        for name in ('actionMoveToTop', 'actionMoveToBottom', 'actionCheckAndAllParents'):
            menu.addAction(self.mContextActions[name])
        if node.parent() is not self.mApp.mProject.layerTreeRoot():
            menu.addAction(self.mContextActions['actionMoveOutOfGroup'])
        menu.addSeparator()
        for name in ['mActionZoomToLayer', 'mActionZoomToSelected', 'mActionDuplicateLayer',
                     'mActionSetLayerScaleVisibility', 'mActionSetLayerCRS', 'mActionSetProjectCRSFromLayer']:
            action = getattr(self.mApp, name, None)
            if action:
                menu.addAction(action)
        menu.addAction(defaults.actionShowInOverview(menu))
        if layer.type() == QgsMapLayerType.VectorLayer:
            menu.addSeparator()
            for name in ['mActionOpenTable', 'mActionToggleEditing', 'mActionSaveEdits', 'mActionLayerSubsetString']:
                menu.addAction(getattr(self.mApp, name))
            menu.addAction(defaults.actionShowFeatureCount(menu))
        menu.addSeparator()
        export = menu.addMenu('导出')
        export.addAction(self.mApp.mActionLayerSaveAs)
        export.addAction('保存图层定义…', self.mApp.saveAsLayerDefinition)
        styles = menu.addMenu('样式')
        styles.addAction(self.mApp.mActionCopyStyle)
        styles.addAction(self.mApp.mActionPasteStyle)
        styles.addAction('加载样式…', self.mApp.loadStyle)
        styles.addAction('保存样式…', self.mApp.saveStyle)
        manager = layer.styleManager()
        styles.addSeparator()
        for name in manager.styles():
            action = styles.addAction(name or '默认')
            action.setCheckable(True)
            action.setChecked(name == manager.currentStyle())
            action.triggered.connect(lambda checked=False, n=name: manager.setCurrentStyle(n))
        styles.addAction('添加样式…', lambda: self.addStyle(layer))
        menu.addSeparator()
        for action in self.mApp.customLayerActions(layer):
            menu.addAction(action)
        menu.addAction(self.mApp.mActionLayerProperties)
        return menu

    def addStyle(self, layer):
        name, ok = QInputDialog.getText(self.mApp, '新样式', '名称')
        if ok and name:
            layer.styleManager().addStyleFromLayer(name)
            layer.styleManager().setCurrentStyle(name)

