"""QGIS 3.34.10 desktop controller port, corresponding to src/app/qgisapp.cpp.

Native core/gui classes are imported, never reimplemented as fake substitutes.
The shipped upstream UI and action inventory are the naming/structure baseline.
"""
import json
from pathlib import Path
import traceback
from functools import partial
from qgis.PyQt import uic, sip
from qgis.PyQt.QtCore import Qt, QTimer, QUrl, QSize, QEvent
from qgis.PyQt.QtGui import QDesktopServices, QColor, QKeySequence, QIcon
from qgis.PyQt.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget, QAction, QActionGroup,
    QMenu, QToolBar, QFileDialog, QMessageBox, QInputDialog, QLabel, QLineEdit,
    QCheckBox, QPushButton, QTreeWidget, QTableView, QUndoView, QDialog,
    QDialogButtonBox, QTabWidget, QFormLayout, QDoubleSpinBox, QSpinBox, QToolButton, QProgressBar,
)
from qgis.core import (
    Qgis, QgsApplication, QgsProject, QgsSettings, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsRectangle, QgsVectorLayer, QgsRasterLayer,
    QgsMeshLayer, QgsVectorTileLayer, QgsPointCloudLayer, QgsMapLayerType,
    QgsLayerTreeModel, QgsLayerTreeLayer, QgsLayerTreeGroup, QgsFeature,
    QgsGeometry, QgsFeatureRequest, QgsVectorFileWriter, QgsMapLayerStyle,
    QgsLayerDefinition, QgsStyle, QgsBookmark, QgsReferencedRectangle,
    QgsBookmarkManagerModel, QgsSnappingConfig, QgsTolerance, QgsPrintLayout,
    QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsLayoutExporter,
    QgsProviderRegistry, QgsMimeDataUtils, QgsReadWriteContext, QgsExpression,
    QgsRasterMinMaxOrigin, QgsContrastEnhancement, QgsWkbTypes, QgsVectorDataProvider,
)
from qgis.gui import (
    QgsGui, QgsMapCanvas, QgsMessageBar, QgsLayerTreeView, QgsLayerTreeMapCanvasBridge,
    QgsBrowserGuiModel, QgsBrowserDockWidget, QgsMapCanvasSnappingUtils,
    QgsAdvancedDigitizingDockWidget, QgsMapToolPan, QgsMapToolZoom,
    QgsMapToolDigitizeFeature, QgsVectorLayerProperties, QgsRasterLayerProperties,
    QgsMeshLayerProperties, QgsVectorTileLayerProperties, QgsFieldCalculator,
    QgsExpressionSelectionDialog, QgsQueryBuilder, QgsNewMemoryLayerDialog,
    QgsNewVectorLayerDialog, QgsNewGeoPackageLayerDialog, QgsStyleManagerDialog,
    QgsMessageLogViewer, QgsTemporalControllerWidget, QgsLocatorWidget,
    QgsProjectionSelectionWidget, QgsProjectionSelectionDialog,
    QgsAttributeTableFilterModel, QgsCustomLayerOrderWidget, QgsMapOverviewCanvas,
)
from .qgsguivectorlayertools import QgsGuiVectorLayerTools
from .qgsmaptooladdfeature import QgsMapToolAddFeature
from .qgisappinterface import QgisAppInterface
from .qgsapplayertreeviewmenuprovider import QgsAppLayerTreeViewMenuProvider
from .qgsmaptoolselect import QgsMapToolSelect
from .qgsmaptoolidentifyaction import QgsMapToolIdentifyAction
from .qgsmeasuretool import QgsMeasureTool

ROOT = Path(__file__).resolve().parents[2]


