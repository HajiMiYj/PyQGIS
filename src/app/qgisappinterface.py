"""QgisInterface implementation corresponding to src/app/qgisappinterface.cpp.

Only implemented capabilities are exposed; unported virtuals retain explicit
NotImplementedError rather than silently claiming desktop compatibility.
"""
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolBar
from qgis.PyQt.QtGui import QKeySequence
from qgis.core import QgsProject, QgsApplication
from qgis.gui import QgisInterface, QgsAttributeDialog


class QgisAppInterface(QgisInterface):
    def __init__(self, app):
        super().__init__()
        self.qgis = app
        self.mOptionsFactories = []
        self.mExitBlockers = []
        self.mDropHandlers = []
        self.mLayerConfigFactories = []
        self.mCustomActions = []
        app.mLayerTreeView.currentLayerChanged.connect(self.currentLayerChanged.emit)
        QgsProject.instance().readProject.connect(lambda _: self.projectRead.emit())

    def mainWindow(self): return self.qgis
    def mapCanvas(self): return self.qgis.mMapCanvas
    def mapCanvases(self): return self.qgis.mapCanvases()
    def activeLayer(self): return self.qgis.activeLayer()
    def setActiveLayer(self, layer): return self.qgis.setActiveLayer(layer)
    def layerTreeView(self): return self.qgis.mLayerTreeView
    def layerTreeCanvasBridge(self): return self.qgis.mLayerTreeCanvasBridge
    def browserModel(self): return self.qgis.mBrowserModel
    def messageBar(self): return self.qgis.mMessageBar
    def messageTimeout(self): return self.qgis.mSettings.value('qgis/messageTimeout', 6, type=int)
    def vectorLayerTools(self): return self.qgis.mVectorLayerTools
    def cadDockWidget(self): return self.qgis.mAdvancedDigitizingDockWidget
    def iconSize(self, dockedToolbar=False): return QSize(24, 24)
    def firstRightStandardMenu(self): return self.qgis.mHelpMenu
    def editableLayers(self, modified=False):
        return [l for l in QgsProject.instance().mapLayers().values()
                if hasattr(l, 'isEditable') and l.isEditable() and (not modified or l.isModified())]
    def addVectorLayer(self, path, name, provider='ogr'): return self.qgis.addVectorLayer(path, name, provider)
    def addRasterLayer(self, path, name='', provider='gdal'): return self.qgis.addRasterLayer(path, name, provider)
    def addMeshLayer(self, path, name, provider='mdal'): return self.qgis.addMeshLayer(path, name, provider)
    def addPointCloudLayer(self, path, name, provider='pdal'): return self.qgis.addPointCloudLayer(path, name, provider)
    def addProject(self, path): return self.qgis.addProject(path)
    def newProject(self, promptToSaveFlag=False): return self.qgis.fileNew()
    def showLayerProperties(self, layer, page=''): return self.qgis.showLayerProperties(layer, page)
    def showAttributeTable(self, layer, filterExpression=''):
        return self.qgis.attributeTable(layer=layer, filterExpression=filterExpression)
    def openFeatureForm(self, layer, feature, updateFeatureOnly=False, showModal=True):
        dialog = self.getFeatureForm(layer, feature)
        return bool(dialog.exec_())
    def getFeatureForm(self, layer, feature):
        return QgsAttributeDialog(layer, feature, False, self.qgis)
    def addDockWidget(self, area, dock):
        self.qgis.addDockWidget(area, dock)
        self.qgis.mPanelMenu.addAction(dock.toggleViewAction())
    def addUserInputWidget(self, widget): self.qgis.addUserInputWidget(widget)
    def addTabifiedDockWidget(self, area, dock, tabifyWith=None, raiseTab=False):
        self.addDockWidget(area, dock)
        for name in tabifyWith or []:
            sibling = self.qgis.findChild(type(dock), name)
            if sibling:
                self.qgis.tabifyDockWidget(sibling, dock)
                break
        if raiseTab: dock.raise_()
    def removeDockWidget(self, dock):
        self.qgis.mPanelMenu.removeAction(dock.toggleViewAction())
        self.qgis.removeDockWidget(dock)
    def addToolBar(self, toolbar):
        if isinstance(toolbar, str):
            toolbar = QToolBar(toolbar, self.qgis)
            toolbar.setObjectName(toolbar.windowTitle())
        self.qgis.addToolBar(toolbar)
        self.qgis.mToolbarMenu.addAction(toolbar.toggleViewAction())
        return toolbar
    def addToolBarIcon(self, action):
        self.qgis.mPluginToolBar.addAction(action)
        return len(self.qgis.mPluginToolBar.actions()) - 1
    def removeToolBarIcon(self, action): self.qgis.mPluginToolBar.removeAction(action)
    def addToolBarWidget(self, widget): return self.qgis.mPluginToolBar.addWidget(widget)
    def _pluginMenu(self, parent, name):
        for action in parent.actions():
            if action.menu() and action.text() == name: return action.menu()
        return parent.addMenu(name)
    def addPluginToMenu(self, name, action): self._pluginMenu(self.qgis.mPluginMenu, name).addAction(action)
    def insertAddLayerAction(self, action): self.qgis.insertAddLayerAction(action)
    def removeAddLayerAction(self, action): self.qgis.removeAddLayerAction(action)
    def removePluginMenu(self, name, action): self._pluginMenu(self.qgis.mPluginMenu, name).removeAction(action)
    def registerMainWindowAction(self, action, shortcut):
        action.setShortcut(QKeySequence(shortcut))
        self.qgis.addAction(action)
        return True
    def unregisterMainWindowAction(self, action): self.qgis.removeAction(action)
    def registerOptionsWidgetFactory(self, factory): self.mOptionsFactories.append(factory)
    def unregisterOptionsWidgetFactory(self, factory):
        if factory in self.mOptionsFactories: self.mOptionsFactories.remove(factory)
    def registerApplicationExitBlocker(self, blocker): self.mExitBlockers.append(blocker)
    def unregisterApplicationExitBlocker(self, blocker):
        if blocker in self.mExitBlockers: self.mExitBlockers.remove(blocker)
    def registerCustomDropHandler(self, handler): self.mDropHandlers.append(handler)
    def unregisterCustomDropHandler(self, handler):
        if handler in self.mDropHandlers: self.mDropHandlers.remove(handler)
    def registerLocatorFilter(self, filter): self.qgis.mLocatorWidget.locator().registerFilter(filter)
    def deregisterLocatorFilter(self, filter): self.qgis.mLocatorWidget.locator().deregisterFilter(filter)
    def invalidateLocatorResults(self): self.qgis.mLocatorWidget.invalidateResults()
    def locatorSearch(self, text): self.qgis.mLocatorWidget.search(text)
    def registerMapLayerConfigWidgetFactory(self, factory): self.mLayerConfigFactories.append(factory)
    def unregisterMapLayerConfigWidgetFactory(self, factory):
        if factory in self.mLayerConfigFactories: self.mLayerConfigFactories.remove(factory)
    def showOptionsDialog(self, parent=None, currentPage=''): return self.qgis.options(currentPage)
    def showProjectPropertiesDialog(self, currentPage=''): return self.qgis.projectProperties(currentPage)
    def openMessageLog(self): self.qgis.mLogDock.show()
    def reloadConnections(self): self.qgis.mBrowserModel.refresh()
    def openDataSourceManagerPage(self, page): self.qgis.dataSourceManager(page)
    def showLayoutManager(self): return self.qgis.showLayoutManager()
    def openLayoutDesigner(self, layout): return self.qgis.openLayoutDesigner(layout)
    def openLayoutDesigners(self): return [w for w in self.qgis.mLayoutDesigners]
    def copySelectionToClipboard(self, layer=None): return self.qgis.copySelectionToClipboard(layer)
    def pasteFromClipboard(self, layer=None): return self.qgis.pasteFromClipboard(layer)
    def addCustomActionForLayerType(self, action, menu, layerType, allLayers):
        self.mCustomActions.append((action, menu, layerType, allLayers, set()))
    def addCustomActionForLayer(self, action, layer):
        for entry in self.mCustomActions:
            if entry[0] == action: entry[4].add(layer.id())
    def removeCustomActionForLayerType(self, action):
        self.mCustomActions[:] = [a for a in self.mCustomActions if a[0] != action]
        return True
    def addWindow(self, window): self.qgis.mWindows.append(window)
    def removeWindow(self, window):
        if window in self.qgis.mWindows: self.qgis.mWindows.remove(window)


