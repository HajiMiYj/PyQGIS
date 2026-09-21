"""Application layer-tree context menu; upstream class/file names retained."""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMenu, QInputDialog, QAction
from qgis.core import (QgsLayerTreeLayer, QgsLayerTreeGroup, QgsMapLayerType,
                       QgsVectorLayer, QgsRasterLayer, QgsMeshLayer, QgsPointCloudLayer,
                       QgsVectorTileLayer, QgsAbstractVectorLayerLabeling, QgsVectorLayerSimpleLabeling)
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
        self.actionShowLabels = QAction(QCoreApplication.translate('QObject', 'Show label'), app)
        self.actionShowLabels.setObjectName('actionShowLabels')
        self.actionShowLabels.setCheckable(True)
        self.actionShowLabels.toggled.connect(self.toggleLabels)
        for name, label, note in [
                ('changeDataSource', '更改数据源…', '原版 QgsDataSourceSelectDialog 选择新数据源；修复无效图层、保留子集串、刷新图层树，并自动修复同路径的其他损坏图层。'),
                ('zoomToLayerScale', '缩放到可见比例尺', '当前图层超出其比例尺可见范围时缩放到最近可见比例尺。'),
                ('openRasterAttributeTable', '打开栅格属性表', '原生 QgsRasterAttributeTableDialog 打开当前栅格图层属性表。'),
                ('createRasterAttributeTable', '创建栅格属性表', '从 Paletted/伪彩色渲染器创建栅格属性表，支持本机或 DBF 存储。'),
                ('loadRasterAttributeTableFromFile', '从 VAT.DBF 加载栅格属性表', '读取 VAT.DBF 文件并按波段写入栅格图层。'),
                ('legendGroupSetWmsData', '设置组 WMS 数据…', '原生 QgsGroupWmsDataDialog 编辑组 WMS 短名/标题/摘要，写入组自定义属性。')]:
            action = QAction(label, app)
            action.setObjectName(name)
            if name == 'changeDataSource':
                action.triggered.connect(lambda checked=False: app.changeDataSource(self.mView.currentLayer()))
            else:
                action.triggered.connect(getattr(app, name))
            self.mContextActions[name] = action

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
        menu.addAction(QCoreApplication.translate('MainWindow', 'Remove Layer/Group'), self.mApp.removeLayer)
        if isinstance(node, QgsLayerTreeGroup):
            for name in ('actionZoomToGroup', 'actionCheckAndAllChildren', 'actionUncheckAndAllChildren',
                         'actionMoveToTop', 'actionMoveToBottom'):
                menu.addAction(self.mContextActions[name])
            menu.addAction(self.mContextActions['legendGroupSetWmsData'])
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
        if layer.hasScaleBasedVisibility() and not layer.isInScaleRange(self.mCanvas.scale()):
            menu.addAction(self.mContextActions['zoomToLayerScale'])
        if isinstance(layer, (QgsVectorLayer, QgsRasterLayer, QgsMeshLayer, QgsPointCloudLayer)):
            changeAction = self.mContextActions['changeDataSource']
            changeAction.setText(QCoreApplication.translate('QgsAppLayerTreeViewMenuProvider', 'Repair Data Source…') if not layer.isValid() else '更改数据源…')
            changeAction.setEnabled(not layer.isEditable())
            menu.addAction(changeAction)
        if isinstance(layer, QgsRasterLayer):
            if layer.attributeTableCount() > 0:
                menu.addAction(self.mContextActions['openRasterAttributeTable'])
            elif layer.canCreateRasterAttributeTable():
                menu.addAction(self.mContextActions['createRasterAttributeTable'])
            menu.addAction(self.mContextActions['loadRasterAttributeTableFromFile'])
        if layer.type() == QgsMapLayerType.VectorLayer:
            menu.addSeparator()
            for name in ['mActionOpenTable', 'mActionToggleEditing', 'mActionSaveEdits', 'mActionLayerSubsetString']:
                menu.addAction(getattr(self.mApp, name))
            menu.addAction(defaults.actionShowFeatureCount(menu))
        menu.addSeparator()
        export = menu.addMenu(QCoreApplication.translate('QgsAuthCertInfo', 'Export'))
        export.addAction(self.mApp.mActionLayerSaveAs)
        export.addAction('保存图层定义…', self.mApp.saveAsLayerDefinition)
        styles = menu.addMenu(QCoreApplication.translate('QgsAppLayerTreeViewMenuProvider', 'Styles'))
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
        name, ok = QInputDialog.getText(self.mApp, '新样式', QCoreApplication.translate('DBManagerPlugin', 'Name'))
        if ok and name:
            layer.styleManager().addStyleFromLayer(name)
            layer.styleManager().setCurrentStyle(name)

