"""Port of the application attribute-table controller, using native QgsDualView."""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QToolBar, QComboBox, QLineEdit, QLabel, QInputDialog, QMessageBox
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsFeatureRequest, QgsApplication, QgsSettings, QgsField
from qgis.gui import QgsAttributeEditorContext, QgsDualView, QgsAttributeTableFilterModel, QgsFieldCalculator
from src.gui.qgsdockablewidgethelper import QgsDockableWidgetHelper


class QgsAttributeTableDialog(QWidget):
    def __init__(self, layer, app, filterMode=QgsAttributeTableFilterModel.ShowAll):
        super().__init__(app)
        self.setObjectName('QgsAttributeTableDialog')
        self.mLayer, self.mApp = layer, app
        self.resize(1050, 640)
        layout = QVBoxLayout(self)
        self.mToolbar = QToolBar(self)
        self.mActions = {}
        layout.addWidget(self.mToolbar)
        for name in ['mActionToggleEditing', 'mActionSaveEdits', 'mActionDeleteSelected',
                     'mActionCutFeatures', 'mActionCopyFeatures', 'mActionPasteFeatures',
                     'mActionSelectAll', 'mActionInvertSelection', 'mActionDeselectActiveLayer',
                     'mActionZoomToSelected', 'mActionPanToSelected']:
            action = self.mToolbar.addAction(getattr(app, name).icon(), getattr(app, name).text())
            action.setObjectName(name)
            self.mActions[name] = action
            action.triggered.connect(lambda checked=False, n=name: self.layerAction(n))
        self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionCalculateField.svg'), QCoreApplication.translate('QObject', 'Field calculator'), self.runFieldCalculator)
        self.mActionAddAttribute = self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionNewAttribute.svg'), '新增字段', self.addAttribute)
        self.mActionRemoveAttribute = self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionDeleteAttribute.svg'), QCoreApplication.translate('QgsAttributeTableDialog', 'Delete field'), self.removeAttribute)
        self.mToolbar.addAction(QgsApplication.getThemeIcon('/mIconExpressionSelect.svg'), QCoreApplication.translate('QgsExpressionSelectionDialogBase', 'Select by Expression'), lambda: self.layerAction('mActionSelectByExpression'))
        self.mActionSelectedToTop = self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionSelectedToTop.svg'), '选中要素置顶')
        self.mActionSelectedToTop.setCheckable(True)
        self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionOpenTable.svg'), QCoreApplication.translate('QgsAttributeTableDialog', 'Table View'), lambda: self.mMainView.setView(QgsDualView.AttributeTable))
        self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionFormView.svg'), QCoreApplication.translate('QgsAttributeTableDialog', 'Form View'), lambda: self.mMainView.setView(QgsDualView.AttributeEditor))
        self.mToolbar.addAction(QgsApplication.getThemeIcon('/mActionRefresh.svg'), QCoreApplication.translate('QgsCodeEditorHistoryDialogBase', 'Reload'), self.reload)
        self.mFilterButton = QComboBox()
        for text, value in [('全部要素', QgsAttributeTableFilterModel.ShowAll),
                            ('选中要素', QgsAttributeTableFilterModel.ShowSelected),
                            ('地图范围内', QgsAttributeTableFilterModel.ShowVisible),
                            ('已修改和新增', QgsAttributeTableFilterModel.ShowEdited)]:
            self.mFilterButton.addItem(text, value)
        self.mToolbar.addWidget(self.mFilterButton)
        self.mFilterQuery = QLineEdit()
        self.mFilterQuery.setPlaceholderText('QGIS 表达式筛选；回车应用，留空清除')
        layout.addWidget(self.mFilterQuery)
        self.mMainView = QgsDualView(self)
        context = QgsAttributeEditorContext()
        context.setVectorLayerTools(app.mVectorLayerTools)
        context.setMapCanvas(app.mMapCanvas)
        self.mMainView.init(layer, app.mMapCanvas, QgsFeatureRequest(), context)
        self.mMainView.setView(QgsDualView.AttributeTable)
        self.mActionSelectedToTop.toggled.connect(self.mMainView.setSelectedOnTop)
        layout.addWidget(self.mMainView)
        self.mStatus = QLabel()
        layout.addWidget(self.mStatus)
        self.mFilterButton.currentIndexChanged.connect(lambda: self.mMainView.setFilterMode(self.mFilterButton.currentData()))
        self.mFilterQuery.returnPressed.connect(self.filterExpression)
        self.mMainView.setFilterMode(filterMode)
        self.mFilterButton.setCurrentIndex(max(0, self.mFilterButton.findData(filterMode)))
        layer.selectionChanged.connect(self.updateTitle)
        layer.featureAdded.connect(self.updateTitle)
        layer.featureDeleted.connect(self.updateTitle)
        layer.willBeDeleted.connect(self.close)
        self.mDockableWidgetHelper = QgsDockableWidgetHelper(
            QgsSettings().value('qgis/dockAttributeTable', False, type=bool), layer.name(), self, app,
            windowGeometrySettingsKey='Windows/BetterAttributeTable')
        self.mToolbar.addAction(self.mDockableWidgetHelper.createDockUndockAction('停靠属性表', self))
        self.mDockableWidgetHelper.dockModeToggled.connect(lambda docked: QgsSettings().setValue('qgis/dockAttributeTable', docked))
        layer.editingStarted.connect(self.updateTitle)
        layer.editingStopped.connect(self.updateTitle)
        self.updateTitle()

    def show(self): self.mDockableWidgetHelper.setUserVisible(True)
    def closeEvent(self, event):
        self.mDockableWidgetHelper.setUserVisible(False)
        event.accept()
    def reload(self):
        self.mMainView.saveEditChanges()
        self.mLayer.reload()
        self.mMainView.masterModel().loadLayer()
    def addAttribute(self):
        name, ok = QInputDialog.getText(self, '新增字段', '字段名')
        if not ok or not name: return
        if self.mLayer.fields().lookupField(name) >= 0:
            QMessageBox.warning(self, QCoreApplication.translate('QgsActionScopeRegistry', 'Field'), '名称已存在')
            return
        kind, ok = QInputDialog.getItem(self, QCoreApplication.translate('QObject', 'Field type'), QCoreApplication.translate('DBManagerPlugin', 'Type'), ['文本', '整数', '小数', '日期'], 0, False)
        if not ok: return
        types = {'文本': QVariant.String, '整数': QVariant.Int, '小数': QVariant.Double, '日期': QVariant.Date}
        self.mLayer.beginEditCommand('新增字段')
        if self.mLayer.addAttribute(QgsField(name, types[kind])): self.mLayer.endEditCommand()
        else: self.mLayer.destroyEditCommand()
    def removeAttribute(self):
        name, ok = QInputDialog.getItem(self, QCoreApplication.translate('QgsAttributeTableDialog', 'Delete field'), QCoreApplication.translate('QgsActionScopeRegistry', 'Field'), self.mLayer.fields().names(), 0, False)
        if ok and QMessageBox.question(self, QCoreApplication.translate('QgsAttributeTableDialog', 'Delete field'), f'删除 {name}？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.mLayer.beginEditCommand(QCoreApplication.translate('QgsAttributeTableDialog', 'Delete field'))
            if self.mLayer.deleteAttribute(self.mLayer.fields().lookupField(name)): self.mLayer.endEditCommand()
            else: self.mLayer.destroyEditCommand()

    def layerAction(self, name):
        self.mApp.setActiveLayer(self.mLayer)
        getattr(self.mApp, name).trigger()

    def runFieldCalculator(self):
        dlg = QgsFieldCalculator(self.mLayer, self)
        dlg.exec_()

    def filterExpression(self):
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
        text = self.mFilterQuery.text().strip()
        if not text:
            self.mMainView.setFilterMode(QgsAttributeTableFilterModel.ShowAll)
            return
        expr = QgsExpression(text)
        if expr.hasParserError():
            self.mApp.mMessageBar.pushWarning(QCoreApplication.translate('Dialog', 'Expression'), expr.parserErrorString())
            return
        context = self.mLayer.createExpressionContext()
        ids = []
        for feature in self.mLayer.getFeatures():
            context.setFeature(feature)
            result = expr.evaluate(context)
            if expr.hasEvalError():
                self.mApp.mMessageBar.pushWarning(QCoreApplication.translate('Dialog', 'Expression'), expr.evalErrorString())
                return
            if result:
                ids.append(feature.id())
        self.mMainView.setFilteredFeatures(ids)

    def updateTitle(self, *args):
        text = f'{self.mLayer.name()} — 总数 {self.mLayer.featureCount()}，选中 {self.mLayer.selectedFeatureCount()}'
        self.setWindowTitle(text)
        self.mStatus.setText(text)
        if hasattr(self, 'mDockableWidgetHelper'): self.mDockableWidgetHelper.setWindowTitle(text)
        for name, action in self.mActions.items():
            action.setEnabled(self.mLayer.isEditable() if self.mApp.mRequirements.get(name) == 'editing' else True)
        self.mActions['mActionToggleEditing'].setCheckable(True)
        self.mActions['mActionToggleEditing'].setChecked(self.mLayer.isEditable())
        self.mActionAddAttribute.setEnabled(self.mLayer.isEditable())
        self.mActionRemoveAttribute.setEnabled(self.mLayer.isEditable())