# Explicit mapping to QgisApp's upstream UI members (not fabricated fallback methods).
_members = {
    'projectMenu': 'mProjectMenu', 'editMenu': 'mEditMenu', 'viewMenu': 'mViewMenu',
    'layerMenu': 'mLayerMenu', 'newLayerMenu': 'mNewLayerMenu', 'addLayerMenu': 'mAddLayerMenu',
    'settingsMenu': 'mSettingsMenu', 'pluginMenu': 'mPluginMenu', 'rasterMenu': 'mRasterMenu',
    'vectorMenu': 'mVectorMenu', 'meshMenu': 'mMeshMenu', 'helpMenu': 'mHelpMenu',
    'databaseMenu': 'mDatabaseMenu', 'webMenu': 'mWebMenu', 'pluginHelpMenu': 'mMenuPluginHelp',
    'fileToolBar': 'mFileToolBar', 'layerToolBar': 'mLayerToolBar', 'mapNavToolToolBar': 'mMapNavToolBar',
    'digitizeToolBar': 'mDigitizeToolBar', 'advancedDigitizeToolBar': 'mAdvancedDigitizeToolBar',
    'attributesToolBar': 'mAttributesToolBar', 'pluginToolBar': 'mPluginToolBar',
    'rasterToolBar': 'mRasterToolBar', 'vectorToolBar': 'mVectorToolBar', 'databaseToolBar': 'mDatabaseToolBar',
    'webToolBar': 'mWebToolBar', 'helpToolBar': 'mHelpToolBar', 'shapeDigitizeToolBar': 'mShapeDigitizeToolBar',
    'selectionToolBar': 'mSelectionToolBar', 'dataSourceManagerToolBar': 'mDataSourceManagerToolBar',
    'projectImportExportMenu': 'menuImport_Export',
}
_actionAliases = {'actionShowPythonDialog': 'mActionShowPythonDialog',
                  'actionOpenStatisticalSummary': 'mActionStatisticalSummary', 'actionOpenFieldCalculator': 'mActionOpenFieldCalc', 'actionLayerSaveAs': 'mActionLayerSaveAs', 'actionCopyLayerStyle': 'mActionCopyStyle',
                  'actionPasteLayerStyle': 'mActionPasteStyle', 'actionCreatePrintLayout': 'mActionNewPrintLayout',
                  'actionSelect': 'mActionSelectFeatures', 'actionSelectRectangle': 'mActionSelectFeatures',
                  'actionZoomFullExtent': 'mActionZoomFullExtent'}