class QgisApp(QMainWindow):
    _instance = None

    @staticmethod
    def instance(): return QgisApp._instance

    def __init__(self, customization=True, customizationFile=None):
        super().__init__()
        QgisApp._instance = self
        self.runtimeErrors = []
        self.mWindows = []
        self.mLayoutDesigners = []
        self.mVectorExportTasks = {}
        self.mAdditionalCanvases = []
        self.mClipboard = None
        self.mStyleClipboard = None
        self.mLayerClipboard = []
        self.mDataSourceManagerDialog = None
        self.mProcessingPlugin = None
        self.mPluginManager = None
        self.mShutdown = False
        self.mImplementedActions = {}
        self.mDynamicActions = {}
        self.mAnnotationItemTools = {}
        self.mAnnotationItemActions = {}
        self.mRequirements = {}
        self.mPreviousSelections = {}
        self.mSettings = QgsSettings()
        try:
            from src.ui.ui_qgisapp import Ui_MainWindow
        except ImportError:
            uic.loadUi(str(ROOT / 'src/ui/qgisapp.ui'), self)
        else:
            ui = Ui_MainWindow()
            ui.setupUi(self)
            self.mUiActionNames = [name for name, value in vars(ui).items() if isinstance(value, QAction)]
            self.__dict__.update(vars(ui))
        self.setObjectName('QgisApp')
        self.resize(1440, 900)
        self.setAcceptDrops(True)
        # self.setWindowIcon(QgsApplication.getThemeIcon('/qgis-icon.svg'))
        self.mProject = QgsProject.instance()
        self.mProject.setCrs(QgsCoordinateReferenceSystem(self.mSettings.value('projections/defaultProjectCrs', 'EPSG:4326')))
        self.mProject.setEllipsoid('WGS84')
        self.createCanvas()
        self.createMenus()
        self.createStatusBar()
        self.createLayerTreeView()
        self.mVectorLayerTools = QgsGuiVectorLayerTools(self)
        self.createDockWidgets()
        self.mQgisInterface = QgisAppInterface(self)
        import qgis.utils
        qgis.utils.iface = self.mQgisInterface
        from console.console import init_options_widget
        init_options_widget()
        self.createMapTools()
        self.mProject.annotationManager().annotationAdded.connect(self.annotationCreated)
        self.mProject.readProjectWithContext.connect(self.restoreFormAnnotations)
        for annotation in self.mProject.annotationManager().annotations(): self.annotationCreated(annotation)
        self.createMapTips()
        self.createDecorations()
        self.createActions()
        from .mesh.qgsmaptooleditmeshframe import QgsMapToolEditMeshFrame
        self.mMeshEditTool = QgsMapToolEditMeshFrame(self.mMapCanvas, self.mAdvancedDigitizingDockWidget, self)
        self.initProcessing()
        self.setTheme()
        self.createToolBars()
        from .qgssnappingwidget import QgsSnappingWidget
        self.mSnappingWidget = QgsSnappingWidget(self.mProject, self.mMapCanvas, self.mSnappingToolBar)
        self.mSnappingToolBar.addWidget(self.mSnappingWidget)
        self.mSnappingToolBar.show()
        self.mProject.layersAdded.connect(self.layersAdded)
        self.mProject.layersWillBeRemoved.connect(self.layersWillBeRemoved)
        self.mProject.isDirtyChanged.connect(self.updateWindowTitle)
        self.mProject.fileNameChanged.connect(self.updateWindowTitle)
        self.mLayerTreeView.currentLayerChanged.connect(self.activateLayer)
        self.mLayerTreeView.selectionModel().selectionChanged.connect(self.updateActionState)
        self.mMapCanvas.mapToolSet.connect(self.updateActionState)
        self.mMapCanvas.extentsChanged.connect(self.updateStatusBar)
        self.mMapCanvas.setMapTool(self.mMapTools['pan'])
        self.mActionPan.setChecked(True)
        self.restoreGeometry(self.mSettings.value('PythonDesktop/geometry', b''))
        self.restoreState(self.mSettings.value('PythonDesktop/state', b''))
        # A saved QMainWindow state may contain an older hidden toolbar layout.
        # The editing workbench must remain discoverable even before a layer is loaded.
        self.mDigitizeToolBar.show()
        self.mAdvancedDigitizeToolBar.show()
        self.mSnappingToolBar.show()
        self.mAnnotationsToolBar.show()
        self.mShapeDigitizeToolBar.show()
        self.mMeshToolBar.show()
        self.updateRecentProjects()
        self.updateActionState()
        self.updateWindowTitle()
        from .qgscustomization import QgsCustomization
        from qgis.PyQt.QtCore import QSettings
        customizationSettings = QSettings(customizationFile, QSettings.IniFormat) if customizationFile else None
        enabled = False if not customization else True if customizationFile else None
        self.mCustomization = QgsCustomization(self, customizationSettings, enabled)
        self.mCustomization.updateMainWindow()
        self.writeCoverage()

    def createCanvas(self):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.mMessageBar = QgsMessageBar(container)
        layout.addWidget(self.mMessageBar)
        self.mMapCanvas = QgsMapCanvas(container)
        from qgis.gui import QgsUserInputWidget, QgsFloatingWidget
        self.mUserInputDockWidget = QgsUserInputWidget(self.mMapCanvas)
        self.mUserInputDockWidget.setObjectName('UserInputDockWidget')
        self.mUserInputDockWidget.setAnchorWidget(self.mMapCanvas)
        self.mUserInputDockWidget.setAnchorWidgetPoint(QgsFloatingWidget.TopRight)
        self.mUserInputDockWidget.setAnchorPoint(QgsFloatingWidget.TopRight)
        self.mMapCanvas.setCanvasColor(QColor(*[self.mSettings.value('qgis/default_canvas_color_' + channel, 255, type=int) for channel in ('red', 'green', 'blue')]))
        self.mMapCanvas.setSelectionColor(QColor(*[self.mSettings.value('qgis/default_selection_color_' + channel, value, type=int) for channel, value in [('red', 255), ('green', 255), ('blue', 0), ('alpha', 255)]]))
        self.mMapCanvas.enableAntiAliasing(self.mSettings.value('PythonDesktop/antialiasing', True, type=bool))
        self.mMapCanvas.setWheelFactor(max(1.01, self.mSettings.value('qgis/zoom_factor', 2.0, type=float)))
        self.mMapCanvas.setMagnificationFactor(max(0.1, self.mSettings.value('qgis/magnifier_factor_default', 1.0, type=float)))
        self.mProject.layerTreeRegistryBridge().setNewLayersVisible(self.mSettings.value('qgis/new_layers_visible', True, type=bool))
        self.mMapCanvas.setDestinationCrs(self.mProject.crs())
        self.mMapCanvas.setProject(self.mProject)
        self.mMapCanvas.setExtent(QgsRectangle(-180, -90, 180, 90))
        self.mSnappingUtils = QgsMapCanvasSnappingUtils(self.mMapCanvas, self)
        self.mSnappingUtils.setConfig(self.mProject.snappingConfig())
        self.mMapCanvas.setSnappingUtils(self.mSnappingUtils)
        self.mProject.snappingConfigChanged.connect(self.mSnappingUtils.setConfig)
        self.mProject.crsChanged.connect(lambda: self.mMapCanvas.setDestinationCrs(self.mProject.crs()))
        layout.addWidget(self.mMapCanvas, 1)
        self.setCentralWidget(container)

    def createMenus(self):
        self.mPanelMenu = self.mViewMenu.addMenu('面板')
        self.mPanelMenu.setObjectName('mPanelMenu')
        self.mToolbarMenu = self.mViewMenu.addMenu('工具栏')
        self.mToolbarMenu.setObjectName('mToolbarMenu')
        self.mDatabaseMenu = QMenu('数据库', self)
        self.mWebMenu = QMenu('Web', self)
        self.menuBar().insertMenu(self.mHelpMenu.menuAction(), self.mDatabaseMenu)
        self.menuBar().insertMenu(self.mHelpMenu.menuAction(), self.mWebMenu)
        action = self.mHelpMenu.addAction('功能移植清单…')
        action.setObjectName('mActionPortingStatus')
        action.triggered.connect(self.showPortingStatus)

    def createStatusBar(self):
        from .qgsstatusbarcoordinateswidget import QgsStatusBarCoordinatesWidget
        from .qgsstatusbarmagnifierwidget import QgsStatusBarMagnifierWidget
        from .qgsstatusbarscalewidget import QgsStatusBarScaleWidget
        from qgis.gui import QgsDoubleSpinBox, QgsStatusBar
        from qgis.PyQt.QtWidgets import QShortcut
        from qgis.PyQt.QtCore import QElapsedTimer
        from src.gui.qgstaskmanagerwidget import QgsTaskManagerStatusBarWidget
        self.statusbar.setStyleSheet('QStatusBar::item {border: none;}')
        statusFont = self.font()
        statusFont.setPointSize(max(8, statusFont.pointSize() - 1))
        self.statusbar.setFont(statusFont)
        self.mStatusBar = QgsStatusBar(self.statusbar)
        self.mStatusBar.setObjectName('mStatusBar')
        self.mStatusBar.setParentStatusBar(self.statusbar)
        self.mStatusBar.setFont(statusFont)
        self.statusbar.addPermanentWidget(self.mStatusBar, 10)
        self.mLocatorWidget = QgsLocatorWidget(self.mStatusBar)
        self.mStatusBar.addPermanentWidget(self.mLocatorWidget, 0, QgsStatusBar.AnchorLeft)
        self.mLocatorShortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        self.mLocatorShortcut.setObjectName('Locator')
        self.mLocatorShortcut.activated.connect(lambda: self.mLocatorWidget.search(''))
        self.mProgressBar = QProgressBar()
        self.mProgressBar.setObjectName('mProgressBar')
        self.mProgressBar.setMaximumWidth(100)
        self.mProgressBar.setMaximumHeight(18)
        self.mProgressBar.setRange(0, 0)
        self.mProgressBar.hide()
        self.mStatusBar.addPermanentWidget(self.mProgressBar, 1)
        self.mLastRenderTime = QElapsedTimer()
        self.mLastRenderTimeSeconds = 0
        self.mRenderProgressBarTimer = QTimer(self)
        self.mRenderProgressBarTimer.setSingleShot(True)
        self.mRenderProgressBarTimer.timeout.connect(lambda: self.showProgress(-1, 0))
        self.mMapCanvas.renderStarting.connect(self.canvasRefreshStarted)
        self.mMapCanvas.mapCanvasRefreshed.connect(self.canvasRefreshFinished)
        self.mTaskManagerWidget = QgsTaskManagerStatusBarWidget(QgsApplication.taskManager(), self.mStatusBar)
        self.mStatusBar.addPermanentWidget(self.mTaskManagerWidget)
        self.mCoordsEdit = QgsStatusBarCoordinatesWidget(self.mMapCanvas, self.mStatusBar)
        self.mCoordsEdit.setObjectName('mCoordsEdit')
        self.mStatusBar.addPermanentWidget(self.mCoordsEdit)
        self.mScaleWidget = QgsStatusBarScaleWidget(self.mMapCanvas, self.mStatusBar)
        self.mScaleWidget.setObjectName('mScaleWidget')
        self.mScaleEdit = self.mScaleWidget.mScale
        self.mStatusBar.addPermanentWidget(self.mScaleWidget)
        self.mMagnifierWidget = QgsStatusBarMagnifierWidget(self.mMapCanvas, self.mStatusBar)
        self.mMagnifierWidget.setObjectName('mMagnifierWidget')
        self.mStatusBar.addPermanentWidget(self.mMagnifierWidget)
        self.mRotationEdit = QgsDoubleSpinBox()
        self.mRotationEdit.setObjectName('mRotationEdit')
        self.mRotationEdit.setClearValue(0)
        self.mRotationEdit.setWrapping(True)
        self.mRotationEdit.setSingleStep(5)
        self.mRotationEdit.setRange(-360, 360)
        self.mRotationEdit.setDecimals(1)
        self.mRotationEdit.setSuffix(' °')
        self.mRotationEdit.setKeyboardTracking(False)
        self.mRotationEdit.setMaximumWidth(120)
        self.mRotationEdit.setToolTip('当前地图顺时针旋转角度')
        self.mRotationEdit.valueChanged.connect(self.mMapCanvas.setRotation)
        self.mMapCanvas.rotationChanged.connect(self.showRotation)
        self.mRotationEdit.setValue(self.mMapCanvas.rotation())
        self.mRotationLabel = QLabel('旋转', self.mStatusBar)
        self.mRotationLabel.setObjectName('mRotationLabel')
        self.mRotationLabel.setMinimumWidth(10)
        self.mRotationLabel.setMargin(3)
        self.mRotationLabel.setAlignment(Qt.AlignCenter)
        self.mRotationLabel.setToolTip(self.mRotationEdit.toolTip())
        self.mStatusBar.addPermanentWidget(self.mRotationLabel)
        self.mStatusBar.addPermanentWidget(self.mRotationEdit)
        self.mRenderSuppressionCBox = QCheckBox('渲染')
        self.mRenderSuppressionCBox.setObjectName('mRenderSuppressionCBox')
        self.mRenderSuppressionCBox.setToolTip('开启或暂停地图渲染')
        self.mRenderSuppressionCBox.setChecked(self.mMapCanvas.renderFlag())
        self.mRenderSuppressionCBox.toggled.connect(self.mMapCanvas.setRenderFlag)
        self.mRenderSuppressionCBox.toggled.connect(lambda enabled: None if enabled else self.canvasRefreshFinished())
        self.mStatusBar.addPermanentWidget(self.mRenderSuppressionCBox)
        self.mOnTheFlyProjectionStatusButton = QToolButton()
        self.mOnTheFlyProjectionStatusButton.setObjectName('mOntheFlyProjectionStatusButton')
        self.mOnTheFlyProjectionStatusButton.setAutoRaise(True)
        self.mOnTheFlyProjectionStatusButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.mOnTheFlyProjectionStatusButton.setIcon(QgsApplication.getThemeIcon('/mIconProjectionEnabled.svg'))
        self.mOnTheFlyProjectionStatusButton.clicked.connect(lambda: self.projectProperties('mProjOptsCRS'))
        self.mStatusBar.addPermanentWidget(self.mOnTheFlyProjectionStatusButton)
        self.mProject.crsChanged.connect(self.updateCrsStatusBar)
        self.updateCrsStatusBar()
        self.mMessageButton = QToolButton()
        self.mMessageButton.setAutoRaise(True)
        self.mMessageButton.setObjectName('mMessageLogViewerButton')
        self.mMessageButton.setCheckable(True)
        self.mMessageButton.setIcon(QgsApplication.getThemeIcon('/mMessageLogRead.svg'))
        self.mMessageButton.setToolTip('显示/隐藏日志消息')
        self.mStatusBar.addPermanentWidget(self.mMessageButton)
        self.mStatusBar.showMessage('就绪')

    def showProgress(self, progress, totalSteps):
        if progress == totalSteps:
            self.mProgressBar.reset()
            self.mProgressBar.hide()
        else:
            self.mProgressBar.setRange(0, totalSteps)
            self.mProgressBar.setValue(progress)
            self.mProgressBar.show()

    def canvasRefreshStarted(self):
        self.mRenderProgressBarTimer.stop()
        self.mLastRenderTime.start()
        if 0 < self.mLastRenderTimeSeconds < 0.5:
            self.mRenderProgressBarTimer.start(500)
        else: self.showProgress(-1, 0)

    def canvasRefreshFinished(self):
        self.mRenderProgressBarTimer.stop()
        if self.mLastRenderTime.isValid(): self.mLastRenderTimeSeconds = self.mLastRenderTime.elapsed()/1000
        self.showProgress(0, 0)

    def updateCrsStatusBar(self):
        crs = self.mProject.crs()
        self.mOnTheFlyProjectionStatusButton.setText((crs.authid() or '未知 CRS') if crs.isValid() else '')
        self.mOnTheFlyProjectionStatusButton.setToolTip(('当前 CRS：' + crs.userFriendlyIdentifier() + '；点击设置') if crs.isValid() else '无投影；点击设置')
        self.mOnTheFlyProjectionStatusButton.setIcon(QgsApplication.getThemeIcon('/mIconProjectionEnabled.svg' if crs.isValid() else '/mIconProjectionDisabled.svg'))

    def showRotation(self, *unused):
        blocked = self.mRotationEdit.blockSignals(True)
        self.mRotationEdit.setValue(self.mMapCanvas.rotation())
        self.mRotationEdit.blockSignals(blocked)



    def setTheme(self):
        # These assignments are made by QgisApp::setTheme in C++, not qgisapp.ui.
        iconPath = ROOT / 'docs/upstream-icons.json'
        from images import THEME_ICONS
        icons = json.loads(iconPath.read_text(encoding='utf-8')) if iconPath.exists() else THEME_ICONS
        # Some 3.34 application assignments still name PNGs absent from its qrc.
        # Keep the source inventory literal and resolve to the shipped SVG here.
        replacements = {'mActionSetLayerCRS': '/mActionSetProjection.svg',
                        'mActionSetProjectCRSFromLayer': '/mActionSetProjection.svg',
                        'mActionToggleFullScreen': '/mActionZoomFullExtent.svg'}
        for name, path in icons.items():
            obj = getattr(self, name, None)
            if obj is not None and hasattr(obj, 'setIcon'):
                icon = QgsApplication.getThemeIcon(path)
                if icon.isNull() and path.endswith('.png'): icon = QgsApplication.getThemeIcon(path[:-4] + '.svg')
                if icon.isNull() and name in replacements: icon = QgsApplication.getThemeIcon(replacements[name])
                if not icon.isNull(): obj.setIcon(icon)
        layer = self.vectorLayer()
        if layer:
            from qgis.core import QgsWkbTypes
            icon = {QgsWkbTypes.PointGeometry: '/mActionCapturePoint.svg', QgsWkbTypes.LineGeometry: '/mActionCaptureLine.svg', QgsWkbTypes.PolygonGeometry: '/mActionCapturePolygon.svg'}.get(layer.geometryType(), '/mActionNewTableRow.svg')
            self.mActionAddFeature.setIcon(QgsApplication.getThemeIcon(icon))
        if hasattr(self, 'mFeatureActionMenu'): self.refreshActionFeatureAction()

    def dock(self, name, title, widget, area=Qt.RightDockWidgetArea, visible=False):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self.mPanelMenu.addAction(dock.toggleViewAction())
        dock.setVisible(visible)
        return dock

    def createLayerTreeView(self):
        self.mLayerTreeView = QgsLayerTreeView(self)
        self.mLayerTreeModel = QgsLayerTreeModel(self.mProject.layerTreeRoot(), self)
        for flag in [QgsLayerTreeModel.AllowNodeRename, QgsLayerTreeModel.AllowNodeReorder,
                     QgsLayerTreeModel.AllowNodeChangeVisibility, QgsLayerTreeModel.ShowLegendAsTree]:
            self.mLayerTreeModel.setFlag(flag)
        self.mLayerTreeView.setModel(self.mLayerTreeModel)
        self.mLayerTreeCanvasBridge = QgsLayerTreeMapCanvasBridge(self.mProject.layerTreeRoot(), self.mMapCanvas, self)
        self.mLayerTreeMapCanvasBridge = self.mLayerTreeCanvasBridge
        self.mLayerTreeViewMenuProvider = QgsAppLayerTreeViewMenuProvider(self.mLayerTreeView, self.mMapCanvas, self)
        self.mLayerTreeView.setMenuProvider(self.mLayerTreeViewMenuProvider)
        self.mLayerTreeView.doubleClicked.connect(lambda _: self.layerProperties())
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mLayerTreeToolBar = QToolBar()
        defaults = self.mLayerTreeView.defaultActions()
        from .qgsmapthemes import QgsMapThemes
        from qgis.gui import QgsLegendFilterButton
        self.mMapThemes = QgsMapThemes(self)
        self.mActionStyleDock = QAction(QgsApplication.getThemeIcon('/propertyicons/symbology.svg'), '图层样式', self)
        self.mActionStyleDock.setObjectName('mActionStyleDock')
        self.mActionStyleDock.setCheckable(True)
        self.mActionStyleDock.setShortcut('F7')
        self.addAction(self.mActionStyleDock)
        self.mActionStyleDock.toggled.connect(self.mapStyleDock)
        self.mLayerTreeToolBar.addAction(self.mActionStyleDock)
        self.actionAddGroup = self.mLayerTreeToolBar.addAction(QgsApplication.getThemeIcon('/mActionAddGroup.svg'), '添加组', defaults.addGroup)
        self.mVisibilityPresetsButton = QToolButton()
        self.mVisibilityPresetsButton.setToolTip('管理地图主题')
        self.mVisibilityPresetsButton.setIcon(QgsApplication.getThemeIcon('/mActionShowAllLayers.svg'))
        self.mVisibilityPresetsButton.setPopupMode(QToolButton.InstantPopup)
        self.mVisibilityPresetsButton.setMenu(self.mMapThemes.menu())
        self.mLayerTreeToolBar.addWidget(self.mVisibilityPresetsButton)
        self.mFilterLegendToolButton = QToolButton()
        self.mFilterLegendToolButton.setToolTip('过滤图例')
        self.mFilterLegendToolButton.setIcon(QgsApplication.getThemeIcon('/mActionFilter2.svg'))
        self.mFilterLegendToolButton.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        self.mFilterLegendToolButton.setMenu(menu)
        self.mFilterLegendByMapContentAction = menu.addAction('按地图内容过滤图例')
        self.mFilterLegendByMapContentAction.setCheckable(True)
        self.mFilterLegendByMapContentAction.toggled.connect(self.updateFilterLegend)
        self.mFilterLegendToggleShowPrivateLayersAction = menu.addAction('显示私有图层')
        self.mFilterLegendToggleShowPrivateLayersAction.setCheckable(True)
        self.mFilterLegendToggleShowPrivateLayersAction.toggled.connect(self.mLayerTreeView.setShowPrivateLayers)
        self.mLayerTreeToolBar.addWidget(self.mFilterLegendToolButton)
        self.mLegendExpressionFilterButton = QgsLegendFilterButton(self)
        self.mLegendExpressionFilterButton.setToolTip('按表达式过滤图例')
        self.mLegendExpressionFilterButton.toggled.connect(self.toggleFilterLegendByExpression)
        self.mLegendExpressionFilterButton.expressionTextChanged.connect(lambda: self.toggleFilterLegendByExpression(self.mLegendExpressionFilterButton.isChecked()))
        self.mLayerTreeToolBar.addWidget(self.mLegendExpressionFilterButton)
        self.actionExpandAll = self.mLayerTreeToolBar.addAction(QgsApplication.getThemeIcon('/mActionExpandTree.svg'), '展开全部', self.mLayerTreeView.expandAllNodes)
        self.actionCollapseAll = self.mLayerTreeToolBar.addAction(QgsApplication.getThemeIcon('/mActionCollapseTree.svg'), '折叠全部', self.mLayerTreeView.collapseAllNodes)
        for name in ('actionAddGroup', 'actionExpandAll', 'actionCollapseAll', 'mActionStyleDock',
                     'mFilterLegendByMapContentAction', 'mFilterLegendToggleShowPrivateLayersAction'):
            action = getattr(self, name)
            action.setObjectName(name)
            self.mDynamicActions['qgisapp:' + name] = dict(action=action, handler=name, note='原版图层面板动态入口。',
                                                          toolbarWidget=self.mLayerTreeToolBar, inInterface=True)
        self.mLayerTreeToolBar.addAction(self.mActionRemoveLayer)
        self.mMapCanvas.extentsChanged.connect(self.updateFilterLegend)
        layout.addWidget(self.mLayerTreeToolBar)
        layout.addWidget(self.mLayerTreeView)
        self.mLayerTreeDock = self.dock('Layers', '图层', container, Qt.LeftDockWidgetArea, True)

    def createDockWidgets(self):
        self.mBrowserModel = QgsBrowserGuiModel(self)
        self.mBrowserModel.initialize()
        self.mBrowserWidget = QgsBrowserDockWidget('浏览器', self.mBrowserModel, self)
        self.mBrowserWidget.setObjectName('Browser')
        self.mBrowserWidget.setDisabledDataItemsKeys(['gpx'])
        self.mBrowserWidget.setMessageBar(self.mMessageBar)
        self.mBrowserWidget.openFile.connect(lambda path, hint='': self.openFile(path))
        self.mBrowserWidget.handleDropUriList.connect(self.handleDropUriList)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.mBrowserWidget)
        self.mPanelMenu.addAction(self.mBrowserWidget.toggleViewAction())
        self.mAdvancedDigitizingDockWidget = QgsAdvancedDigitizingDockWidget(self.mMapCanvas, self)
        self.mAdvancedDigitizingDockWidget.setObjectName('AdvancedDigitizingTools')
        self.addDockWidget(Qt.LeftDockWidgetArea, self.mAdvancedDigitizingDockWidget)
        self.mPanelMenu.addAction(self.mAdvancedDigitizingDockWidget.toggleViewAction())
        self.mAdvancedDigitizingDockWidget.hide()
        self.mUndoWidget = QUndoView(self)
        self.mUndoDock = self.dock('Undo', '撤销/重做', self.mUndoWidget)
        self.mLogViewer = QgsMessageLogViewer(self)
        self.mLogDock = self.dock('MessageLog', '日志消息', self.mLogViewer, Qt.BottomDockWidgetArea)
        self.mMessageButton.toggled.connect(self.mLogDock.setVisible)
        self.mLogDock.visibilityChanged.connect(self.mMessageButton.setChecked)
        self.mLogDock.visibilityChanged.connect(lambda visible: self.toggleLogMessageIcon(False) if visible else None)
        QgsApplication.messageLog().messageReceived[bool].connect(self.toggleLogMessageIcon)
        # QgsMessageLogViewer creates tabs on the first message for each tag.
        QgsApplication.messageLog().logMessage('QGIS Python 已启动', '通用', Qgis.Info)
        QgsApplication.messageLog().logMessage('Python 插件宿主已初始化', '插件', Qgis.Info)
        self.mTemporalControllerWidget = QgsTemporalControllerWidget(self)
        self.mTemporalControllerDock = self.dock('TemporalController', '时间控制器', self.mTemporalControllerWidget, Qt.BottomDockWidgetArea)
        self.mMapCanvas.setTemporalController(self.mTemporalControllerWidget.temporalController())
        self.mIdentifyResults = QTreeWidget(self)
        self.mIdentifyResults.setHeaderLabels(['属性', '值'])
        identifyContainer = QWidget()
        identifyLayout = QVBoxLayout(identifyContainer)
        identifyLayout.setContentsMargins(0, 0, 0, 0)
        self.mIdentifyResultsToolBar = QToolBar()
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionExpandTree.svg'), '展开全部', self.mIdentifyResults.expandAll)
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionCollapseTree.svg'), '折叠全部', self.mIdentifyResults.collapseAll)
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionDeleteSelected.svg'), '清除', self.mIdentifyResults.clear)
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionEditCopy.svg'), '复制选中值', self.copyIdentifyValue)
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionZoomToSelected.svg'), '缩放到结果', self.zoomToIdentifyResult)
        self.mIdentifyResultsToolBar.addAction(QgsApplication.getThemeIcon('/mActionFormView.svg'), '打开要素表单', self.openIdentifyForm)
        identifyLayout.addWidget(self.mIdentifyResultsToolBar)
        identifyLayout.addWidget(self.mIdentifyResults)
        self.mIdentifyResultsDock = self.dock('IdentifyResults', '识别结果', identifyContainer)
        self.mLayerOrderWidget = QgsCustomLayerOrderWidget(self.mLayerTreeCanvasBridge, self)
        self.mLayerOrderDock = self.dock('LayerOrder', '图层顺序', self.mLayerOrderWidget)
        self.mOverviewCanvas = QgsMapOverviewCanvas(self, self.mMapCanvas)
        self.mLayerTreeCanvasBridge.setOverviewCanvas(self.mOverviewCanvas)
        self.mOverviewDock = self.dock('Overview', '概览', self.mOverviewCanvas, Qt.LeftDockWidgetArea)
        self.mBookmarksModel = QgsBookmarkManagerModel(QgsApplication.bookmarkManager(), self.mProject.bookmarkManager(), self)
        self.mBookmarksView = QTableView(self)
        self.mBookmarksView.setModel(self.mBookmarksModel)
        self.mBookmarksView.doubleClicked.connect(self.zoomToBookmark)
        self.mBookmarksDock = self.dock('Bookmarks', '空间书签', self.mBookmarksView)
        from .vertextool.qgsvertexeditor import QgsVertexEditor
        self.mVertexEditorDock = QgsVertexEditor(self.mMapCanvas, self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.mVertexEditorDock)
        self.mPanelMenu.addAction(self.mVertexEditorDock.toggleViewAction())
        self.mVertexEditorDock.hide()
        from .qgsstatisticalsummarydockwidget import QgsStatisticalSummaryDockWidget
        self.mStatisticalSummaryDockWidget = QgsStatisticalSummaryDockWidget(self.mMapCanvas, self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.mStatisticalSummaryDockWidget)
        self.mPanelMenu.addAction(self.mStatisticalSummaryDockWidget.toggleViewAction())
        self.mStatisticalSummaryDockWidget.hide()

    def mapStyleDock(self, visible):
        if not hasattr(self, 'mLayerStylingWidget'):
            from .qgslayerstylingwidget import QgsLayerStylingWidget
            self.mLayerStylingWidget = QgsLayerStylingWidget(self)
            self.mMapStylingDock = self.dock('LayerStyling', '图层样式', self.mLayerStylingWidget)
            self.mMapStylingDock.visibilityChanged.connect(self.mActionStyleDock.setChecked)
        self.mLayerStylingWidget.setLayer(self.activeLayer())
        self.mMapStylingDock.setVisible(visible)
    def toggleFilterLegendByExpression(self, checked):
        from qgis.core import QgsLayerTreeUtils
        node = self.mLayerTreeView.currentNode()
        if isinstance(node, QgsLayerTreeLayer): QgsLayerTreeUtils.setLegendFilterByExpression(node, self.mLegendExpressionFilterButton.expressionText(), checked)
        self.updateFilterLegend()
    def updateFilterLegend(self, *args):
        from qgis.core import QgsLayerTreeUtils, QgsLayerTreeFilterSettings
        root = self.mProject.layerTreeRoot()
        expressions = QgsLayerTreeUtils.hasLegendFilterExpression(root)
        if self.mFilterLegendByMapContentAction.isChecked() or expressions:
            settings = QgsLayerTreeFilterSettings(self.mMapCanvas.mapSettings())
            if not self.mFilterLegendByMapContentAction.isChecked(): settings.setFlags(Qgis.LayerTreeFilterFlag.SkipVisibilityCheck)
            if expressions: settings.setLayerFilterExpressionsFromLayerTree(root)
            self.mLayerTreeModel.setFilterSettings(settings)
        else: self.mLayerTreeModel.setFilterSettings(None)

    def createMapTools(self):
        from .qgsmaptoolmovefeature import QgsMapToolMoveFeature
        from .qgsmaptoolgeometryedit import QgsMapToolGeometryEdit
        from .vertextool.qgsvertextool import QgsVertexTool
        from .qgsmaptoolmeasureangle import QgsMapToolMeasureAngle
        from .qgsmaptoolmeasurebearing import QgsMapToolMeasureBearing
        canvas = self.mMapCanvas
        self.mMapTools = {'pan': QgsMapToolPan(canvas), 'zoomIn': QgsMapToolZoom(canvas, False),
                         'zoomOut': QgsMapToolZoom(canvas, True), 'selectFeatures': QgsMapToolSelect(canvas),
                         'identify': QgsMapToolIdentifyAction(canvas, self),
                         'measure': QgsMeasureTool(canvas),
                         'measureArea': QgsMeasureTool(canvas, True),
                         'measureBearing': QgsMapToolMeasureBearing(canvas),
                         'measureAngle': QgsMapToolMeasureAngle(canvas),
                         'addFeature': QgsMapToolAddFeature(canvas, self.mAdvancedDigitizingDockWidget, self)}
        self.mMapTools['addFeature'].digitizingCompleted.connect(self.digitizingCompleted)
        self.mMapTools.update({
            'moveFeature': QgsMapToolMoveFeature(canvas, QgsMapToolMoveFeature.Move, self.mAdvancedDigitizingDockWidget),
            'moveFeatureCopy': QgsMapToolMoveFeature(canvas, QgsMapToolMoveFeature.CopyMove, self.mAdvancedDigitizingDockWidget),
            'vertexTool': QgsVertexTool(canvas, self.mAdvancedDigitizingDockWidget),
            'vertexToolActiveLayer': QgsVertexTool(canvas, self.mAdvancedDigitizingDockWidget, QgsVertexTool.ActiveLayer),
        })
        from .qgsmaptoolsplitfeatures import QgsMapToolSplitFeatures
        from .qgsmaptoolsplitparts import QgsMapToolSplitParts
        from .qgsmaptooladdring import QgsMapToolAddRing
        from .qgsmaptooladdpart import QgsMapToolAddPart
        from .qgsmaptoolreshape import QgsMapToolReshape
        for name, cls in [('split', QgsMapToolSplitFeatures), ('splitParts', QgsMapToolSplitParts), ('addRing', QgsMapToolAddRing), ('addPart', QgsMapToolAddPart), ('reshape', QgsMapToolReshape)]:
            self.mMapTools[name] = cls(canvas, self.mAdvancedDigitizingDockWidget)
            self.mMapTools[name].messageEmitted.connect(lambda message, level: self.mMessageBar.pushMessage('几何编辑', message, level=level))
        self.mGeometryEditTool = QgsMapToolGeometryEdit(canvas, self.mAdvancedDigitizingDockWidget, 'operation')
        from .qgsmaptooldeletepart import QgsMapToolDeletePart
        from .qgsmaptooldeletering import QgsMapToolDeleteRing
        self.mMapTools['deletePart'] = QgsMapToolDeletePart(canvas)
        self.mMapTools['deleteRing'] = QgsMapToolDeleteRing(canvas)
        from .qgsmaptooltrimextendfeature import QgsMapToolTrimExtendFeature
        self.mMapTools['trimExtendFeature'] = QgsMapToolTrimExtendFeature(canvas)
        self.mMapTools['trimExtendFeature'].messageEmitted.connect(lambda message, level: self.mMessageBar.pushMessage('修剪/延伸', message, level=level))
        from .qgsmaptoolfillring import QgsMapToolFillRing
        from .qgsmaptoolfeatureaction import QgsMapToolFeatureAction
        self.mMapTools['fillRing'] = QgsMapToolFillRing(canvas, self.mAdvancedDigitizingDockWidget, self)
        self.mMapTools['featureAction'] = QgsMapToolFeatureAction(canvas, self)
        from .qgsmaptooltextannotation import QgsMapToolTextAnnotation
        from .qgsmaptoolsvgannotation import QgsMapToolSvgAnnotation
        from .qgsmaptoolhtmlannotation import QgsMapToolHtmlAnnotation
        from .qgsmaptoolformannotation import QgsMapToolFormAnnotation
        for key, cls in [('textAnnotation', QgsMapToolTextAnnotation), ('svgAnnotation', QgsMapToolSvgAnnotation),
                         ('htmlAnnotation', QgsMapToolHtmlAnnotation), ('formAnnotation', QgsMapToolFormAnnotation)]:
            self.mMapTools[key] = cls(canvas)
        from .qgsmaptoolrotatepointsymbols import QgsMapToolRotatePointSymbols
        from .qgsmaptooloffsetpointsymbol import QgsMapToolOffsetPointSymbol
        self.mMapTools['rotatePointSymbols'] = QgsMapToolRotatePointSymbols(canvas)
        self.mMapTools['offsetPointSymbol'] = QgsMapToolOffsetPointSymbol(canvas)
        for key in ('rotatePointSymbols', 'offsetPointSymbol'):
            self.mMapTools[key].messageEmitted.connect(lambda message, level: self.mMessageBar.pushMessage('点符号', message, level=level))
        from .labeling.qgsmaptoolpinlabels import QgsMapToolPinLabels
        from .labeling.qgsmaptoolshowhidelabels import QgsMapToolShowHideLabels
        from .labeling.qgsmaptoolmovelabel import QgsMapToolMoveLabel
        from .labeling.qgsmaptoolrotatelabel import QgsMapToolRotateLabel
        from .labeling.qgsmaptoolchangelabelproperties import QgsMapToolChangeLabelProperties
        for key, cls in [('pinLabels', QgsMapToolPinLabels), ('showHideLabels', QgsMapToolShowHideLabels),
                         ('moveLabel', QgsMapToolMoveLabel), ('rotateLabel', QgsMapToolRotateLabel),
                         ('changeLabelProperties', QgsMapToolChangeLabelProperties)]:
            self.mMapTools[key] = cls(canvas, self.mAdvancedDigitizingDockWidget)
            self.mMapTools[key].messageEmitted.connect(lambda message, level: self.mMessageBar.pushMessage('标注', message, level=level))
        for key in ('fillRing', 'featureAction'):
            self.mMapTools[key].messageEmitted.connect(lambda message, level: self.mMessageBar.pushMessage('要素', message, level=level))
        from .qgsmaptoolselectionhandler import QgsMapToolSelectionHandler
        for key, mode in [('selectPolygon', QgsMapToolSelectionHandler.SelectPolygon), ('selectFreehand', QgsMapToolSelectionHandler.SelectFreehand), ('selectRadius', QgsMapToolSelectionHandler.SelectRadius)]:
            self.mMapTools[key] = QgsMapToolSelect(canvas, mode)
        for key in ('vertexTool', 'vertexToolActiveLayer'):
            self.mMapTools[key].vertexSelected.connect(self.mVertexEditorDock.setVertex)
        self.mMapToolActionGroup = QActionGroup(self)
        self.mMapToolActionGroup.setExclusive(True)
        from src.gui.annotations.qgsmaptoolmodifyannotation import QgsMapToolModifyAnnotation
        self.mMapTools['modifyAnnotation'] = QgsMapToolModifyAnnotation(self.mMapCanvas, self)

    def bind(self, name, callback, requirement=None, note='', signal='triggered'):
        action = getattr(self, name, None)
        if action is None:
            raise AttributeError(f'Upstream UI action missing: {name}')
        getattr(action, signal).connect(lambda checked=False: callback())
        action.setEnabled(True)
        self.mImplementedActions[name] = {'handler': getattr(callback, '__name__', str(callback)), 'note': note}
        if requirement: self.mRequirements[name] = requirement

    def createActions(self):
        # Restrict the porting state to the main form's own inventory. Native
        # browser/editor widgets also have mAction* children with working slots.
        inventoryPath = ROOT / 'docs/upstream-actions.json'
        if inventoryPath.exists():
            inventory = json.loads(inventoryPath.read_text(encoding='utf-8'))
        else:
            actionNames = getattr(self, 'mUiActionNames', [])
            if not actionNames:
                actionNames = [action.objectName() for action in self.findChildren(QAction) if action.objectName()]
            inventory = {'actions': []}
            for name in actionNames:
                action = getattr(self, name, None)
                inventory['actions'].append({
                    'objectName': name,
                    'text': action.text() if isinstance(action, QAction) else name,
                    'excluded': False,
                })
            QgsApplication.messageLog().logMessage(
                '未找到可选动作清单；已从当前 UI 自动发现 QAction',
                'Python', Qgis.Warning)
        self.mActionInventory = inventory
        for item in inventory['actions']:
            action = getattr(self, item['objectName'], None)
            if isinstance(action, QAction):
                action.setEnabled(False)
                action.setToolTip(action.text() + ' — 此应用层功能尚未移植；见帮助 → 功能移植清单')
        slots = {
            'NewProject': self.fileNew, 'NewBlankProject': self.fileNewBlank,
            'OpenProject': self.fileOpen, 'CloseProject': self.fileClose, 'RevertProject': self.fileRevert,
            'SaveProject': self.fileSave, 'SaveProjectAs': self.fileSaveAs, 'Exit': self.fileExit,
            'SaveMapAsImage': self.saveMapAsImage, 'SaveMapAsPdf': self.saveMapAsPdf,
            'Draw': self.refreshMapCanvas, 'ZoomFullExtent': self.zoomFull,
            'ZoomLast': self.zoomToPrevious, 'ZoomNext': self.zoomToNext,
            'NewMapCanvas': self.newMapCanvas, 'ToggleFullScreen': self.toggleFullScreen,
            'TogglePanelsVisibility': self.togglePanelsVisibility, 'ToggleMapOnly': self.toggleMapOnly,
            'ShowAllLayers': partial(self.setLayersVisible, True), 'HideAllLayers': partial(self.setLayersVisible, False),
            'ShowSelectedLayers': partial(self.setSelectedLayersVisible, True),
            'HideSelectedLayers': partial(self.setSelectedLayersVisible, False),
            'ToggleSelectedLayers': self.toggleSelectedLayers, 'ToggleSelectedLayersIndependently': self.toggleSelectedLayers,
            'HideDeselectedLayers': self.hideDeselectedLayers,
            'AddAllToOverview': partial(self.allToOverview, True), 'RemoveAllFromOverview': partial(self.allToOverview, False),
            'NewMemoryLayer': self.newMemoryLayer, 'NewVectorLayer': self.newVectorLayer,
            'NewGeoPackageLayer': self.newGeoPackageLayer, 'AddLayerDefinition': self.addLayerDefinition,
            'ShowPythonDialog': self.showPythonDialog, 'StyleManager': self.showStyleManager,
            'ManagePlugins': self.showPluginManager, 'ProjectProperties': self.projectProperties,
            'Options': self.options, 'ConfigureShortcuts': self.configureShortcuts,
            'TemporalController': self.mTemporalControllerDock.show,
            'ShowBookmarks': self.mBookmarksDock.show, 'ShowBookmarkManager': self.mBookmarksDock.show,
            'NewBookmark': self.newBookmark, 'NewPrintLayout': self.newPrintLayout,
            'ShowLayoutManager': self.showLayoutManager, 'DeselectAll': self.deselectAll,
            'SaveAllEdits': self.saveAllEdits, 'RollbackAllEdits': self.rollbackAllEdits,
            'CancelAllEdits': self.cancelAllEdits, 'PasteAsNewMemoryVector': self.pasteAsNewMemoryVector,
            'PasteLayer': self.pasteLayer, 'SnappingOptions': self.snappingOptions,
        }
        for name, callback in slots.items(): self.bind('mAction' + name, callback)
        layerSlots = {
            'ZoomToLayer': self.zoomToLayerExtent, 'ZoomToLayers': self.zoomToLayerExtent,
            'LayerProperties': self.layerProperties, 'LayerSaveAs': self.saveAsFile,
            'RemoveLayer': self.removeLayer, 'DuplicateLayer': self.duplicateLayers,
            'SetLayerCRS': self.setLayerCrs, 'SetProjectCRSFromLayer': self.setProjectCrsFromLayer,
            'SetLayerScaleVisibility': self.setLayerScaleVisibility, 'AddToOverview': self.addToOverview,
            'CopyStyle': self.copyStyle, 'PasteStyle': self.applyStyleToGroup,
            'CopyLayer': self.copyLayer, 'SaveLayerDefinition': self.saveAsLayerDefinition,
        }
        for name, callback in layerSlots.items(): self.bind('mAction' + name, callback, 'layer')
        vectorSlots = {
            'OpenTable': self.attributeTable, 'OpenTableSelected': partial(self.attributeTable, QgsAttributeTableFilterModel.ShowSelected),
            'OpenTableVisible': partial(self.attributeTable, QgsAttributeTableFilterModel.ShowVisible),
            'OpenTableEdited': partial(self.attributeTable, QgsAttributeTableFilterModel.ShowEdited),
            'SelectAll': self.selectAll, 'InvertSelection': self.invertSelection,
            'DeselectActiveLayer': self.deselectActiveLayer, 'SelectByExpression': self.selectByExpression,
            'Reselect': self.reselect, 'ToggleEditing': self.toggleEditing,
            'LayerSubsetString': self.layerSubsetString, 'OpenFieldCalc': self.fieldCalculator,
            'CopyFeatures': self.copySelectionToClipboard, 'ZoomToSelected': self.zoomToSelected,
            'PanToSelected': self.panToSelected, 'Labeling': self.labeling, 'DiagramProperties': self.diagramProperties,
        }
        for name, callback in vectorSlots.items(): self.bind('mAction' + name, callback, 'vector')
        editSlots = {'SaveEdits': self.saveEdits, 'SaveLayerEdits': self.saveActiveLayerEdits,
                     'RollbackEdits': self.rollbackEdits, 'CancelEdits': self.cancelEdits,
                     'DeleteSelected': self.deleteSelected, 'CutFeatures': self.cutSelectionToClipboard,
                     'PasteFeatures': self.pasteFromClipboard, 'Undo': self.undo, 'Redo': self.redo}
        for name, callback in editSlots.items(): self.bind('mAction' + name, callback, 'editing')
        geometrySlots = {
            'SimplifyFeature': self.runSimplifyFeature,
            'RotateFeature': self.runRotateFeature,
            'ScaleFeature': self.runScaleFeature,
            'MergeFeatures': self.runMergeFeatures,
            'MergeFeatureAttributes': self.runMergeFeatureAttributes,
            'ReverseLine': self.runReverseLine,
            'OffsetCurve': self.runOffsetCurve,
        }
        for name, callback in geometrySlots.items():
            self.bind('mAction' + name, callback, 'geometry-edit')
        rasterSlots = {
            'FullHistogramStretch': self.fullHistogramStretch, 'LocalHistogramStretch': self.localHistogramStretch,
            'FullCumulativeCutStretch': self.fullCumulativeCutStretch, 'LocalCumulativeCutStretch': self.localCumulativeCutStretch,
            'IncreaseBrightness': self.increaseBrightness, 'DecreaseBrightness': self.decreaseBrightness,
            'IncreaseContrast': self.increaseContrast, 'DecreaseContrast': self.decreaseContrast,
            'IncreaseGamma': self.increaseGamma, 'DecreaseGamma': self.decreaseGamma,
        }
        for name, callback in rasterSlots.items(): self.bind('mAction' + name, callback, 'raster')
        self.bind('mActionShowRasterCalculator', self.showRasterCalculator)
        self.bind('mActionDxfExport', self.dxfExport, note='原版 DXF 窗口、图层/字段选择、地图主题、符号模式/比例、编码/CRS、范围、二维和 MText；原生 QgsDxfExport 写文件。复杂 CAD 符号组合仍需验收。')
        self.bind('mActionDwgImport', self.dwgImport, note='原版 CAD 表单；GDAL 读取、GeoPackage、CRS/XYZ/属性、三种 DXF 块模式、图层选择/预览/分组/合并。ASCII DXF 隐藏/冻结/锁定标志、中文编码、透明色、纸面/地图单位、虚线及端点/连接样式、字体/粗斜体/下划线/删除线/对齐/旋转，以及原版包的多段线宽度与 MTEXT 行距已接入并检查。DWG 版本范围、二进制图层状态、曲线、复杂块/填充/特殊文字仍不完整。')
        self.bind('mActionNewSpatiaLiteLayer', self.newSpatialiteLayer, note='原版建层窗口；数据库连接、字段、主键、几何/Z/M、CRS、空间索引与事务创建；添加至工程。已有数据库只添加，不提供整库覆盖。')
        self.bind('mActionShowMeshCalculator', self.showMeshCalculator, 'mesh', note='原版网格计算 UI；数据集/运算符、时间、范围/多边形掩膜、MDAL 持久或虚拟结果组、进度与取消。部分驱动和复杂时间数据待验收。')
        self.bind('mActionNewMeshLayer', self.newMeshLayer, note='原版窗口与 MDAL createMeshData；空网格、从工程/文件复制网格框架、格式/CRS/名称与加载。不包含网格数字化工具移植。')
        self.bind('mActionSelectByForm', self.selectByForm, 'vector')
        self.bind('mActionMultiEditAttributes', self.modifyAttributesOfSelectedFeatures, 'editing')
        self.bind('mActionZoomActualSize', self.zoomActualSize, 'raster')
        from qgis.gui import QgsPreviewEffect
        previewModes = {'PreviewModeOff': None, 'PreviewModeMono': QgsPreviewEffect.PreviewMono,
                        'PreviewModeGrayscale': QgsPreviewEffect.PreviewGrayscale,
                        'PreviewProtanope': QgsPreviewEffect.PreviewProtanope,
                        'PreviewDeuteranope': QgsPreviewEffect.PreviewDeuteranope,
                        'PreviewTritanope': QgsPreviewEffect.PreviewTritanope}
        self.mPreviewActionGroup = QActionGroup(self)
        for name, mode in previewModes.items():
            self.mPreviewActionGroup.addAction(getattr(self, 'mAction' + name))
            self.bind('mAction' + name, partial(self.setPreviewMode, mode))
        self.mCaptureTechniqueGroup = QActionGroup(self)
        for name, technique in [('DigitizeWithSegment', Qgis.CaptureTechnique.StraightSegments),
                                ('DigitizeWithCurve', Qgis.CaptureTechnique.CircularString),
                                ('StreamDigitize', Qgis.CaptureTechnique.Streaming)]:
            self.mCaptureTechniqueGroup.addAction(getattr(self, 'mAction' + name))
            self.bind('mAction' + name, partial(self.setCaptureTechnique, technique), 'capture-technique')
            getattr(self, 'mAction' + name).setData(technique)
        self.mActionDigitizeWithSegment.setChecked(True)
        from .maptools.qgsmaptoolsdigitizingtechniquemanager import QgsMapToolsDigitizingTechniqueManager
        self.mMapToolsDigitizingTechniqueManager = QgsMapToolsDigitizingTechniqueManager(self)
        self.mCaptureTechniqueGroup.addAction(self.mActionDigitizeShape)
        self.bind('mActionDigitizeShape', self.mMapToolsDigitizingTechniqueManager.setShapeTool,
                  note='17 个形状工具均已接入；包含切线捕捉圆、半径圆弧。复杂 Z/M、拓扑及圆心辅助线仍有差异。')
        for name, tool in [('Pan', 'pan'), ('ZoomIn', 'zoomIn'), ('ZoomOut', 'zoomOut'),
                           ('SelectFeatures', 'selectFeatures'), ('Identify', 'identify'),
                           ('SelectPolygon', 'selectPolygon'), ('SelectFreehand', 'selectFreehand'), ('SelectRadius', 'selectRadius'),
                           ('Measure', 'measure'), ('MeasureArea', 'measureArea'),
                           ('MeasureBearing', 'measureBearing'), ('MeasureAngle', 'measureAngle'),
                           ('AddFeature', 'addFeature'),
                           ('MoveFeature', 'moveFeature'), ('MoveFeatureCopy', 'moveFeatureCopy'),
                           ('VertexTool', 'vertexTool'), ('VertexToolActiveLayer', 'vertexToolActiveLayer')]:
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[tool].setAction(action)
            requirement = 'editing' if tool == 'addFeature' else ('geometry-edit' if tool in ('moveFeature', 'moveFeatureCopy', 'vertexTool', 'vertexToolActiveLayer') else None)
            if tool.startswith('select'): requirement = 'vector'
            self.bind('mAction' + name, partial(self.setMapTool, tool), requirement)
        for name, tool in [('ReshapeFeatures', 'reshape'), ('SplitFeatures', 'split'),
                           ('SplitParts', 'splitParts'), ('AddRing', 'addRing'), ('AddPart', 'addPart'),
                           ('DeleteRing', 'deleteRing'), ('DeletePart', 'deletePart'), ('TrimExtendFeature', 'trimExtendFeature')]:
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[tool].setAction(action)
            requirement = 'polygon-edit' if tool in ('addRing', 'deleteRing') else 'part-edit' if tool == 'addPart' else 'geometry-edit' if tool == 'deletePart' else 'line-polygon-edit'
            self.bind('mAction' + name, partial(self.setMapTool, tool), requirement)
        sources = {'DataSourceManager': '', 'AddOgrLayer': 'ogr', 'AddRasterLayer': 'gdal',
                   'AddMeshLayer': 'mdal', 'AddPgLayer': 'postgres', 'AddSpatiaLiteLayer': 'spatialite',
                   'AddMssqlLayer': 'mssql', 'AddOracleLayer': 'oracle', 'AddHanaLayer': 'hana',
                   'AddWmsLayer': 'wms', 'AddWcsLayer': 'wcs', 'AddWfsLayer': 'WFS',
                   'AddXyzLayer': 'xyz', 'AddVectorTileLayer': 'vectortile', 'AddPointCloudLayer': 'pointcloud',
                   'AddDelimitedText': 'delimitedtext', 'AddVirtualLayer': 'virtual',
                   'NewVirtualLayer': 'virtual', 'AddAfsLayer': 'arcgisfeatureserver'}
        available = {p.providerKey().lower() for p in QgsGui.sourceSelectProviderRegistry().providers()}
        for name, provider in sources.items():
            if not provider or provider.lower() in available:
                self.bind('mAction' + name, partial(self.dataSourceManager, provider))
        urls = {'HelpContents': 'https://docs.qgis.org/3.34/en/docs/user_manual/',
                'HelpAPI': 'https://api.qgis.org/api/3.34/', 'HelpPyQgisAPI': 'https://qgis.org/pyqgis/3.34/',
                'QgisHomePage': 'https://qgis.org/', 'ReportaBug': 'https://github.com/qgis/QGIS/issues',
                'NeedSupport': 'https://qgis.org/resources/support/', 'Donate': 'https://qgis.org/funding/donate/',
                'GetInvolved': 'https://qgis.org/community/get-involved/'}
        for name, url in urls.items(): self.bind('mAction' + name, partial(QDesktopServices.openUrl, QUrl(url)))
        self.bind('mActionSponsors', self.sponsors)
        self.bind('mActionCustomization', lambda: self.mCustomization.openDialog(),
                  note='原版界面自定义表单；菜单/工具栏/面板/状态栏/浏览器/对话框控件，搜索、全选、INI 导入导出、应用/重置/取消，重启应用配置。')
        self.bind('actionActionCatchForCustomization', lambda: self.mCustomization.toggleCatch(),
                  note='Ctrl+M 切换非模态自定义窗口的控件捕获；定位配置树，拦截原操作，临时高亮且不改控件样式。')
        self.actionActionCatchForCustomization.setShortcutContext(Qt.ApplicationShortcut)
        self.addAction(self.actionActionCatchForCustomization)
        self.mActionAddLayerSeparator.setVisible(False)
        self.mActionAddLayerSeparator.setToolTip('添加图层扩展动作的插入位置')
        self.mImplementedActions['mActionAddLayerSeparator'] = {'handler': 'insertAddLayerAction/removeAddLayerAction', 'note': '原版隐藏插入锚点，供插件注册添加图层动作；本身不是可执行命令。'}
        self.bind('mActionCheckQgisVersion', self.checkQgisVersion)
        for name in ('Title', 'Copyright', 'Image', 'NorthArrow', 'ScaleBar'):
            note = '原版 UI、应用/取消、画布覆盖层、位置/边距/单位、工程保存恢复、PNG/JPEG/PDF 装饰导出。'
            if name == 'Image': note += 'HTTP(S) 异步加载、base64/data URI、将本地/网络图片嵌入工程。'
            self.bind('mActionDecoration' + name, self.mDecorations[name].run, note=note)
        self.bind('mActionDecorationGrid', self.mDecorations['Grid'].run,
                  note='原版网格表单、线/标记符号、间隔/偏移、范围/栅格像元取值、四种坐标标注方向；原生网格渲染、工程保存及地图导出。')
        self.bind('mActionDecorationLayoutExtent', self.mDecorations['LayoutExtent'].run,
                  note='原版表单、已打开布局地图的范围及名称、符号/文本格式、跨 CRS 与旋转；布局变化同步、工程保存及地图导出。')
        self.bind('mActionNewReport', self.newReport, note='原生报表树、静态/字段分组章节与原版配置表单；嵌套分组、排序、独立页眉/正文/页脚开关、空组显示策略、章节移动/升降级/复制/删除、布局编辑、PDF 与 QGZ 保存。')
        self.bind('mActionElevationProfile', self.createElevationProfile, note='原生剖面画布、高程图层过滤/图例筛选/符号提示、勾选状态保存恢复、内部排序/跨树复制拖入、绘制/选中线/地图拾取、偏移、识别、测量及裁剪、捕捉与地图联动、十种单位、轴比例与 X 轴缩放、原版图片/PDF 导出设置表单及三类数据导出已接入；图层树核心检查通过，整体交互和导出结果待统一调试。')
        self.mActionModifyAnnotation.setCheckable(True)
        self.mMapToolActionGroup.addAction(self.mActionModifyAnnotation)
        self.mMapTools['modifyAnnotation'].setAction(self.mActionModifyAnnotation)
        self.bind('mActionModifyAnnotation', lambda: self.setMapTool('modifyAnnotation'), note='按渲染边界距离和 Z 顺序悬停拾取；原生 CAD、节点与几何预览、点击移动/确认、Esc/右键取消、节点增删、方向键移动及旋转画布换算；同步属性面板和删除清理。')
        self.bind('mActionAbout', self.about)
        self.bind('mActionEmbedLayers', self.embedLayers, note='原生组嵌入、QGS/QGZ 选择树与引用保存；3.34 未导出单图层嵌入接口，该分支仍未移植。')
        self.bind('mActionCustomProjection', self.customProjection, note='原版 CRS 表单及原生定义控件；WKT/PROJ 编辑、校验、增加/修改/批量删除、应用/取消、用户 CRS 注册表持久化。独立窗口承载，整体 Options 仍暂停。')
        self.bind('mMainAnnotationLayerProperties', lambda: self.showLayerProperties(self.mProject.mainAnnotationLayer()), note='原版三页属性 UI、插件页面工厂/位置提示/同步/应用、QML/默认样式、动态样式新增/移除/重命名/切换及取消恢复已接入；本批插件页面和样式菜单待统一运行调试。')
        for name in ('TextAnnotation', 'SvgAnnotation', 'HtmlAnnotation', 'FormAnnotation'):
            key = name[0].lower() + name[1:]
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[key].setAction(action)
            self.bind('mAction' + name, partial(self.setMapTool, key), note='原生注记对象与画布项；点击创建，拖动/缩放，双击或右键编辑；原版属性表单、工程保存恢复。')
        for name, key, note in [
            ('RotatePointSymbols', 'rotatePointSymbols', '原生渲染器符号拾取与预览；旋转字段写入，Ctrl 15°，撤销和取消。'),
            ('OffsetPointSymbol', 'offsetPointSymbol', '原生符号预览；按偏移单位及符号角度计算字段值，撤销和取消。'),
        ]:
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[key].setAction(action)
            self.bind('mAction' + name, partial(self.setMapTool, key), 'point-symbol-edit', note=note)
        labelNotes = {
            'PinLabels': '固定/解除固定标注和图表；Shift 解除、Ctrl 切换；字段/辅助存储与撤销。',
            'ShowHideLabels': '当前图层点击/框选显隐；点击要素恢复标注/图表，Shift 框选隐藏；规则 provider。',
            'MoveLabel': '两次点击移动；XY/点字段、图表、线锚点与脱离线、引线端点；Shift 角度约束、Delete 清除、Esc 取消。',
            'RotateLabel': '旋转预览；Ctrl 15°；角度单位转换；Delete 清除覆盖、Esc/右键取消。',
            'ChangeLabelProperties': '原版标注属性 UI，文字/字体/颜色/缓冲/位置/比例/引线/显隐；应用/确定/取消及辅助字段。',
        }
        for name, note in labelNotes.items():
            key = name[0].lower() + name[1:]
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[key].setAction(action)
            self.bind('mAction' + name, partial(self.setMapTool, key), 'label', note=note)
            action.setToolTip(note)
        self.bind('mActionShowPinnedLabels', self.showPinnedLabels, signal='toggled', note='高亮已固定的标注、图表和引线端点；不会自动固定标注。请先固定或移动标注。绿色表示图层正在编辑，蓝色表示未编辑。')
        self.bind('mActionShowUnplacedLabels', self.showUnplacedLabels, signal='toggled', note='显示因冲突等原因未放置的标注，默认用红色绘制；没有未放置标注时画面不会变化。工程设置同步到所有地图画布。')
        self.mActionShowPinnedLabels.setToolTip('高亮固定标注、图表和引线端点')
        self.mActionShowUnplacedLabels.setToolTip('显示未放置标注；可用移动工具手动放置')
        self.mProject.labelingEngineSettingsChanged.connect(self.syncLabelingEngineActions)
        self.mProject.layersRemoved.connect(self.updateLabelToolButtons)
        self.syncLabelingEngineActions()
        self.bind('mActionPasteAsNewVector', self.pasteAsNewVector, note='临时图层不加入工程；原生导出对话框与后台写入，支持字段/显示值/CRS 等选项。')
        self.bind('mActionCreateAnnotationLayer', self.createAnnotationLayer, note='原生注记图层、唯一名称、工程 CRS、插入图层树顶端；注记绘制与编辑工具另列未完成。')
        for name, tool, requirement in [('FillRing', 'fillRing', 'polygon-edit'), ('FeatureAction', 'featureAction', 'vector')]:
            action = getattr(self, 'mAction' + name)
            action.setCheckable(True)
            self.mMapToolActionGroup.addAction(action)
            self.mMapTools[tool].setAction(action)
            self.bind('mAction' + name, partial(self.setMapTool, tool), requirement)
        self.menuAllEdits = QMenu('当前编辑', self)
        self.menuAllEdits.setObjectName('AllEditsMenu')
        for name in ('SaveEdits', 'RollbackEdits', 'CancelEdits', None, 'SaveAllEdits', 'RollbackAllEdits', 'CancelAllEdits'):
            if name is None: self.menuAllEdits.addSeparator()
            else: self.menuAllEdits.addAction(getattr(self, 'mAction' + name))
        self.mActionAllEdits.setMenu(self.menuAllEdits)
        self.mImplementedActions['mActionFillRing']['note'] = 'CAD 捕获后添加并填充；Shift 点击现有内环；取消表单完整回滚。复杂曲线/ZM/跨图层拓扑仍待验收。'
        self.mImplementedActions['mActionFeatureAction']['note'] = '画布/插件单要素动作选择菜单、默认动作互斥切换、图标提示同步、编辑状态过滤、重叠要素菜单和点击上下文；Python 动作由独立宿主执行，插件获得消息栏上下文。'
        self.mImplementedActions['mActionAllEdits'] = {'handler': 'menuAllEdits', 'note': '原版六项编辑子菜单；前三项使用图层树选中集。'}
        self.bind('mActionMapTips', lambda: self.toggleMapTips(self.mActionMapTips.isChecked()), signal='toggled')
        self.mActionMapTips.setChecked(self.mSettings.value('qgis/enableMapTips', False, type=bool))
        self.toggleMapTips(self.mActionMapTips.isChecked())
        self.bind('mActionStatisticalSummary', lambda: self.mStatisticalSummaryDockWidget.setVisible(self.mActionStatisticalSummary.isChecked()), signal='toggled')
        self.mStatisticalSummaryDockWidget.visibilityChanged.connect(self.mActionStatisticalSummary.setChecked)
        from .georeferencer.qgsgeorefmainwindow import QgsGeoreferencerMainWindow
        self.mGeoreferencer = QgsGeoreferencerMainWindow(self)
        self.bind('mActionShowGeoreferencer', self.showGeoreferencer,
                  note='原版地理配准窗口及 24 个 Action；栅格/矢量配准与脚本、控制点、输出及画布联动。栅格投影变换、PDF 和停靠仍未完成。')
        self.openProfileFolderAction = QAction('打开当前用户配置文件夹', self)
        self.openProfileFolderAction.setObjectName('openProfileFolderAction')
        self.openProfileFolderAction.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(QgsApplication.qgisSettingsDirPath())))
        self.mConfigMenu = self.mSettingsMenu.addMenu('用户配置')
        self.mConfigMenu.addAction(self.openProfileFolderAction)
        self.mDynamicActions['qgisapp:openProfileFolderAction'] = dict(action=self.openProfileFolderAction,
            handler='openProfileFolder', note='打开当前独立应用实际使用的 QGIS 配置目录。', inInterface=True)
        for name in self.mImplementedActions:
            action = getattr(self, name)
            action.setToolTip(self.mImplementedActions[name].get('note') or action.text())
            shortcut = self.mSettings.value('PythonDesktop/shortcuts/' + name, None)
            if shortcut is not None: action.setShortcut(QKeySequence(shortcut))

    def createToolBars(self):
        self.mDigitizeToolBar.insertAction(self.mActionToggleEditing, self.mActionAllEdits)
        self.mDigitizeToolBar.widgetForAction(self.mActionAllEdits).setPopupMode(QToolButton.InstantPopup)
        self.mAttributesToolBar.insertAction(self.mActionMapTips, self.mActionFeatureAction)
        self.mFeatureActionMenu = QMenu(self)
        self.mFeatureActionMenu.aboutToShow.connect(self.refreshFeatureActions)
        QgsGui.mapLayerActionRegistry().changed.connect(self.refreshActionFeatureAction)
        self.mActionFeatureAction.setMenu(self.mFeatureActionMenu)
        self.mAttributesToolBar.widgetForAction(self.mActionFeatureAction).setPopupMode(QToolButton.MenuButtonPopup)
        cadAction = self.mAdvancedDigitizingDockWidget.enableAction()
        self.mAdvancedDigitizeToolBar.insertAction(self.mAdvancedDigitizeToolBar.actions()[0], cadAction)
        cadAction.triggered.connect(lambda checked: self.mAdvancedDigitizingDockWidget.show() if checked else None)
        self.createToolButton(self.mAdvancedDigitizeToolBar, [self.mActionMoveFeature, self.mActionMoveFeatureCopy], self.mActionRotateFeature, 'ActionMoveFeatureTool', 'UI/defaultMoveTool')
        vertexToolButton = self.createToolButton(self.mDigitizeToolBar, [self.mActionVertexToolActiveLayer, self.mActionVertexTool], self.mActionMultiEditAttributes, 'ActionVertexTool', 'UI/defaultVertexTool')
        vertexToolButton.menu().addSeparator()
        vertexToolButton.menu().addAction(self.mVertexEditorDock.toggleViewAction())
        self.mSelectionToolBar.addAction(self.mActionOpenTable)
        self.createToolButton(self.mSelectionToolBar, [self.mActionSelectByForm, self.mActionSelectByExpression, self.mActionSelectAll, self.mActionInvertSelection], self.mActionOpenTable, 'ActionSelection', 'UI/selectionTool')
        self.mSelectToolButton = self.createToolButton(self.mSelectionToolBar, [self.mActionSelectFeatures, self.mActionSelectPolygon, self.mActionSelectFreehand, self.mActionSelectRadius], self.mSelectionToolBar.actions()[0], 'ActionSelect', 'UI/selectTool', [1, 3, 4, 2])
        self.createToolButton(self.mSelectionToolBar, [self.mActionDeselectAll, self.mActionDeselectActiveLayer], self.mActionOpenTable, 'ActionDeselection', 'UI/deselectionTool')
        self.mMeasureToolButton = self.createToolButton(self.mAttributesToolBar, [self.mActionMeasure, self.mActionMeasureArea, self.mActionMeasureBearing, self.mActionMeasureAngle], self.mActionMapTips, 'ActionMeasure', 'UI/measureTool')
        annotationLayerToolButton = QToolButton(self.mAnnotationsToolBar)
        annotationLayerToolButton.setPopupMode(QToolButton.MenuButtonPopup)
        annotationLayerMenu = QMenu(annotationLayerToolButton)
        annotationLayerMenu.addAction(self.mActionCreateAnnotationLayer)
        annotationLayerMenu.addAction(self.mMainAnnotationLayerProperties)
        annotationLayerToolButton.setMenu(annotationLayerMenu)
        annotationLayerToolButton.setDefaultAction(self.mActionCreateAnnotationLayer)
        self.mAnnotationsToolBar.insertWidget(self.mActionModifyAnnotation, annotationLayerToolButton).setObjectName('ActionAnnotationLayer')
        self.mAnnotationToolButton = self.createToolButton(self.mAnnotationsToolBar, [self.mActionTextAnnotation, self.mActionFormAnnotation, self.mActionHtmlAnnotation, self.mActionSvgAnnotation], None, 'ActionAnnotation', 'UI/annotationTool')
        self.mAnnotationsItemInsertBefore = self.mAnnotationsToolBar.insertSeparator(self.mAnnotationsToolBar.actions()[-1])
        registry = QgsGui.annotationItemGuiRegistry()
        if not registry.itemMetadataIds(): registry.addDefaultItems()
        for metadataId in registry.itemMetadataIds(): self.annotationItemTypeAdded(metadataId)
        registry.typeAdded.connect(self.annotationItemTypeAdded)
        self.mMapToolsDigitizingTechniqueManager.setupToolBars()
        self.mMeshEditTool.setupActions()
        for toolbar in self.findChildren(QToolBar):
            size = self.mSettings.value('qgis/toolbarIconSize', 24, type=int)
            toolbar.setIconSize(QSize(size, size))
            if toolbar.parent() is not self: continue
            self.mToolbarMenu.addAction(toolbar.toggleViewAction())
            if toolbar.objectName() in ('mDigitizeToolBar', 'mAdvancedDigitizeToolBar', 'mSnappingToolBar'):
                toolbar.show()
            elif not any(a.isEnabled() for a in toolbar.actions()):
                toolbar.hide()
        self.mHelpToolBar.hide()
        if not self.mWebToolBar.actions(): self.mWebToolBar.hide()
        self.mDatabaseToolBar.hide()

    def createToolButton(self, toolbar, actions, before, name, key, values=None):
        button = QToolButton(toolbar)
        button.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(button)
        button.setMenu(menu)
        for action in actions:
            toolbar.removeAction(action)
            menu.addAction(action)
        values = values or list(range(len(actions)))
        value = self.mSettings.value(key, values[0], type=int)
        button.setDefaultAction(actions[values.index(value) if value in values else 0])
        def triggered(action):
            if action not in actions: return
            button.setDefaultAction(action)
            self.mSettings.setValue(key, values[actions.index(action)])
        button.triggered.connect(triggered)
        toolbar.insertWidget(before, button).setObjectName(name)
        return button

    def annotationItemTypeAdded(self, metadataId):
        registry = QgsGui.annotationItemGuiRegistry()
        metadata = registry.itemMetadata(metadataId)
        if metadataId in self.mAnnotationItemActions or metadata.flags() & Qgis.AnnotationItemGuiFlag.FlagNoCreationTools: return
        action = QAction(metadata.creationIcon(), '创建' + metadata.visibleName(), self)
        action.setObjectName('mAction' + metadata.visibleName().replace(' ', ''))
        action.setCheckable(True)
        action.setData(metadataId)
        action.setToolTip('创建' + metadata.visibleName() + '；完成后在图层样式面板编辑属性')
        self.mMapToolActionGroup.addAction(action)
        self.mAnnotationsToolBar.insertAction(self.mAnnotationsItemInsertBefore, action)
        self.mAnnotationItemActions[metadataId] = action
        self.mDynamicActions['annotation:' + metadata.type()] = {
            'action': action, 'handler': 'annotationItemTypeAdded', 'toolbar': 'mAnnotationsToolBar',
            'note': '原生注册表/捕获工具创建注记项，加入目标注记图层；原生内容/符号属性页、渲染与工程保存。节点修改单列于 Modify Annotations。'}
        def activated(checked):
            if not checked: return
            interface = self.mAnnotationItemTools.get(metadataId)
            if interface is None:
                interface = metadata.createMapTool(self.mMapCanvas, self.mAdvancedDigitizingDockWidget)
                if interface is None:
                    action.setChecked(False)
                    self.mMessageBar.pushWarning('注记', '该注册类型未提供创建工具')
                    return
                self.mAnnotationItemTools[metadataId] = interface
                tool = interface.mapTool()
                tool.setAction(action)
                interface.handler().itemCreated.connect(lambda: self.annotationItemCreated(metadataId))
            self.mMapCanvas.setMapTool(interface.mapTool())
        action.toggled.connect(activated)

    def annotationItemCreated(self, metadataId):
        interface = self.mAnnotationItemTools[metadataId]
        item = interface.handler().takeCreatedItem()
        if item is None: return
        layer = interface.handler().targetLayer()
        itemId = layer.addItem(item)
        QgsGui.annotationItemGuiRegistry().newItemAddedToLayer(metadataId, layer.item(itemId), layer)
        layer.triggerRepaint()
        self.mProject.setDirty(True)
        self.mapStyleDock(True)
        self.mLayerStylingWidget.setAnnotationItem(layer, itemId)
        self.mMapCanvas.refresh()
    def setCaptureTechnique(self, technique):
        self.mMapToolsDigitizingTechniqueManager.setCaptureTechnique(technique)

    def initProcessing(self):
        from processing.ProcessingPlugin import ProcessingPlugin
        self.mProcessingPlugin = ProcessingPlugin(self.mQgisInterface)
        registry = QgsApplication.processingRegistry()
        self.mGpsAlgorithmsRemoved = [a.id() for a in registry.algorithms()
                                      if 'gps' in a.id().lower() or 'gpx' in a.id().lower()]
        self.mProcessingPlugin.initGui()
        from python.plugins.processing.gui.AlgorithmLocatorFilter import AlgorithmLocatorFilter
        self.mQgisInterface.deregisterLocatorFilter(self.mProcessingPlugin.locator_filter)
        self.mProcessingPlugin.locator_filter = AlgorithmLocatorFilter()
        self.mQgisInterface.registerLocatorFilter(self.mProcessingPlugin.locator_filter)
        self.excludeGpsFromToolbox()

    def excludeGpsFromToolbox(self):
        from qgis.PyQt.QtCore import QModelIndex
        tree = self.mProcessingPlugin.toolbox.algorithmTree
        def hideRows(parent=QModelIndex()):
            model = tree.model()
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                algorithm = tree.algorithmForIndex(index)
                forbidden = algorithm is not None and ('gps' in algorithm.id().lower() or 'gpx' in algorithm.id().lower())
                tree.setRowHidden(row, parent, forbidden)
                if model.hasChildren(index): hideRows(index)
        self._hideGpsRows = hideRows
        tree.model().modelReset.connect(lambda: QTimer.singleShot(0, hideRows))
        tree.model().rowsInserted.connect(lambda *args: QTimer.singleShot(0, hideRows))
        tree.model().layoutChanged.connect(lambda *args: QTimer.singleShot(0, hideRows))
        tree.expanded.connect(lambda index: hideRows(index))
        hideRows()

    def activeLayer(self): return self.mLayerTreeView.currentLayer()
    def setActiveLayer(self, layer):
        if layer is None: return False
        self.mLayerTreeView.setCurrentLayer(layer)
        self.mMapCanvas.setCurrentLayer(layer)
        return True
    def vectorLayer(self, layer=None):
        layer = layer or self.activeLayer()
        return layer if isinstance(layer, QgsVectorLayer) else None
    def mapCanvases(self): return [self.mMapCanvas] + self.mAdditionalCanvases

    def layersAdded(self, layers):
        for layer in layers:
            layer.styleChanged.connect(self.updateLabelToolButtons)
            if isinstance(layer, QgsVectorLayer):
                layer.editingStarted.connect(self.updateActionState)
                layer.editingStopped.connect(self.updateActionState)
                layer.editingStarted.connect(self.mMapTools['pinLabels'].updatePinnedLabels)
                layer.editingStopped.connect(self.mMapTools['pinLabels'].updatePinnedLabels)
                layer.layerModified.connect(self.updateActionState)
                layer.selectionChanged.connect(self.updateActionState)
                layer.undoStack().canUndoChanged.connect(self.updateActionState)
                layer.undoStack().canRedoChanged.connect(self.updateActionState)
            elif isinstance(layer, QgsMeshLayer):
                layer.undoStack().canUndoChanged.connect(self.updateActionState)
                layer.undoStack().canRedoChanged.connect(self.updateActionState)
                layer.undoStack().indexChanged.connect(lambda index, mesh=layer: self.mMeshEditTool.onEdit() if self.activeLayer() is mesh else None)
        if layers:
            self.setActiveLayer(layers[-1])
        if len(self.mProject.mapLayers()) == len(layers) and layers:
            QTimer.singleShot(0, self.zoomToLayerExtent)

    def layersWillBeRemoved(self, ids):
        if self.mMeshEditTool.mCurrentLayer and self.mMeshEditTool.mCurrentLayer.id() in ids:
            if self.mMapCanvas.mapTool() is self.mMeshEditTool: self.mMapCanvas.setMapTool(self.mMapTools['pan'])
            self.mMeshEditTool.mCurrentLayer = None
            self.mMeshEditTool.mSelectedVertices.clear()
            self.mMeshEditTool.mSelectedFaces.clear()
            if self.mMeshEditTool.mTransformDockWidget: self.mMeshEditTool.mTransformDockWidget.hide()
        self.clearMapTip()
        for key in ('rotatePointSymbols', 'offsetPointSymbol'): self.mMapTools[key].cancel()
        for key in ('pinLabels', 'showHideLabels', 'moveLabel', 'rotateLabel', 'changeLabelProperties'):
            self.mMapTools[key].cancel()
        self.mMapTools['pinLabels'].removePinnedHighlights()
        for key in ('vertexTool', 'vertexToolActiveLayer'):
            tool = self.mMapTools[key]
            if tool.mVertex and tool.mVertex[0].id() in ids: tool.cancel()
        if hasattr(self, 'mLayerStylingWidget') and self.mLayerStylingWidget.mLayer and self.mLayerStylingWidget.mLayer.id() in ids:
            self.mLayerStylingWidget.setLayer(None)
        for window in list(self.mWindows):
            if not sip.isdeleted(window) and hasattr(window, 'mLayer') and window.mLayer.id() in ids:
                window.close()
                if hasattr(window, 'mDockableWidgetHelper'):
                    window.mDockableWidgetHelper.dispose()
                    self.mWindows.remove(window)
                    sip.delete(window)
        self.mUndoWidget.setStack(None)

    def activateLayer(self, layer):
        self.clearMapTip()
        self.mStatisticalSummaryDockWidget.setLayer(layer)
        self.mMapCanvas.setCurrentLayer(layer)
        self.mUndoWidget.setStack(layer.undoStack() if isinstance(layer, (QgsVectorLayer, QgsMeshLayer)) else None)
        self.mDigitizeToolBar.show()
        self.updateActionState()
        self.setTheme()
        if hasattr(self, 'mLayerStylingWidget'): self.mLayerStylingWidget.setLayer(layer)
        self.mLegendExpressionFilterButton.blockSignals(True)
        self.mLegendExpressionFilterButton.setVectorLayer(self.vectorLayer())
        node = self.mLayerTreeView.currentNode()
        from qgis.core import QgsLayerTreeUtils
        expression = QgsLayerTreeUtils.legendFilterByExpression(node) if isinstance(node, QgsLayerTreeLayer) else ''
        if isinstance(expression, tuple): expression = expression[0]
        self.mLegendExpressionFilterButton.setExpressionText(expression)
        self.mLegendExpressionFilterButton.setChecked(bool(expression and node.customProperty('legend/expressionFilterEnabled', False)))
        self.mLegendExpressionFilterButton.blockSignals(False)

    def updateActionState(self, *args):
        layer = self.activeLayer()
        vector = self.vectorLayer()
        for name, requirement in self.mRequirements.items():
            enabled = bool(layer) if requirement == 'layer' else bool(vector)
            if requirement == 'editing': enabled = bool(vector and vector.isEditable())
            if requirement == 'raster': enabled = isinstance(layer, QgsRasterLayer)
            if requirement == 'mesh': enabled = isinstance(layer, QgsMeshLayer) and layer.isValid() and not layer.isEditable()
            if requirement == 'capture-technique':
                from qgis.gui import QgsMapToolCapture
                tool = self.mMapCanvas.mapTool()
                action = getattr(self, name)
                enabled = isinstance(tool, QgsMapToolCapture) and tool.supportsTechnique(action.data())
                if enabled:
                    action.setChecked(tool.currentCaptureTechnique() == action.data())
            if requirement == 'point-symbol-edit':
                enabled = bool(vector and vector.isEditable() and vector.geometryType() == Qgis.GeometryType.Point and vector.dataProvider().capabilities() & QgsVectorDataProvider.ChangeAttributeValues)
            if requirement == 'geometry-edit': enabled = bool(vector and vector.isEditable() and vector.isSpatial() and vector.dataProvider().capabilities() & QgsVectorDataProvider.ChangeGeometries)
            if requirement in ('line-polygon-edit', 'polygon-edit', 'part-edit'):
                enabled = bool(vector and vector.isEditable() and vector.isSpatial() and vector.dataProvider().capabilities() & QgsVectorDataProvider.ChangeGeometries)
                if enabled and requirement == 'line-polygon-edit': enabled = vector.geometryType() in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry)
                if enabled and requirement == 'polygon-edit': enabled = vector.geometryType() == QgsWkbTypes.PolygonGeometry
                if enabled and requirement == 'part-edit': enabled = vector.selectedFeatureCount() == 1
            getattr(self, name).setEnabled(enabled)
        if vector:
            caps = vector.dataProvider().capabilities()
            selected = vector.selectedFeatureCount()
            for name in ('mActionRotateFeature', 'mActionScaleFeature', 'mActionSimplifyFeature', 'mActionReverseLine', 'mActionOffsetCurve'):
                action = getattr(self, name)
                action.setEnabled(action.isEnabled() and selected > 0)
            for name in ('mActionReverseLine', 'mActionOffsetCurve'):
                action = getattr(self, name)
                action.setEnabled(action.isEnabled() and vector.geometryType() == QgsWkbTypes.LineGeometry)
            self.mActionSimplifyFeature.setEnabled(self.mActionSimplifyFeature.isEnabled() and vector.geometryType() != QgsWkbTypes.PointGeometry)
            self.mActionMergeFeatures.setEnabled(vector.isEditable() and selected >= 2 and bool(caps & QgsVectorDataProvider.DeleteFeatures) and bool(caps & QgsVectorDataProvider.ChangeGeometries))
            self.mActionMergeFeatureAttributes.setEnabled(vector.isEditable() and selected >= 2 and bool(caps & QgsVectorDataProvider.ChangeAttributeValues))
            self.mActionToggleEditing.setEnabled(vector.isEditable() or bool(caps & QgsVectorDataProvider.EditingCapabilities) and not vector.readOnly())
            self.mActionAddFeature.setEnabled(vector.isEditable() and bool(caps & QgsVectorDataProvider.AddFeatures))
            self.mActionMoveFeatureCopy.setEnabled(vector.isEditable() and vector.isSpatial() and bool(caps & QgsVectorDataProvider.AddFeatures))
            for name in ('mActionDeleteSelected', 'mActionCutFeatures'):
                getattr(self, name).setEnabled(vector.isEditable() and vector.selectedFeatureCount() > 0 and bool(caps & QgsVectorDataProvider.DeleteFeatures))
            self.mActionUndo.setEnabled(vector.undoStack().canUndo())
            self.mActionRedo.setEnabled(vector.undoStack().canRedo())
        self.mActionToggleEditing.blockSignals(True)
        editing = self.editableLayers()
        selectedEditing = self.editableLayers(selected=True)
        self.mActionAllEdits.setEnabled(bool(editing))
        self.mActionCancelAllEdits.setEnabled(bool(editing))
        for name in ('SaveAllEdits', 'RollbackAllEdits'): getattr(self, 'mAction' + name).setEnabled(any(layer.isModified() for layer in editing))
        self.mActionCancelEdits.setEnabled(bool(selectedEditing))
        for name in ('SaveEdits', 'RollbackEdits'): getattr(self, 'mAction' + name).setEnabled(any(layer.isModified() for layer in selectedEditing))
        self.mActionFillRing.setEnabled(self.mActionFillRing.isEnabled() and bool(vector and vector.dataProvider().capabilities() & QgsVectorDataProvider.AddFeatures))
        self.mActionPasteAsNewVector.setEnabled(bool(self.mClipboard and self.mClipboard[2]))
        self.mActionToggleEditing.setChecked(bool(vector and vector.isEditable()))
        self.mActionToggleEditing.blockSignals(False)
        self.updateLabelToolButtons()
        self.refreshActionFeatureAction()
        tool = self.mMapCanvas.mapTool()
        if tool and tool.action() and tool.action().objectName() in self.mRequirements and not tool.action().isEnabled():
            self.mMapCanvas.setMapTool(self.mMapTools['pan'])
        if hasattr(self, 'mMapToolsDigitizingTechniqueManager'):
            self.mMapToolsDigitizingTechniqueManager.updateActions()
        if hasattr(self, 'mMeshEditTool'): self.mMeshEditTool.updateActions()

    def fullHistogramStretch(self): self.histogramStretch(False, QgsRasterMinMaxOrigin.MinMax)
    def localHistogramStretch(self): self.histogramStretch(True, QgsRasterMinMaxOrigin.MinMax)
    def fullCumulativeCutStretch(self): self.histogramStretch(False, QgsRasterMinMaxOrigin.CumulativeCut)
    def localCumulativeCutStretch(self): self.histogramStretch(True, QgsRasterMinMaxOrigin.CumulativeCut)
    def histogramStretch(self, visibleAreaOnly, limits):
        layer = self.activeLayer()
        if not isinstance(layer, QgsRasterLayer): return
        extent = self.mMapCanvas.mapSettings().outputExtentToLayerExtent(layer, self.mMapCanvas.extent()) if visibleAreaOnly else QgsRectangle()
        layer.setContrastEnhancement(QgsContrastEnhancement.StretchToMinimumMaximum, limits, extent)
        layer.triggerRepaint()
        self.mProject.setDirty(True)
    def increaseBrightness(self): self.adjustBrightnessContrast(self.rasterAdjustmentStep())
    def decreaseBrightness(self): self.adjustBrightnessContrast(-self.rasterAdjustmentStep())
    def increaseContrast(self): self.adjustBrightnessContrast(self.rasterAdjustmentStep(), False)
    def decreaseContrast(self): self.adjustBrightnessContrast(-self.rasterAdjustmentStep(), False)
    def increaseGamma(self): self.adjustGamma(self.rasterAdjustmentStep() / 10)
    def decreaseGamma(self): self.adjustGamma(-self.rasterAdjustmentStep() / 10)
    def rasterAdjustmentStep(self): return 10 if QgsApplication.keyboardModifiers() & Qt.ShiftModifier else 1
    def selectedRasterLayers(self):
        return [layer for layer in (self.mLayerTreeView.selectedLayers() or [self.activeLayer()]) if isinstance(layer, QgsRasterLayer)]
    def adjustBrightnessContrast(self, delta, updateBrightness=True):
        for layer in self.selectedRasterLayers():
            filter = layer.brightnessFilter()
            if updateBrightness: filter.setBrightness(max(-255, min(255, filter.brightness() + delta)))
            else: filter.setContrast(max(-100, min(100, filter.contrast() + delta)))
            layer.triggerRepaint()
            self.mProject.setDirty(True)
    def adjustGamma(self, delta):
        for layer in self.selectedRasterLayers():
            filter = layer.brightnessFilter()
            filter.setGamma(max(0.1, min(10.0, filter.gamma() + delta)))
            layer.triggerRepaint()
            self.mProject.setDirty(True)

    def showRasterCalculator(self):
        from .qgsrastercalcdialog import QgsRasterCalcDialog
        layer = self.activeLayer()
        QgsRasterCalcDialog(layer if isinstance(layer, QgsRasterLayer) else None, self).exec_()

    def dwgImport(self):
        from .dwg.qgsdwgimportdialog import QgsDwgImportDialog
        dialog = QgsDwgImportDialog(self)
        try: return dialog.exec_()
        finally:
            dialog.clearPreview()
            dialog.deleteLater()

    def dxfExport(self):
        from .qgsdxfexportdialog import QgsDxfExportDialog
        dialog = QgsDxfExportDialog(self, self.mMapCanvas)
        if dialog.exec_(): self.mMessageBar.pushSuccess('DXF 导出', '已保存至 ' + dialog.saveFile())

    def newSpatialiteLayer(self):
        from .qgsnewspatialitelayerdialog import QgsNewSpatialiteLayerDialog
        dialog = QgsNewSpatialiteLayerDialog(self, self.mProject.crs())
        if dialog.exec_():
            self.mLayerTreeView.setCurrentLayer(dialog.mNewLayer)
            self.mBrowserModel.refresh()

    def newMeshLayer(self):
        from .mesh.qgsnewmeshlayerdialog import QgsNewMeshLayerDialog
        dialog = QgsNewMeshLayerDialog(self)
        if isinstance(self.activeLayer(), QgsMeshLayer): dialog.setSourceMeshLayer(self.activeLayer(), False)
        if dialog.exec_(): self.mLayerTreeView.setCurrentLayer(dialog.newLayer())

    def showMeshCalculator(self):
        layer = self.activeLayer()
        if not isinstance(layer, QgsMeshLayer) or not layer.isValid():
            self.mMessageBar.pushWarning('网格计算器', '请先选择网格图层')
            return
        if layer.isEditable():
            self.mMessageBar.pushWarning('网格计算器', '请先结束网格编辑')
            return
        from .mesh.qgsmeshcalculatordialog import QgsMeshCalculatorDialog
        if QgsMeshCalculatorDialog(layer, self).exec_(): self.mMessageBar.pushSuccess('网格计算器', '计算完成，结果组已加入当前网格图层')

    def zoomActualSize(self):
        layer = self.activeLayer()
        if not isinstance(layer, QgsRasterLayer): return
        center = self.mMapCanvas.extent().center()
        point = self.mMapCanvas.mapSettings().mapToLayerCoordinates(layer, center)
        rectangle = QgsRectangle(point.x(), point.y(), point.x() + abs(layer.rasterUnitsPerPixelX()), point.y() + abs(layer.rasterUnitsPerPixelY()))
        transform = QgsCoordinateTransform(layer.crs(), self.mMapCanvas.mapSettings().destinationCrs(), self.mProject)
        pixel = transform.transformBoundingBox(rectangle)
        if self.mMapCanvas.mapUnitsPerPixel() > 0:
            self.mMapCanvas.zoomByFactor(pixel.width() / self.mMapCanvas.mapUnitsPerPixel())
    def setPreviewMode(self, mode):
        self.mMapCanvas.setPreviewModeEnabled(mode is not None)
        if mode is not None: self.mMapCanvas.setPreviewMode(mode)
    def selectByForm(self):
        from qgis.gui import QgsAttributeForm, QgsAttributeEditorContext
        layer = self.vectorLayer()
        if not layer: return
        dialog = QDialog(self)
        dialog.setWindowTitle('按表单选择 — ' + layer.name())
        layout = QVBoxLayout(dialog)
        form = QgsAttributeForm(layer, QgsFeature(layer.fields()), QgsAttributeEditorContext(), dialog)
        form.setMode(QgsAttributeEditorContext.SearchMode)
        layout.addWidget(form)
        dialog.resize(640, 480)
        dialog.exec_()
    def modifyAttributesOfSelectedFeatures(self):
        from qgis.gui import QgsDualView
        layer = self.vectorLayer()
        if not layer or not layer.isEditable(): return
        if not layer.selectedFeatureCount():
            self.mMessageBar.pushInfo('批量编辑', '请先选择需要修改的要素')
            return
        table = self.attributeTable(QgsAttributeTableFilterModel.ShowSelected, layer=layer)
        table.mMainView.setView(QgsDualView.AttributeEditor)
        table.mMainView.setMultiEditEnabled(True)

    def updateWindowTitle(self, *args):
        self.setWindowTitle(f"{'*' if self.mProject.isDirty() else ''}{self.mProject.baseName() or '未命名工程'} — QGIS Python 3.34.10")

    def updateStatusBar(self):
        self.mScaleWidget.setScale(self.mMapCanvas.scale())
        self.mCoordsEdit.coordinateDisplaySettingsChanged()
        self.updateCrsStatusBar()

    def userScale(self):
        self.mScaleWidget.userScale()

    def toggleLogMessageIcon(self, hasLogMessage):
        unread = hasLogMessage and not self.mLogDock.isVisible()
        self.mMessageButton.setIcon(QgsApplication.getThemeIcon('/mMessageLog.svg' if unread else '/mMessageLogRead.svg'))

    def addMapLayer(self, layer):
        if not layer or not layer.isValid():
            self.mMessageBar.pushCritical('加载失败', layer.source() if layer else '无效图层')
            return None
        added = self.mProject.addMapLayer(layer)
        self.setActiveLayer(added)
        self.updateActionState()
        return added

    def addVectorLayer(self, path, name='', provider='ogr'):
        if provider.lower() == 'gpx' or str(path).split('|')[0].lower().endswith('.gpx'):
            self.mMessageBar.pushWarning('GPS 已排除', '不加载 GPX 图层')
            return None
        return self.addMapLayer(QgsVectorLayer(path, name or Path(path).stem, provider))
    def addRasterLayer(self, path, name='', provider='gdal'): return self.addMapLayer(QgsRasterLayer(path, name or Path(path).stem, provider))
    def addMeshLayer(self, path, name='', provider='mdal'): return self.addMapLayer(QgsMeshLayer(path, name or Path(path).stem, provider))
    def addVectorTileLayer(self, path, name=''): return self.addMapLayer(QgsVectorTileLayer(path, name or '矢量瓦片'))
    def addPointCloudLayer(self, path, name='', provider='pdal'): return self.addMapLayer(QgsPointCloudLayer(path, name or Path(path).stem, provider))
    def addVectorLayers(self, paths, encoding='', dataSourceType='file'):
        return [self.addVectorLayer(path) for path in paths]
    def addRasterLayers(self, paths): return [self.addRasterLayer(path) for path in paths]
    def addLayerByType(self, layerType, uri, name, provider, *args):
        loaders = {QgsMapLayerType.VectorLayer: self.addVectorLayer,
                   QgsMapLayerType.RasterLayer: self.addRasterLayer, QgsMapLayerType.MeshLayer: self.addMeshLayer,
                   QgsMapLayerType.PointCloudLayer: self.addPointCloudLayer}
        if layerType == QgsMapLayerType.VectorTileLayer: return self.addVectorTileLayer(uri, name)
        if layerType in loaders: return loaders[layerType](uri, name, provider)
        self.mMessageBar.pushWarning('数据类型', f'尚未移植图层类型 {layerType}')

    def handleDropUriList(self, uris):
        for uri in uris:
            if uri.layerType == 'custom':
                for handler in self.mQgisInterface.mDropHandlers:
                    if handler.customUriProviderKey() == uri.providerKey: handler.handleCustomUriDrop(uri)
            else:
                kinds = {'vector': QgsMapLayerType.VectorLayer, 'raster': QgsMapLayerType.RasterLayer,
                         'mesh': QgsMapLayerType.MeshLayer, 'vector-tile': QgsMapLayerType.VectorTileLayer,
                         'point-cloud': QgsMapLayerType.PointCloudLayer}
                if uri.layerType in kinds:
                    self.addLayerByType(kinds[uri.layerType], uri.uri, uri.name, uri.providerKey)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or QgsMimeDataUtils.isUriList(event.mimeData()): event.acceptProposedAction()
    def dropEvent(self, event):
        if QgsMimeDataUtils.isUriList(event.mimeData()):
            self.handleDropUriList(QgsMimeDataUtils.decodeUriList(event.mimeData()))
        else:
            for url in event.mimeData().urls():
                if url.isLocalFile(): self.openFile(url.toLocalFile())
        event.acceptProposedAction()
    def openFile(self, path):
        if path.lower().endswith(('.qgs', '.qgz')): return self.addProject(path)
        if path.lower().endswith('.gpx'):
            self.mMessageBar.pushWarning('GPS 已排除', path)
            return
        for handler in self.mQgisInterface.mDropHandlers:
            if handler.handleFileDrop(path): return
        details = QgsProviderRegistry.instance().querySublayers(path)
        for detail in details:
            self.addMapLayer(detail.toLayer(QgsProviderSublayerOptions(self.mProject.transformContext())))

    def dataSourceManager(self, page=''):
        if self.mDataSourceManagerDialog is None:
            from .qgsdatasourcemanagerdialog import QgsDataSourceManagerDialog
            self.mDataSourceManagerDialog = QgsDataSourceManagerDialog(self)
        self.mDataSourceManagerDialog.openPage(page)

    def saveDirty(self):
        for layer in list(self.mProject.mapLayers().values()):
            if isinstance(layer, QgsVectorLayer) and layer.isEditable():
                if not self.mVectorLayerTools.stopEditing(layer): return False
            elif isinstance(layer, QgsMeshLayer) and layer.isEditable():
                if not self.mMeshEditTool.stopEditing(layer): return False
        if self.mProject.isDirty():
            answer = QMessageBox.question(self, '保存工程', '工程已修改。是否保存？',
                                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if answer == QMessageBox.Cancel: return False
            if answer == QMessageBox.Save: return self.fileSave()
        return True
    def fileNew(self):
        if not self.saveDirty(): return False
        self.mProject.clear()
        self.mProject.setCrs(QgsCoordinateReferenceSystem(self.mSettings.value('projections/defaultProjectCrs', 'EPSG:4326')))
        self.mProject.setEllipsoid('WGS84')
        self.mMapCanvas.setExtent(QgsRectangle(-180, -90, 180, 90))
        self.mMapCanvas.refresh()
        self.mProject.setDirty(False)
        self.mQgisInterface.newProjectCreated.emit()
        return True
    def fileNewBlank(self): return self.fileNew()
    def fileClose(self): return self.fileNew()
    def fileExit(self): self.close()
    def fileOpen(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开工程', '', 'QGIS 工程 (*.qgz *.qgs)')
        if path: return self.addProject(path)
    def addProject(self, path):
        if not self.saveDirty(): return False
        # Validate in a temporary project before replacing the current one.
        candidate = QgsProject()
        if not candidate.read(path):
            self.mMessageBar.pushCritical('打开失败', candidate.error())
            return False
        candidate.clear()
        del candidate
        if not self.mProject.read(path):
            self.mMessageBar.pushCritical('打开失败', self.mProject.error())
            return False
        gps = [l.id() for l in self.mProject.mapLayers().values() if l.providerType() == 'gpx' or l.source().split('|')[0].lower().endswith('.gpx')]
        if gps:
            self.mProject.removeMapLayers(gps)
            self.mMessageBar.pushWarning('GPS 已排除', f'工程中移除了 {len(gps)} 个 GPX 图层；源文件未改写')
        self.mMapCanvas.setDestinationCrs(self.mProject.crs())
        extent = self.mProject.viewSettings().defaultViewExtent()
        if not extent.isEmpty():
            transform = QgsCoordinateTransform(extent.crs(), self.mMapCanvas.mapSettings().destinationCrs(), self.mProject)
            self.mMapCanvas.setExtent(transform.transformBoundingBox(extent))
        self.mMapCanvas.refresh()
        self.addRecentProject(path)
        return True
    def fileRevert(self):
        path = self.mProject.fileName()
        if path: return self.addProject(path)
    def fileSave(self):
        if not self.mProject.fileName(): return self.fileSaveAs()
        return self.writeProject(self.mProject.fileName())
    def fileSaveAs(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存工程', self.mProject.fileName(), 'QGIS 压缩工程 (*.qgz);;QGIS 工程 (*.qgs)')
        if not path: return False
        if not Path(path).suffix: path += '.qgz'
        return self.writeProject(path)
    def writeProject(self, path):
        from qgis.core import QgsReferencedRectangle
        self.mProject.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(self.mMapCanvas.extent(), self.mMapCanvas.mapSettings().destinationCrs()))
        if not self.mProject.write(path):
            self.mMessageBar.pushCritical('保存失败', self.mProject.error())
            return False
        self.addRecentProject(path)
        return True
    def addRecentProject(self, path):
        paths = self.mSettings.value('PythonDesktop/recentProjects', [], type=list)
        paths = [path] + [p for p in paths if p != path]
        self.mSettings.setValue('PythonDesktop/recentProjects', paths[:12])
        self.updateRecentProjects()
    def updateRecentProjects(self):
        self.mRecentProjectsMenu.clear()
        paths = self.mSettings.value('PythonDesktop/recentProjects', [], type=list)
        for path in paths:
            self.mRecentProjectsMenu.addAction(path, partial(self.addProject, path))
        if not hasattr(self, 'clearRecentProjectsAction'):
            self.clearRecentProjectsAction = QAction('清空列表', self)
            self.clearRecentProjectsAction.setObjectName('clearRecentProjectsAction')
            self.clearRecentProjectsAction.triggered.connect(self.clearRecentProjects)
        self.clearRecentProjectsAction.setEnabled(bool(paths))
        if paths:
            self.mRecentProjectsMenu.addSeparator()
            self.mRecentProjectsMenu.addAction(self.clearRecentProjectsAction)
        self.mDynamicActions['qgisapp:clearRecentProjectsAction'] = dict(action=self.clearRecentProjectsAction,
            handler='clearRecentProjects', note='清空最近工程记录，保留磁盘工程文件。', inInterface=True)

    def clearRecentProjects(self):
        self.mSettings.remove('PythonDesktop/recentProjects')
        self.updateRecentProjects()

    def addUserInputWidget(self, widget):
        self.mUserInputDockWidget.addUserInputWidget(widget)

    def createMapTips(self):
        from qgis.gui import QgsMapTip
        self.mpMaptip = QgsMapTip()
        self.mMapTipsVisible, self.mLastMapPosition = False, None
        self.mpMapTipsTimer = QTimer(self.mMapCanvas)
        self.mpMapTipsTimer.setSingleShot(True)
        self.mpMapTipsTimer.setInterval(self.mSettings.value('qgis/mapTipsDelay', 850, type=int))
        self.mpMapTipsTimer.timeout.connect(self.showMapTip)
        self.mMapCanvas.xyCoordinates.connect(self.saveLastMousePosition)
        self.mMapCanvas.extentsChanged.connect(self.clearMapTip)
        self.mMapCanvas.mapToolSet.connect(self.clearMapTip)
        self.mMapCanvas.viewport().installEventFilter(self)

    def toggleMapTips(self, enabled):
        self.mMapTipsVisible = enabled
        self.mSettings.setValue('qgis/enableMapTips', enabled)
        if self.mActionMapTips.isChecked() != enabled: self.mActionMapTips.setChecked(enabled)
        if not enabled: self.clearMapTip()

    def clearMapTip(self, *args):
        self.mpMapTipsTimer.stop()
        self.mpMaptip.clear(self.mMapCanvas)

    def saveLastMousePosition(self, point):
        if self.mMapTipsVisible:
            self.mLastMapPosition = point
            if self.mMapCanvas.underMouse():
                self.mpMaptip.clear(self.mMapCanvas, min(300, self.mpMapTipsTimer.interval()))
                self.mpMapTipsTimer.start()

    def showMapTip(self):
        layer = self.mMapCanvas.currentLayer()
        if self.mMapTipsVisible and self.mLastMapPosition is not None and self.mMapCanvas.underMouse() and layer and layer.hasMapTips() and not self.mMapCanvas.isDrawing():
            self.mpMaptip.showMapTip(layer, self.mLastMapPosition, self.mMapCanvas.mouseLastXY(), self.mMapCanvas)

    def eventFilter(self, watched, event):
        if hasattr(self, 'mpMapTipsTimer') and watched is self.mMapCanvas.viewport() and event.type() in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Wheel):
            self.clearMapTip()
        return super().eventFilter(watched, event)

    def setMapTool(self, name): self.mMapCanvas.setMapTool(self.mMapTools[name])
    def refreshMapCanvas(self): self.mMapCanvas.refreshAllLayers()
    def zoomFull(self): self.mMapCanvas.zoomToFullExtent()
    def zoomToPrevious(self): self.mMapCanvas.zoomToPreviousExtent()
    def zoomToNext(self): self.mMapCanvas.zoomToNextExtent()
    def zoomToSelected(self):
        if self.vectorLayer(): self.mMapCanvas.zoomToSelected(self.vectorLayer())
    def panToSelected(self):
        if self.vectorLayer(): self.mMapCanvas.panToSelected(self.vectorLayer())
    def zoomToLayerExtent(self):
        layers = self.mLayerTreeView.selectedLayers() or ([self.activeLayer()] if self.activeLayer() else [])
        extent = QgsRectangle()
        extent.setMinimal()
        for layer in layers:
            transform = QgsCoordinateTransform(layer.crs(), self.mMapCanvas.mapSettings().destinationCrs(), self.mProject)
            extent.combineExtentWith(transform.transformBoundingBox(layer.extent()))
        if not extent.isNull() and extent.isFinite():
            if extent.width() == 0 or extent.height() == 0: extent.grow(0.001)
            extent.scale(1.05)
            self.mMapCanvas.setExtent(extent)
            self.mMapCanvas.refresh()
    def newMapCanvas(self):
        canvas = QgsMapCanvas(self)
        canvas.setProject(self.mProject)
        canvas.setLabelingEngineSettings(self.mProject.labelingEngineSettings())
        canvas.setDestinationCrs(self.mProject.crs())
        canvas.setLayers(self.mMapCanvas.layers())
        canvas.setExtent(self.mMapCanvas.extent())
        from qgis.gui import QgsMapCanvasAnnotationItem
        for annotation in self.mProject.annotationManager().annotations(): QgsMapCanvasAnnotationItem(annotation, canvas)
        canvas._bridge = QgsLayerTreeMapCanvasBridge(self.mProject.layerTreeRoot(), canvas, canvas)
        canvas._pan = QgsMapToolPan(canvas)
        canvas.setMapTool(canvas._pan)
        from .decorations.qgsdecorationoverlay import QgsDecorationOverlay
        canvas._decorationOverlay = QgsDecorationOverlay(canvas, self)
        self.mAdditionalCanvases.append(canvas)
        return self.dock(f'MapCanvas{len(self.mAdditionalCanvases)}', '地图视图', canvas, visible=True)

    def removeLayer(self):
        nodes = self.mLayerTreeView.selectedNodes(True)
        for node in nodes:
            layers = [node.layer()] if isinstance(node, QgsLayerTreeLayer) else [n.layer() for n in node.findLayers()]
            for layer in layers:
                if isinstance(layer, QgsVectorLayer) and not self.mVectorLayerTools.stopEditing(layer): return
                if isinstance(layer, QgsMeshLayer) and not self.mMeshEditTool.stopEditing(layer): return
        if nodes and QMessageBox.question(self, '移除', f'移除选中的 {len(nodes)} 个图层/组？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            for node in nodes:
                if node.parent(): node.parent().removeChildNode(node)
    def duplicateLayers(self):
        for layer in self.mLayerTreeView.selectedLayers():
            clone = layer.clone()
            clone.setName(layer.name() + ' 副本')
            self.addMapLayer(clone)
    def setLayersVisible(self, visible): self.mProject.layerTreeRoot().setItemVisibilityCheckedRecursive(visible)
    def setSelectedLayersVisible(self, visible):
        for node in self.mLayerTreeView.selectedNodes(): node.setItemVisibilityCheckedRecursive(visible)
    def toggleSelectedLayers(self):
        for node in self.mLayerTreeView.selectedNodes(): node.setItemVisibilityCheckedRecursive(not node.itemVisibilityChecked())
    def hideDeselectedLayers(self):
        selected = set(self.mLayerTreeView.selectedLayers())
        for node in self.mProject.layerTreeRoot().findLayers():
            if node.layer() not in selected: node.setItemVisibilityChecked(False)
    def addToOverview(self):
        node = self.mProject.layerTreeRoot().findLayer(self.activeLayer().id())
        node.setCustomProperty('overview', not node.customProperty('overview', False))
    def allToOverview(self, visible):
        for node in self.mProject.layerTreeRoot().findLayers(): node.setCustomProperty('overview', visible)

    def layerProperties(self): return self.showLayerProperties(self.activeLayer())
    def showLayerProperties(self, layer, page=''):
        from qgis.core import QgsAnnotationLayer
        if isinstance(layer, QgsVectorLayer): dialog = QgsVectorLayerProperties(self.mMapCanvas, self.mMessageBar, layer, self)
        elif isinstance(layer, QgsRasterLayer): dialog = QgsRasterLayerProperties(layer, self.mMapCanvas, self)
        elif isinstance(layer, QgsMeshLayer): dialog = QgsMeshLayerProperties(layer, self.mMapCanvas, self)
        elif isinstance(layer, QgsVectorTileLayer): dialog = QgsVectorTileLayerProperties(layer, self.mMapCanvas, self.mMessageBar, self)
        elif isinstance(layer, QgsAnnotationLayer):
            from .annotations.qgsannotationlayerproperties import QgsAnnotationLayerProperties
            dialog = QgsAnnotationLayerProperties(layer, self.mMapCanvas, self.mMessageBar, self)
        else:
            self.mMessageBar.pushWarning('属性', '此图层类型的属性窗口尚未移植')
            return
        if page: dialog.setCurrentPage(page)
        dialog.exec_()
        layer.triggerRepaint()
        self.refreshActionFeatureAction()
    def labeling(self): return self.showLayerProperties(self.activeLayer(), 'mOptsPage_Labeling')

    def updateLabelToolButtons(self, *args):
        enabled = any(isinstance(layer, QgsVectorLayer) and (layer.labelsEnabled() or layer.diagramsEnabled())
                      for layer in self.mProject.mapLayers().values())
        for name in ('PinLabels', 'ShowHideLabels', 'MoveLabel', 'RotateLabel', 'ChangeLabelProperties'):
            getattr(self, 'mAction' + name).setEnabled(enabled)

    def showPinnedLabels(self):
        tool = self.mMapTools['pinLabels']
        enabled = self.mActionShowPinnedLabels.isChecked()
        tool.showPinnedLabels(enabled)
        if enabled:
            count = len(tool.mHighlights)
            message = f'已高亮 {count} 个固定标注/图表/引线端点' if count else (
                '固定标注高亮已开启，等待地图绘制完成' if self.mMapCanvas.isDrawing() else
                '当前范围没有可高亮的固定对象；请先用“固定标注”或“移动标注”工具操作标注')
            self.statusbar.showMessage(message, 6000)

    def showUnplacedLabels(self):
        settings = self.mProject.labelingEngineSettings()
        settings.setFlag(Qgis.LabelingFlag.DrawUnplacedLabels, self.mActionShowUnplacedLabels.isChecked())
        self.mProject.setLabelingEngineSettings(settings)
        self.mProject.setDirty(True)

    def syncLabelingEngineActions(self):
        settings = self.mProject.labelingEngineSettings()
        action = self.mActionShowUnplacedLabels
        action.blockSignals(True)
        action.setChecked(settings.testFlag(Qgis.LabelingFlag.DrawUnplacedLabels))
        action.blockSignals(False)
        # QgsMapCanvas.setProject() does not connect these settings in 3.34.
        # This explicit bridge is present in QgisApp::createCanvas().
        for canvas in self.mapCanvases():
            canvas.setLabelingEngineSettings(settings)
            canvas.refreshAllLayers()
    def diagramProperties(self): return self.showLayerProperties(self.activeLayer(), 'mOptsPage_Diagrams')
    def attributeTable(self, filterMode=QgsAttributeTableFilterModel.ShowAll, layer=None, filterExpression=''):
        layer = self.vectorLayer(layer)
        if not layer: return
        from .qgsattributetabledialog import QgsAttributeTableDialog
        dialog = QgsAttributeTableDialog(layer, self, filterMode)
        if filterExpression:
            dialog.mFilterQuery.setText(filterExpression)
            dialog.filterExpression()
        self.mWindows.append(dialog)
        dialog.show()
        return dialog
    def fieldCalculator(self):
        if self.vectorLayer(): QgsFieldCalculator(self.vectorLayer(), self).exec_()
    def layerSubsetString(self):
        layer = self.vectorLayer()
        if layer:
            dialog = QgsQueryBuilder(layer, self)
            if dialog.exec_(): layer.setSubsetString(dialog.sql())
    def setLayerCrs(self):
        dialog = QgsProjectionSelectionDialog(self)
        dialog.setCrs(self.activeLayer().crs())
        if dialog.exec_(): self.activeLayer().setCrs(dialog.crs())
    def setProjectCrsFromLayer(self): self.mProject.setCrs(self.activeLayer().crs())
    def setLayerScaleVisibility(self):
        layer = self.activeLayer()
        dlg = QDialog(self)
        dlg.setWindowTitle('比例尺可见性')
        form = QFormLayout(dlg)
        enabled = QCheckBox('启用')
        enabled.setChecked(layer.hasScaleBasedVisibility())
        minimum, maximum = QDoubleSpinBox(), QDoubleSpinBox()
        for widget in (minimum, maximum): widget.setRange(0, 1e12)
        minimum.setValue(layer.minimumScale())
        maximum.setValue(layer.maximumScale())
        form.addRow(enabled)
        form.addRow('缩小界限（比例尺分母）', minimum)
        form.addRow('放大界限（比例尺分母）', maximum)
        self.dialogButtons(dlg, form)
        if dlg.exec_():
            layer.setScaleBasedVisibility(enabled.isChecked())
            layer.setMinimumScale(minimum.value())
            layer.setMaximumScale(maximum.value())
            layer.triggerRepaint()

    def selectAll(self):
        if self.vectorLayer(): self.vectorLayer().selectAll()
    def invertSelection(self):
        if self.vectorLayer(): self.vectorLayer().invertSelection()
    def deselectActiveLayer(self):
        layer = self.vectorLayer()
        if layer:
            self.mPreviousSelections[layer.id()] = layer.selectedFeatureIds()
            layer.removeSelection()
    def deselectAll(self):
        for layer in self.mProject.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self.mPreviousSelections[layer.id()] = layer.selectedFeatureIds()
                layer.removeSelection()
    def reselect(self):
        layer = self.vectorLayer()
        if layer: layer.selectByIds(self.mPreviousSelections.get(layer.id(), []))
    def selectByExpression(self):
        if self.vectorLayer(): QgsExpressionSelectionDialog(self.vectorLayer(), '', self).exec_()
    def toggleEditing(self):
        mesh = self.activeLayer()
        if isinstance(mesh, QgsMeshLayer):
            result = self.mMeshEditTool.stopEditing(mesh) if mesh.isEditable() else self.mMeshEditTool.startEditing(mesh)
            self.updateActionState()
            return result
        layer = self.vectorLayer()
        if not layer: return
        result = self.mVectorLayerTools.stopEditing(layer) if layer.isEditable() else self.mVectorLayerTools.startEditing(layer)
        self.updateActionState()
        return result
    def editableLayers(self, selected=False):
        layers = self.mLayerTreeView.selectedLayers() if selected else [node.layer() for node in self.mProject.layerTreeRoot().findLayers()]
        return [layer for layer in layers if isinstance(layer, (QgsVectorLayer, QgsMeshLayer)) and layer.isEditable() and not layer.properties() & Qgis.MapLayerProperty.UsersCannotToggleEditing]
    def saveActiveLayerEdits(self):
        return self.saveLayerEdits(self.activeLayer())
    def saveLayerEdits(self, layer):
        if isinstance(layer, QgsMeshLayer): return self.mMeshEditTool.saveEdits(layer)
        return self.mVectorLayerTools.saveEdits(layer)
    def saveEdits(self):
        results = [self.saveLayerEdits(layer) for layer in self.editableLayers(selected=True)]
        self.updateActionState()
        return all(results)
    def saveAllEdits(self):
        results = [self.saveLayerEdits(layer) for layer in self.editableLayers()]
        self.updateActionState()
        return all(results)
    def rollbackEdits(self):
        return self.rollbackLayers(self.editableLayers(selected=True), False)
    def cancelEdits(self):
        return self.rollbackLayers(self.editableLayers(selected=True), True)
    def rollbackAllEdits(self):
        return self.rollbackLayers(self.editableLayers(), False)
    def cancelAllEdits(self):
        return self.rollbackLayers(self.editableLayers(), True)
    def rollbackLayers(self, layers, stopEditing):
        modified = [layer.name() for layer in layers if layer.isModified() or layer.id() in self.mMeshEditTool.mFailedSaves]
        if modified and QMessageBox.question(self, '丢弃编辑', '丢弃以下图层的未保存编辑？\n' + '\n'.join(modified), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return False
        results = [layer.rollBackFrameEditing(self.mMeshEditTool.transform(layer), not stopEditing) if isinstance(layer, QgsMeshLayer) else layer.rollBack(stopEditing) for layer in layers]
        for layer, success in zip(layers, results):
            if success: self.mMeshEditTool.mFailedSaves.discard(layer.id())
        self.mMeshEditTool.onEdit()
        self.updateActionState()
        return all(results)
    def confirmDiscard(self, layer):
        return not layer.isModified() or QMessageBox.question(self, '丢弃编辑', f'丢弃 {layer.name()} 的未保存编辑？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
    def undo(self):
        layer = self.activeLayer()
        if isinstance(layer, (QgsVectorLayer, QgsMeshLayer)):
            layer.undoStack().undo()
            if isinstance(layer, QgsMeshLayer): self.mMeshEditTool.onEdit()
    def redo(self):
        layer = self.activeLayer()
        if isinstance(layer, (QgsVectorLayer, QgsMeshLayer)):
            layer.undoStack().redo()
            if isinstance(layer, QgsMeshLayer): self.mMeshEditTool.onEdit()
    def deleteSelected(self):
        layer = self.vectorLayer()
        if not layer or not layer.isEditable(): return
        layer.beginEditCommand('删除选中要素')
        if layer.deleteSelectedFeatures()[0]: layer.endEditCommand()
        else: layer.destroyEditCommand()
        layer.triggerRepaint()

    def geometryEditTool(self):
        return self.mGeometryEditTool

    def runSimplifyFeature(self):
        layer = self.vectorLayer()
        if not layer: return False
        tolerance, ok = QInputDialog.getDouble(self, '简化要素', '容差（图层单位）', 1.0, 0.0, 1e12, 6)
        if ok: return self.geometryEditTool().simplifyFeature(tolerance)
        return False

    def runRotateFeature(self):
        angle, ok = QInputDialog.getDouble(self, '旋转要素', '旋转角度（度）', 90.0, -360.0, 360.0, 3)
        return self.geometryEditTool().rotateFeature(angle) if ok else False

    def runScaleFeature(self):
        factor, ok = QInputDialog.getDouble(self, '缩放要素', '缩放比例', 1.0, 0.0001, 1e6, 4)
        return self.geometryEditTool().scaleFeature(factor) if ok else False

    def runDeleteRing(self): self.setMapTool('deleteRing')
    def runDeletePart(self): self.setMapTool('deletePart')
    def runMergeFeatures(self): return self.geometryEditTool().mergeFeatures()
    def runMergeFeatureAttributes(self):
        from .qgsmergeattributesdialog import QgsMergeAttributesDialog
        layer = self.vectorLayer()
        if not layer or not layer.isEditable() or layer.selectedFeatureCount() < 2: return False
        dialog = QgsMergeAttributesDialog(list(layer.getSelectedFeatures()), layer, self)
        return self.mergeAttributesOfSelectedFeatures(dialog.mergedAttributes()) if dialog.exec_() else False
    def mergeAttributesOfSelectedFeatures(self, values):
        layer = self.vectorLayer()
        if not layer or not layer.isEditable(): return False
        layer.beginEditCommand('合并要素属性')
        success = all(layer.changeAttributeValues(fid, values) for fid in layer.selectedFeatureIds())
        if success: layer.endEditCommand()
        else: layer.destroyEditCommand()
        layer.triggerRepaint()
        return success
    def runReverseLine(self): return self.geometryEditTool().reverseLine()

    def runOffsetCurve(self):
        layer = self.vectorLayer()
        if not layer: return False
        distance, ok = QInputDialog.getDouble(self, '偏移曲线', '偏移距离（图层单位）', 1.0, -1e12, 1e12, 6)
        if ok: return self.geometryEditTool().offsetCurve(distance)
        return False

    def digitizingCompleted(self, feature):
        layer = self.vectorLayer()
        if layer and layer.isEditable():
            return self.mMapTools['addFeature'].addFeature(layer, feature)

    def copySelectionToClipboard(self, layer=None):
        layer = self.vectorLayer(layer)
        if layer:
            self.mClipboard = (layer.fields(), layer.crs(), [QgsFeature(f) for f in layer.getSelectedFeatures()], layer.wkbType())
            self.updateActionState()
            text = '\t'.join(f.name() for f in layer.fields()) + '\n'
            text += '\n'.join('\t'.join(str(v) for v in f.attributes()) for f in self.mClipboard[2])
            QgsApplication.clipboard().setText(text)
    def cutSelectionToClipboard(self):
        self.copySelectionToClipboard()
        self.deleteSelected()
    def pasteFromClipboard(self, layer=None):
        layer = self.vectorLayer(layer)
        if not layer or not layer.isEditable() or not self.mClipboard: return False
        fields, crs, features, wkb = self.mClipboard
        transform = QgsCoordinateTransform(crs, layer.crs(), self.mProject)
        copies = []
        for source in features:
            feature = QgsFeature(layer.fields())
            for i, field in enumerate(layer.fields()):
                sourceIndex = fields.lookupField(field.name())
                if sourceIndex >= 0: feature.setAttribute(i, source[sourceIndex])
            geometry = QgsGeometry(source.geometry())
            if not geometry.isNull(): geometry.transform(transform)
            feature.setGeometry(geometry)
            copies.append(feature)
        layer.beginEditCommand('粘贴要素')
        if layer.addFeatures(copies): layer.endEditCommand()
        else:
            layer.destroyEditCommand()
            return False
        layer.triggerRepaint()
        return True
    def pasteToNewMemoryVector(self):
        if not self.mClipboard: return
        from qgis.core import QgsMemoryProviderUtils
        fields, crs, features, wkb = self.mClipboard
        layer = QgsMemoryProviderUtils.createMemoryLayer('粘贴的要素', fields, wkb, crs)
        if not layer.dataProvider().addFeatures([QgsFeature(f) for f in features])[0]:
            self.mMessageBar.pushCritical('粘贴失败', '无法复制剪贴板要素')
            return None
        layer.updateExtents()
        return layer
    def pasteAsNewMemoryVector(self):
        layer = self.pasteToNewMemoryVector()
        if layer: return self.addMapLayer(layer)
    def pasteAsNewVector(self):
        layer = self.pasteToNewMemoryVector()
        if layer: return self.saveAsVectorFileGeneral(layer)

    def createMapLayerActionContext(self):
        from qgis.gui import QgsMapLayerActionContext
        context = QgsMapLayerActionContext()
        context.setMessageBar(self.mMessageBar)
        return context

    def availableFeatureActions(self, layer):
        if layer is None: return [], []
        actions = [action for action in layer.actions().actions('Canvas')
                   if action.isValid() and (layer.isEditable() or not action.isEnabledOnlyWhenEditable())]
        registered = QgsGui.mapLayerActionRegistry().mapLayerActions(
            layer, Qgis.MapLayerActionTarget.SingleFeature, self.createMapLayerActionContext())
        return actions, registered

    def refreshActionFeatureAction(self):
        from html import escape
        layer = self.vectorLayer()
        actions, registered = self.availableFeatureActions(layer)
        self.mActionFeatureAction.setEnabled(bool(actions or registered))
        name, icon = '', QIcon()
        if layer is not None:
            default = layer.actions().defaultAction('Canvas')
            native = next((action for action in actions if action.id() == default.id()), None)
            plugin = QgsGui.mapLayerActionRegistry().defaultActionForLayer(layer)
            if native is not None: name, icon = native.name(), native.icon()
            elif plugin is not None and plugin in registered: name, icon = plugin.text(), plugin.icon()
        self.mActionFeatureAction.setToolTip('运行要素动作<br><b>' + escape(name) + '</b>' if name else '未选择可用的要素动作')
        self.mActionFeatureAction.setIcon(icon if not icon.isNull() else QgsApplication.getThemeIcon('/mActionActive.svg' if name else '/mAction.svg'))

    def updateDefaultFeatureAction(self, action):
        from qgis.PyQt.QtCore import QUuid
        from qgis.core import QgsAction
        from qgis.gui import QgsMapLayerAction
        layer = self.vectorLayer()
        if layer is None: return
        value = action.data() if action else None
        available, registered = self.availableFeatureActions(layer)
        registry = QgsGui.mapLayerActionRegistry()
        if isinstance(value, QgsAction) and any(a.id() == value.id() for a in available):
            layer.actions().setDefaultAction('Canvas', value.id())
            registry.setDefaultActionForLayer(layer, None)
            self.mProject.setDirty(True)
        elif isinstance(value, QgsMapLayerAction) and not sip.isdeleted(value) and value in registered:
            layer.actions().setDefaultAction('Canvas', QUuid())
            registry.setDefaultActionForLayer(layer, value)
            self.mProject.setDirty(True)
        elif value is None:
            layer.actions().setDefaultAction('Canvas', QUuid())
            registry.setDefaultActionForLayer(layer, None)
            self.mProject.setDirty(True)
        self.refreshActionFeatureAction()

    def refreshFeatureActions(self):
        self.mFeatureActionMenu.clear()
        layer = self.vectorLayer()
        if not layer: return
        if hasattr(self, 'mFeatureActionGroup'): sip.delete(self.mFeatureActionGroup)
        self.mFeatureActionGroup = QActionGroup(self.mFeatureActionMenu)
        default = layer.actions().defaultAction('Canvas')
        actions, registered = self.availableFeatureActions(layer)
        pluginDefault = QgsGui.mapLayerActionRegistry().defaultActionForLayer(layer)
        def addChoice(icon, title, value, checked, enabled=True):
            item = self.mFeatureActionMenu.addAction(icon, title)
            item.setData(value)
            item.setCheckable(True)
            item.setChecked(checked)
            item.setEnabled(enabled)
            self.mFeatureActionGroup.addAction(item)
            item.triggered.connect(lambda _=False, choice=item: self.updateDefaultFeatureAction(choice))
            return item
        addChoice(QgsApplication.getThemeIcon('/mAction.svg'), '不选择默认动作', None,
                  not default.isValid() and pluginDefault is None)
        for action in actions:
            item = addChoice(action.icon(), action.shortTitle() or action.name(), action, default.id() == action.id())
            item.setToolTip(action.name())
        if registered:
            self.mFeatureActionMenu.addSeparator()
            for action in registered:
                # Menu-owned selectors must not change plugin QAction ownership
                # or emit its generic triggered signal merely to choose a default.
                addChoice(action.icon(), action.text(), action, action is pluginDefault and not default.isValid(), action.isEnabled())
        self.mFeatureActionMenu.addSeparator()
        self.mFeatureActionMenu.addAction('配置图层动作…', lambda: self.showLayerProperties(layer, 'mOptsPage_Actions'))
        self.refreshActionFeatureAction()

    def populateFeatureActionMenu(self): self.refreshFeatureActions()

    def saveAsVectorFileGeneral(self, layer, dialog=None):
        from qgis.gui import QgsVectorLayerSaveAsDialog
        from .qgsvectorlayersaveasdialog import saveOptionsFromDialog
        dialog = dialog or QgsVectorLayerSaveAsDialog(layer, QgsVectorLayerSaveAsDialog.Option.AllOptions, self)
        dialog.setMapCanvas(self.mMapCanvas)
        if not dialog.exec_(): return None
        options, converter = saveOptionsFromDialog(dialog, layer, self.mProject)
        return self.startVectorLayerExport(layer, dialog.fileName(), options, dialog.addToCanvas(), converter)

    def startVectorLayerExport(self, layer, path, options, addToCanvas=True, converter=None):
        from qgis.core import QgsVectorFileWriterTask
        task = QgsVectorFileWriterTask(layer, path, options)
        self.mVectorExportTasks[task] = (layer, options, converter)
        def succeeded(filename):
            if not self.mShutdown:
                self.mMessageBar.pushSuccess('导出完成', filename)
                if addToCanvas:
                    uri = filename + ('|layername=' + options.layerName if options.layerName else '')
                    self.addVectorLayer(uri, options.layerName or Path(filename).stem)
            self.mVectorExportTasks.pop(task, None)
        def failed(code, message):
            if not self.mShutdown: self.mMessageBar.pushCritical('导出未完成', message)
            self.mVectorExportTasks.pop(task, None)
        # In 3.34 SIP only writeComplete is exposed, not the C++ completed signal.
        task.writeComplete.connect(succeeded)
        task.errorOccurred.connect(failed)
        QgsApplication.taskManager().addTask(task)
        return task

    def exportVectorLayer(self, layer, path, options, addToCanvas=True):
        result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, self.mProject.transformContext(), options)
        if result[0] != QgsVectorFileWriter.NoError:
            self.mMessageBar.pushCritical('导出失败', str(result[1]))
            return None
        filename = result[2] or path
        layerName = result[3] or options.layerName
        self.mMessageBar.pushSuccess('导出完成', filename)
        if addToCanvas:
            uri = filename + ('|layername=' + layerName if layerName else '')
            return self.addVectorLayer(uri, layerName or Path(filename).stem)
        return filename
    def copyLayer(self): self.mLayerClipboard = [l.clone() for l in self.mLayerTreeView.selectedLayers()]
    def pasteLayer(self):
        for layer in self.mLayerClipboard: self.addMapLayer(layer.clone())
    def copyStyle(self):
        self.mStyleClipboard = QgsMapLayerStyle()
        self.mStyleClipboard.readFromLayer(self.activeLayer())
    def applyStyleToGroup(self):
        if self.mStyleClipboard and self.mStyleClipboard.isValid():
            for layer in self.mLayerTreeView.selectedLayers():
                self.mStyleClipboard.writeToLayer(layer)
                layer.triggerRepaint()
    def saveStyle(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存样式', '', 'QGIS 样式 (*.qml)')
        if path: self.activeLayer().saveNamedStyle(path)
    def loadStyle(self):
        path, _ = QFileDialog.getOpenFileName(self, '加载样式', '', 'QGIS 样式 (*.qml);;SLD (*.sld)')
        if path:
            message, ok = self.activeLayer().loadNamedStyle(path)
            if not ok: self.mMessageBar.pushWarning('样式', message)
            self.activeLayer().triggerRepaint()

    def newMemoryLayer(self):
        layer = QgsNewMemoryLayerDialog.runAndCreateLayer(self, self.mProject.crs())
        if layer: return self.addMapLayer(layer)
    def annotationCreated(self, annotation):
        from qgis.gui import QgsMapCanvasAnnotationItem
        for canvas in self.mapCanvases(): QgsMapCanvasAnnotationItem(annotation, canvas)

    def restoreFormAnnotations(self, document, context):
        # QgisApp registers FormAnnotationItem in the private C++ registry.
        # That registry has SIP_NO_FILE; restore the same native GUI type via
        # the public post-read signal after the core manager restores its types.
        from qgis.gui import QgsFormAnnotation
        nodes = document.elementsByTagName('FormAnnotationItem')
        for i in range(nodes.count()):
            annotation = QgsFormAnnotation()
            annotation.readXml(nodes.at(i).toElement(), context)
            if not annotation.mapPositionCrs().isValid(): annotation.setMapPositionCrs(self.mProject.crs())
            self.mProject.annotationManager().addAnnotation(annotation)

    def createAnnotationLayer(self):
        from qgis.core import QgsAnnotationLayer
        name, index = '注记', 1
        while self.mProject.mapLayersByName(name):
            name, index = f'注记 ({index})', index + 1
        layer = QgsAnnotationLayer(name, QgsAnnotationLayer.LayerOptions(self.mProject.transformContext()))
        layer.setCrs(self.mProject.crs())
        self.mProject.addMapLayer(layer, False)
        self.mProject.layerTreeRoot().insertLayer(0, layer)
        self.setActiveLayer(layer)
        return layer
    def newVectorLayer(self):
        path = QgsNewVectorLayerDialog.runAndCreateLayer(self, 'UTF-8', self.mProject.crs())
        if path: return self.addVectorLayer(path)
    def newGeoPackageLayer(self):
        dialog = QgsNewGeoPackageLayerDialog(self)
        dialog.setCrs(self.mProject.crs())
        dialog.setAddToProject(True)
        dialog.exec_()
    def saveAsFile(self):
        layer = self.activeLayer()
        if isinstance(layer, QgsVectorLayer):
            return self.saveAsVectorFileGeneral(layer)
        elif isinstance(layer, QgsRasterLayer):
            from processing import execAlgorithmDialog
            return execAlgorithmDialog('gdal:translate', {'INPUT': layer})
        else: self.mMessageBar.pushWarning('导出', '当前类型的导出控制器尚未移植')
    def addLayerDefinition(self):
        path, _ = QFileDialog.getOpenFileName(self, '图层定义', '', 'QGIS 图层定义 (*.qlr)')
        if path:
            ok, error = QgsLayerDefinition.loadLayerDefinition(path, self.mProject, self.mProject.layerTreeRoot())
            if not ok: self.mMessageBar.pushWarning('图层定义', error)

    def embedLayers(self):
        from .qgsprojectlayergroupdialog import QgsProjectLayerGroupDialog
        dialog = QgsProjectLayerGroupDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.isValid():
            self.addEmbeddedItems(dialog.selectedProjectFile(), dialog.selectedGroups(), dialog.selectedLayerIds())
        dialog.deleteLater()

    def customProjection(self):
        from .options.qgscustomprojectionoptions import QgsCustomProjectionDialog
        dialog = QgsCustomProjectionDialog(self)
        dialog.exec_()
        dialog.deleteLater()

    def insertAddLayerAction(self, action):
        self.mAddLayerMenu.insertAction(self.mActionAddLayerSeparator, action)

    def removeAddLayerAction(self, action):
        self.mAddLayerMenu.removeAction(action)

    def addEmbeddedItems(self, projectFile, groups, layerIds=()):
        if layerIds:
            self.mMessageBar.pushWarning('嵌入', '当前支持组嵌入；单图层嵌入接口尚未移植，请在源工程中将图层归组。')
            return False
        if self.mProject.fileName() and Path(projectFile).resolve() == Path(self.mProject.fileName()).resolve():
            self.mMessageBar.pushWarning('嵌入', '不能嵌入当前工程自身')
            return False
        from .qgsprojectlayergroupdialog import QgsProjectLayerGroupDialog
        try:
            document = QgsProjectLayerGroupDialog.readProjectDocument(projectFile)
        except (OSError, ValueError) as error:
            self.mMessageBar.pushWarning('嵌入', str(error))
            return False
        from qgis.core import QgsLayerTree, QgsReadWriteContext
        sourceTree = QgsLayerTree()
        sourceTree.readChildrenFromXml(document.documentElement().firstChildElement('layer-tree-group'), QgsReadWriteContext())
        success = True
        for name in dict.fromkeys(groups):
            matching = [g for g in sourceTree.findGroups(True) if g.name() == name]
            if len(matching) != 1:
                self.mMessageBar.pushWarning('嵌入', f'组“{name}”不存在或名称不唯一，未嵌入')
                success = False
                continue
            if any(self.mProject.mapLayer(layerId) for layerId in matching[0].findLayerIds()):
                self.mMessageBar.pushWarning('嵌入', f'组“{name}”含有当前工程已加载的图层，未重复嵌入')
                success = False
                continue
            group = self.mProject.createEmbeddedGroup(name, str(Path(projectFile).resolve()), [])
            if group:
                self.mProject.layerTreeRoot().addChildNode(group)
                self.mProject.setDirty(True)
            else:
                self.mMessageBar.pushWarning('嵌入', f'无法嵌入组“{name}”')
                success = False
        for layer in self.mProject.mapLayers().values(): layer.resolveReferences(self.mProject)
        self.mMapCanvas.refresh()
        return success
    def saveAsLayerDefinition(self):
        path, _ = QFileDialog.getSaveFileName(self, '图层定义', '', 'QGIS 图层定义 (*.qlr)')
        if path:
            ok, error = QgsLayerDefinition.exportLayerDefinition(path, self.mLayerTreeView.selectedNodes())
            if not ok: self.mMessageBar.pushWarning('图层定义', error)

    def saveMapAsImage(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存地图', '', 'PNG (*.png);;JPEG (*.jpg)')
        if path: self.saveMapImage(path)

    def saveMapImage(self, path):
        if not self.decorationsReadyForExport(): return False
        # Native canvas export includes legacy annotations, but not its QWidget
        # decoration overlay. Paint the same decoration items onto the result.
        from qgis.PyQt.QtGui import QImage, QPainter
        self.mMapCanvas.saveAsImage(path)
        image = QImage(path)
        if image.isNull():
            self.mMessageBar.pushCritical('导出失败', path)
            return False
        ratio = image.width() / max(1, self.mMapCanvas.mapSettings().outputSize().width())
        image.setDevicePixelRatio(ratio)
        painter = QPainter(image)
        try:
            self.renderDecorationItems(painter, devicePixelRatio=ratio)
        finally: painter.end()
        success = image.save(path)
        if not success: self.mMessageBar.pushCritical('导出失败', path)
        return success
    def mapLayout(self):
        layout = QgsPrintLayout(self.mProject)
        layout.initializeDefaults()
        item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(10, 10))
        item.attemptResize(QgsLayoutSize(277, 190))
        item.setCrs(self.mMapCanvas.mapSettings().destinationCrs())
        item.setLayers(self.mMapCanvas.layers())
        item.zoomToExtent(self.mMapCanvas.extent())
        return layout
    def saveMapAsPdf(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存地图为 PDF', '', 'PDF (*.pdf)')
        if path: self.saveMapPdf(path)

    def saveMapPdf(self, path):
        if not self.decorationsReadyForExport(): return False
        from qgis.core import QgsMapSettings, QgsMapRendererTask, QgsMapDecoration
        from qgis.PyQt.QtWidgets import QApplication

        class DecorationRenderer(QgsMapDecoration):
            def __init__(self, item):
                super().__init__()
                self.item = item

            def render(self, settings, context): self.item.render(settings, context)

        class MapRendererTask(QgsMapRendererTask):
            def execute(self): return self.run()

        settings = QgsMapSettings(self.mMapCanvas.mapSettings())
        settings.setDevicePixelRatio(1)
        task = MapRendererTask(settings, path, 'PDF')
        decorations = [DecorationRenderer(item) for item in self.mDecorationItems if item.enabled()]
        task.addDecorations(decorations)
        task.addAnnotations(self.mProject.annotationManager().annotations())
        # Keep application-owned decoration callbacks on the GUI thread.
        # The native map job still uses its normal layer renderer machinery.
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success = task.execute()
        finally:
            sip.delete(task)  # Flush the native PDF writer before returning.
            QApplication.restoreOverrideCursor()
        if not success: self.mMessageBar.pushCritical('导出失败', path)
        return success
    def newPrintLayout(self):
        name, ok = QInputDialog.getText(self, '新建打印布局', '名称')
        if not ok or not name: return
        if self.mProject.layoutManager().layoutByName(name):
            self.mMessageBar.pushWarning('布局', '该名称已经存在')
            return
        layout = self.mapLayout()
        layout.setName(name)
        self.mProject.layoutManager().addLayout(layout)
        return self.openLayoutDesigner(layout)
    def openLayoutDesigner(self, layout):
        from qgis.core import QgsReport
        if isinstance(layout, QgsReport):
            from .layout.qgsreportorganizerwidget import QgsReportOrganizerWidget
            dialog = QgsReportOrganizerWidget(self, layout)
            self.mLayoutDesigners.append(dialog)
            dialog.show()
            return dialog
        from .layout.qgslayoutdesignerdialog import QgsLayoutDesignerDialog
        dialog = QgsLayoutDesignerDialog(self, layout)
        self.mLayoutDesigners.append(dialog)
        self.mDecorations['LayoutExtent'].watchDesigner(dialog)
        dialog.show()
        return dialog
    def showLayoutManager(self):
        from qgis.PyQt.QtWidgets import QListWidget
        dialog = QDialog(self)
        dialog.setWindowTitle('布局管理器')
        box = QVBoxLayout(dialog)
        view = QListWidget()
        layouts = self.mProject.layoutManager().layouts()
        view.addItems([l.name() for l in layouts])
        box.addWidget(view)
        view.itemDoubleClicked.connect(lambda item: self.openLayoutDesigner(self.mProject.layoutManager().layoutByName(item.text())))
        add = QPushButton('新建布局')
        add.clicked.connect(self.newPrintLayout)
        box.addWidget(add)
        dialog.exec_()

    def newBookmark(self):
        name, ok = QInputDialog.getText(self, '书签', '名称')
        if ok and name:
            bookmark = QgsBookmark()
            bookmark.setName(name)
            bookmark.setExtent(QgsReferencedRectangle(self.mMapCanvas.extent(), self.mMapCanvas.mapSettings().destinationCrs()))
            self.mProject.bookmarkManager().addBookmark(bookmark)
            self.mProject.setDirty(True)
    def zoomToBookmark(self, index):
        extent = self.mBookmarksModel.data(index, QgsBookmarkManagerModel.RoleExtent)
        transform = QgsCoordinateTransform(extent.crs(), self.mMapCanvas.mapSettings().destinationCrs(), self.mProject)
        self.mMapCanvas.setExtent(transform.transformBoundingBox(extent))
        self.mMapCanvas.refresh()
    def showPythonDialog(self):
        if not hasattr(self, 'mPythonConsole'):
            from python.console.console import PythonConsole
            self.mPythonConsole = PythonConsole(self)
        self.mPythonConsole.setUserVisible(not self.mPythonConsole.isUserVisible())
        if self.mPythonConsole.isUserVisible(): self.mPythonConsole.activate()
        return self.mPythonConsole

    def copyIdentifyValue(self):
        QgsApplication.clipboard().setText('\n'.join(item.text(0) + '\t' + item.text(1) for item in self.mIdentifyResults.selectedItems()))

    def zoomToIdentifyResult(self):
        item = self.mIdentifyResults.currentItem()
        if not item:
            return
        while item.parent():
            item = item.parent()
        index = self.mIdentifyResults.indexOfTopLevelItem(item)
        results = self.mMapTools['identify'].mResults
        if not 0 <= index < len(results):
            return
        result = results[index]
        if not result.mFeature.isValid() or result.mFeature.geometry().isEmpty():
            return
        layer = result.mLayer
        transform = QgsCoordinateTransform(layer.crs(), self.mMapCanvas.mapSettings().destinationCrs(), self.mProject)
        extent = transform.transformBoundingBox(result.mFeature.geometry().boundingBox())
        if extent.width() == 0 or extent.height() == 0:
            extent.grow(self.mMapCanvas.mapUnitsPerPixel() * 20)
        self.mMapCanvas.setExtent(extent)
        self.mMapCanvas.refresh()

    def openIdentifyForm(self):
        item = self.mIdentifyResults.currentItem()
        if not item: return
        while item.parent(): item = item.parent()
        index = self.mIdentifyResults.indexOfTopLevelItem(item)
        results = self.mMapTools['identify'].mResults
        if 0 <= index < len(results):
            result = results[index]
            if isinstance(result.mLayer, QgsVectorLayer) and result.mFeature.isValid():
                self.mQgisInterface.openFeatureForm(result.mLayer, result.mFeature)
    def showStyleManager(self): QgsStyleManagerDialog(QgsStyle.defaultStyle(), self).exec_()
    def showPluginManager(self):
        from .pluginmanager.qgspluginmanager import QgsPluginManager
        if self.mPluginManager is None: self.mPluginManager = QgsPluginManager(self)
        self.mPluginManager.refresh()
        self.mPluginManager.show()
    def customLayerActions(self, layer):
        return [entry[0] for entry in self.mQgisInterface.mCustomActions
                if entry[2] == layer.type() and (entry[3] or layer.id() in entry[4])]

    @staticmethod
    def dialogButtons(dialog, layout):
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons) if hasattr(layout, 'addWidget') else layout.addRow(buttons)
        return buttons
    def projectProperties(self, currentPage=''):
        from .qgsprojectproperties import QgsProjectProperties
        dialog = QgsProjectProperties(self)
        if currentPage == 'mProjOptsCRS': dialog.mOptionsStackedWidget.setCurrentWidget(dialog.mProjectionSelector)
        dialog.exec_()
    def options(self, currentPage=''):
        from .qgsoptions import QgsOptions
        QgsOptions(self, currentPage).exec_()
    def configureShortcuts(self):
        from .qgsoptions import QgsConfigureShortcutsDialog
        QgsConfigureShortcutsDialog(self).exec_()
    def snappingOptions(self):
        self.mSnappingToolBar.show()
        self.mSnappingWidget.editAdvancedConfig()
    def toggleFullScreen(self): self.showNormal() if self.isFullScreen() else self.showFullScreen()
    def togglePanelsVisibility(self):
        visible = any(d.isVisible() for d in self.findChildren(QDockWidget))
        if visible:
            self._visibleDocks = [d for d in self.findChildren(QDockWidget) if d.isVisible()]
            for dock in self._visibleDocks: dock.hide()
        else:
            for dock in getattr(self, '_visibleDocks', []): dock.show()
    def toggleMapOnly(self):
        self.togglePanelsVisibility()
        for toolbar in self.findChildren(QToolBar): toolbar.setVisible(not toolbar.isVisible())
    def about(self):
        QMessageBox.about(self, '关于', f'QGIS Python 3.34.10\n运行库：{Qgis.QGIS_VERSION}\n基于 QGIS GPL 源码的应用层移植。\nGPS 已排除。功能覆盖情况见帮助菜单。')

    def coverage(self):
        source = json.loads(json.dumps(getattr(self, 'mActionInventory', {'actions': []})))
        for item in source['actions']:
            item['status'] = 'excluded-gps' if item.get('excluded', False) else ('connected' if item['objectName'] in self.mImplementedActions else 'not-ported')
            if item['objectName'] in self.mImplementedActions: item.update(self.mImplementedActions[item['objectName']])
        source['summary'] = {status: sum(i['status'] == status for i in source['actions']) for status in ['connected', 'not-ported', 'excluded-gps']}
        catalog = ROOT / 'docs/upstream-toolbar-actions.json'
        dynamic = json.loads(catalog.read_text(encoding='utf-8')) if catalog.exists() else {'actions': [], 'extensionPoints': []}
        for item in dynamic['actions']:
            implementation = self.mDynamicActions.get(item['sourceKey'])
            item['status'] = 'connected' if implementation else 'not-ported'
            item['inToolbar'] = False
            item['inInterface'] = False
            if implementation:
                action = implementation['action']
                item.update(objectName=action.objectName(), handler=implementation['handler'], note=implementation['note'])
                toolbar = implementation.get('toolbarWidget', getattr(self, item['toolbar'], None))
                item['inToolbar'] = toolbar is not None and action in toolbar.actions()
                if not item['inToolbar'] and toolbar is not None:
                    item['inToolbar'] = any(
                        button.menu() and action in button.menu().actions()
                        for toolbarAction in toolbar.actions()
                        for button in [toolbar.widgetForAction(toolbarAction)]
                        if isinstance(button, QToolButton))
                item['inInterface'] = item['inToolbar'] or implementation.get('inInterface', False)
        source['dynamicActions'] = dynamic['actions']
        source['dynamicSummary'] = {state: sum(item['status'] == state for item in dynamic['actions']) for state in ('connected', 'not-ported')}
        source['extensionPoints'] = dynamic['extensionPoints']
        source['toolbarAudit'] = []
        for name in ('mAnnotationsToolBar', 'mShapeDigitizeToolBar', 'mMeshToolBar', 'mWebToolBar'):
            toolbar = getattr(self, name)
            source['toolbarAudit'].append({'objectName': name, 'title': toolbar.windowTitle(),
                'actions': [action.objectName() or action.text() for action in toolbar.actions() if not action.isSeparator()],
                'dynamicMissing': sum(item['toolbar'] == name and item['status'] == 'not-ported' for item in dynamic['actions'])})
        source['note'] = 'Main UI and dynamic toolbars have separate counts. Neither is a complete census of every QGIS action; connected is not full behavioral parity.'
        source['processingAlgorithmCount'] = len(QgsApplication.processingRegistry().algorithms())
        source['gpsAlgorithmsHiddenFromDesktop'] = self.mGpsAlgorithmsRemoved
        from scripts.update_porting_status import implementationState
        for item in source['actions'] + source['dynamicActions']:
            item['implementationState'] = implementationState(item)
        return source
    def writeCoverage(self):
        from scripts.update_porting_status import writeChecklist
        status = self.coverage()
        statusPath = ROOT / 'docs/implementation-status.json'
        if statusPath.parent.exists():
            statusPath.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        return writeChecklist(status)
    def sponsors(self):
        url = self.mSettings.value('qgis/qgisSponsorsUrl', 'https://qgis.org/en/site/about/sustaining_members.html')
        return QDesktopServices.openUrl(QUrl(url))
    def createDecorations(self):
        from .decorations.qgsdecorationtitle import QgsDecorationTitle
        from .decorations.qgsdecorationcopyright import QgsDecorationCopyright
        from .decorations.qgsdecorationimage import QgsDecorationImage
        from .decorations.qgsdecorationnortharrow import QgsDecorationNorthArrow
        from .decorations.qgsdecorationscalebar import QgsDecorationScaleBar
        from .decorations.qgsdecorationgrid import QgsDecorationGrid
        from .decorations.qgsdecorationlayoutextent import QgsDecorationLayoutExtent
        from .decorations.qgsdecorationoverlay import QgsDecorationOverlay
        self.mDecorations = {name: cls(self) for name, cls in (
            ('Grid', QgsDecorationGrid), ('LayoutExtent', QgsDecorationLayoutExtent),
            ('Image', QgsDecorationImage), ('Title', QgsDecorationTitle),
            ('Copyright', QgsDecorationCopyright), ('NorthArrow', QgsDecorationNorthArrow),
            ('ScaleBar', QgsDecorationScaleBar))}
        self.mDecorationItems = list(self.mDecorations.values())
        self.mDecorationOverlay = QgsDecorationOverlay(self.mMapCanvas, self)
        self.mDecorations['Image'].imageChanged.connect(self.refreshDecorationOverlays)
        self.mProject.readProject.connect(self.projectReadDecorationItems)
        self.mProject.cleared.connect(self.projectReadDecorationItems)
        self.mProject.writeProject.connect(self.saveDecorationItems)

    def refreshDecorationOverlays(self):
        if self.mShutdown: return
        self.mDecorationOverlay.update()
        for canvas in self.mAdditionalCanvases: canvas._decorationOverlay.update()

    def decorationsReadyForExport(self):
        image = self.mDecorations['Image']
        if image.enabled() and image.mLoading:
            self.mMessageBar.pushWarning('导出地图', '图片装饰仍在下载，请完成后再次导出。')
            return False
        return True

    def projectReadDecorationItems(self, *args):
        if self.mShutdown: return
        for item in self.mDecorationItems: item.projectRead()
        self.mDecorationOverlay.update()
        for canvas in self.mAdditionalCanvases: canvas._decorationOverlay.update()

    def saveDecorationItems(self, *args):
        for item in self.mDecorationItems: item.saveToProject()

    def renderDecorationItems(self, painter, canvas=None, devicePixelRatio=None):
        from qgis.core import QgsRenderContext
        settings = (canvas or self.mMapCanvas).mapSettings()
        context = QgsRenderContext.fromMapSettings(settings)
        context.setPainter(painter)
        if devicePixelRatio is not None: context.setDevicePixelRatio(devicePixelRatio)
        for item in self.mDecorationItems: item.render(settings, context)

    def checkQgisVersion(self):
        if not hasattr(self, 'mVersionInfo'):
            from .qgsversioninfo import QgsVersionInfo
            self.mVersionInfo = QgsVersionInfo(self)
            self.mVersionInfo.versionInfoAvailable.connect(self.versionInfoReceived)
        self.mActionCheckQgisVersion.setEnabled(False)
        self.mMessageBar.pushInfo('版本检查', '正在查询 QGIS 官方版本信息…')
        self.mVersionInfo.checkVersion()
    def versionInfoReceived(self):
        self.mActionCheckQgisVersion.setEnabled(True)
        info = self.mVersionInfo
        if info.mErrorString:
            self.mMessageBar.pushWarning('版本检查', info.mErrorString)
            return
        latest = info.mLatestVersion
        version = f'{latest//10000}.{latest//100%100}.{latest%100}'
        text = f'当前运行库：{Qgis.QGIS_VERSION}；官方最新版本：{version}。'
        if info.newVersionAvailable(): text += '此独立应用仍要求 QGIS 3.34.10，版本检查不会升级运行环境。'
        QMessageBox.information(self, 'QGIS 版本', text)
    def newReport(self, name=None):
        from qgis.core import QgsReport
        if name is None:
            name, ok = QInputDialog.getText(self, '新建报表', '报表名称')
            if not ok: return
        name = name.strip()
        if not name: return
        if self.mProject.layoutManager().layoutByName(name):
            self.mMessageBar.pushWarning('报表', '该名称已存在')
            return
        report = QgsReport(self.mProject)
        report.setName(name)
        if not self.mProject.layoutManager().addLayout(report): return
        self.mProject.setDirty(True)
        return self.openLayoutDesigner(report)
    def createElevationProfile(self):
        if not hasattr(self, 'mElevationProfileWidget'):
            from .elevation.qgselevationprofilewidget import QgsElevationProfileWidget
            self.mElevationProfileWidget = QgsElevationProfileWidget(self)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.mElevationProfileWidget)
        self.mElevationProfileWidget.show()
        self.mElevationProfileWidget.raise_()
        return self.mElevationProfileWidget
    def showPortingStatus(self):
        path = self.writeCoverage()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            # Windows may have no default application associated with .md.
            from qgis.PyQt.QtCore import QProcess
            QProcess.startDetached('notepad.exe', [str(path)])
    def showGeoreferencer(self):
        self.mGeoreferencer.show()
        self.mGeoreferencer.raise_()
        self.mGeoreferencer.activateWindow()
        return self.mGeoreferencer
    def closeEvent(self, event):
        if not self.saveDirty():
            event.ignore()
            return
        for blocker in self.mQgisInterface.mExitBlockers:
            if not blocker.allowExit():
                event.ignore()
                return
        if not self.mGeoreferencer.canClose():
            event.ignore()
            return
        self.mSettings.setValue('PythonDesktop/geometry', self.saveGeometry())
        self.mSettings.setValue('PythonDesktop/state', self.saveState())
        self.prepareToQuit()
        event.accept()

    def prepareToQuit(self):
        # Run after close confirmation, while the event loop and normal layer
        # removal hooks still exist. Native mesh edit datasets must be released
        # before their canvas/undo GUI consumers are destroyed in QGIS 3.34.
        self.mMapCanvas.setMapTool(self.mMapTools['pan'])
        self.mMapCanvas.stopRendering()
        for canvas in self.mAdditionalCanvases: canvas.stopRendering()
        for layer in list(self.mProject.mapLayers().values()):
            if isinstance(layer, QgsMeshLayer) and layer.isEditable():
                layer.rollBackFrameEditing(self.mMeshEditTool.transform(layer), False)
                self.mProject.removeMapLayer(layer.id())

    def shutdown(self):
        if self.mShutdown: return
        self.mUndoWidget.setStack(None)
        self.mMapCanvas.stopRendering()
        for canvas in self.mAdditionalCanvases: canvas.stopRendering()
        self.mShutdown = True
        self.mGeoreferencer.shutdown()
        if hasattr(self, 'mCustomization'): self.mCustomization.shutdown()
        for decoration in self.mDecorationItems:
            if hasattr(decoration, 'shutdown'): decoration.shutdown()
        if hasattr(self, 'mVersionInfo'): self.mVersionInfo.cancel()
        if hasattr(self, 'mElevationProfileWidget'): self.mElevationProfileWidget.shutdown()
        QgsGui.annotationItemGuiRegistry().typeAdded.disconnect(self.annotationItemTypeAdded)
        self.mMapCanvas.setMapTool(self.mMapTools['pan'])
        self.mMapToolsDigitizingTechniqueManager.shutdown()
        self.mMeshEditTool.shutdown()
        self.mMapTools['modifyAnnotation'].shutdown()
        self.mAnnotationItemTools.clear()
        self.mMapTools['pinLabels'].showPinnedLabels(False)
        for key in ('rotatePointSymbols', 'offsetPointSymbol'): self.mMapTools[key].cancel()
        for key in ('pinLabels', 'showHideLabels', 'moveLabel', 'rotateLabel', 'changeLabelProperties'):
            self.mMapTools[key].cancel()
        for task in list(self.mVectorExportTasks):
            task.cancel()
            task.waitForFinished()
        self.clearMapTip()
        self.mStatisticalSummaryDockWidget.shutdown()
        if self.mPluginManager: self.mPluginManager.unloadAll()
        if self.mProcessingPlugin: self.mProcessingPlugin.unload()
        self.mLocatorWidget.locator().cancel()
        self.mMapCanvas.stopRendering()
        for canvas in self.mAdditionalCanvases: canvas.stopRendering()
        for dialog in self.mWindows + self.mLayoutDesigners:
            if not sip.isdeleted(dialog):
                if hasattr(dialog, 'mDockableWidgetHelper'): dialog.mDockableWidgetHelper.dispose()
                sip.delete(dialog)


# Provider sublayer options are nested in the QGIS 3.34 API.
from qgis.core import QgsProviderSublayerDetails
QgsProviderSublayerOptions = QgsProviderSublayerDetails.LayerOptions