def _memberGetter(name):
    def getter(self): return getattr(self.qgis, name)
    return getter
for _name, _member in _members.items():
    setattr(QgisAppInterface, _name, _memberGetter(_member))
for _name in dir(QgisInterface):
    if _name.startswith('action'):
        setattr(QgisAppInterface, _name, _memberGetter(_actionAliases.get(_name, 'mA' + _name[1:])))
for _category in ('Vector', 'Raster', 'Database', 'Web'):
    def _add(self, name, action, category=_category):
        self._pluginMenu(getattr(self.qgis, f'm{category}Menu'), name).addAction(action)
    def _remove(self, name, action, category=_category):
        self._pluginMenu(getattr(self.qgis, f'm{category}Menu'), name).removeAction(action)
    def _icon(self, action, category=_category):
        toolbar = getattr(self.qgis, f'm{category}ToolBar')
        toolbar.addAction(action)
        toolbar.show()
        return len(toolbar.actions()) - 1
    def _widget(self, widget, category=_category):
        toolbar = getattr(self.qgis, f'm{category}ToolBar')
        action = toolbar.addWidget(widget)
        toolbar.show()
        return action
    def _removeIcon(self, action, category=_category): getattr(self.qgis, f'm{category}ToolBar').removeAction(action)
    setattr(QgisAppInterface, f'addPluginTo{_category}Menu', _add)
    setattr(QgisAppInterface, f'removePlugin{_category}Menu', _remove)
    setattr(QgisAppInterface, f'add{_category}ToolBarIcon', _icon)
    setattr(QgisAppInterface, f'add{_category}ToolBarWidget', _widget)
    setattr(QgisAppInterface, f'remove{_category}ToolBarIcon', _removeIcon)

