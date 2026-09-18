"""Port of src/app/qgssnappingwidget.cpp (QgsSnappingWidget).

Upstream picks its display mode from the parent widget: a QToolBar parent
populates that toolbar with individual actions and widget buttons, any other
parent builds an inline widget for the "Project Snapping Settings" dialog.
Both modes are reproduced here so the snapping toolbar keeps upstream ordering,
icons, object names and menu contents instead of collapsing into one widget.

QgsSnappingLayerTreeModel / QgsSnappingLayerDelegate are application classes
without Python bindings, so the advanced per-layer configuration is rebuilt
with the bound QgsSnappingConfig individual-layer APIs.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QToolBar, QToolButton, QComboBox,
    QCheckBox, QDialog, QTableWidget, QTableWidgetItem, QDialogButtonBox, QAction,
    QMenu, QWidgetAction, QLabel, QAbstractItemView,
)
from qgis.core import (
    Qgis, QgsApplication, QgsSnappingConfig, QgsVectorLayer, QgsUnitTypes, QgsProject,
)
from qgis.gui import QgsDoubleSpinBox, QgsScaleWidget


class QgsSnappingWidget(QWidget):
    # qgsEnumList<Qgis::SnappingType>() declaration order, NoSnap excluded.
    SNAPPING_TYPES = (
        Qgis.SnappingType.Vertex,
        Qgis.SnappingType.Segment,
        Qgis.SnappingType.Area,
        Qgis.SnappingType.Centroid,
        Qgis.SnappingType.MiddleOfSegment,
        Qgis.SnappingType.LineEndpoint,
    )

    def __init__(self, project, canvas, parent=None):
        super().__init__(parent)
        self.mProject, self.mCanvas = project, canvas
        self.mTb = parent if isinstance(parent, QToolBar) else None
        self.mDisplayMode = 'toolbar' if self.mTb is not None else 'widget'
        self.setObjectName('SnappingOptionToolBar' if self.mDisplayMode == 'toolbar' else 'SnappingOptionDialog')
        self.mAdvancedConfigWidget = None
        self.mMinScaleWidget = None
        self.mMaxScaleWidget = None
        self.mSnappingScaleModeButton = None
        self.mSnappingFlagActions = []
        self.mConfig = project.snappingConfig()

        self.createSnappingActions()
        self.createSnappingButtons()
        self.createAdvancedConfigWidget()
        if self.mTb is not None:
            self.setupToolBar()
        else:
            self.setupWidget()

        project.snappingConfigChanged.connect(self.projectSnapSettingsChanged)
        project.topologicalEditingChanged.connect(self.projectTopologicalEditingChanged)
        project.avoidIntersectionsModeChanged.connect(self.projectAvoidIntersectionModeChanged)
        canvas.destinationCrsChanged.connect(self.updateToleranceDecimals)

        # Slightly modify the config so the settings-changed code does not early-exit.
        self.mConfig = project.snappingConfig()
        self.mConfig.setEnabled(not self.mConfig.enabled())
        self.projectSnapSettingsChanged()
        self.projectAvoidIntersectionModeChanged()
        self.modeChanged()
        self.updateToleranceDecimals()

    # ------------------------------------------------------------------ actions
    def createSnappingActions(self):
        self.mEnabledAction = QAction('Toggle Snapping', self)
        self.mEnabledAction.setCheckable(True)
        self.mEnabledAction.setIcon(QgsApplication.getThemeIcon('/mIconSnapping.svg'))
        self.mEnabledAction.setToolTip('启用捕捉 (S)')
        self.mEnabledAction.setShortcut('S')
        self.mEnabledAction.setObjectName('EnableSnappingAction')
        self.mEnabledAction.toggled.connect(self.enableSnapping)

        self.mTopologicalEditingAction = QAction('Topological Editing', self)
        self.mTopologicalEditingAction.setCheckable(True)
        self.mTopologicalEditingAction.setIcon(QgsApplication.getThemeIcon('/mIconTopologicalEditing.svg'))
        self.mTopologicalEditingAction.setToolTip('启用拓扑编辑')
        self.mTopologicalEditingAction.setObjectName('TopologicalEditingAction')
        self.mTopologicalEditingAction.toggled.connect(self.enableTopologicalEditing)

        self.mIntersectionSnappingAction = QAction('Snapping on Intersection', self)
        self.mIntersectionSnappingAction.setCheckable(True)
        self.mIntersectionSnappingAction.setIcon(QgsApplication.getThemeIcon('/mIconSnappingIntersection.svg'))
        self.mIntersectionSnappingAction.setToolTip('启用交点捕捉')
        self.mIntersectionSnappingAction.setObjectName('IntersectionSnappingAction')
        self.mIntersectionSnappingAction.toggled.connect(self.enableIntersectionSnapping)

        self.mEnableTracingAction = QAction('Enable Tracing', self)
        self.mEnableTracingAction.setCheckable(True)
        self.mEnableTracingAction.setIcon(QgsApplication.getThemeIcon('/mActionTracing.svg'))
        self.mEnableTracingAction.setToolTip('启用追踪 (T)')
        self.mEnableTracingAction.setShortcut('T')
        self.mEnableTracingAction.setObjectName('EnableTracingAction')

        self.mSelfSnappingAction = QAction('Self-snapping', self)
        self.mSelfSnappingAction.setCheckable(True)
        self.mSelfSnappingAction.setIcon(QgsApplication.getThemeIcon('/mIconSnappingSelf.svg'))
        self.mSelfSnappingAction.setToolTip('启用自身捕捉')
        self.mSelfSnappingAction.setObjectName('SelfSnappingAction')
        self.mSelfSnappingAction.toggled.connect(self.enableSelfSnapping)

    # ------------------------------------------------------------------ buttons
    def createSnappingButtons(self):
        # avoid-overlap mode button
        self.mAvoidIntersectionsModeButton = QToolButton(self)
        self.mAvoidIntersectionsModeButton.setToolTip('启用避免重叠后，绘制的要素将被裁剪以避免与现有要素重叠。')
        self.mAvoidIntersectionsModeButton.setPopupMode(QToolButton.InstantPopup)
        avoidMenu = QMenu('设置避免重叠模式', self)
        self.mAllowIntersectionsAction = QAction(QgsApplication.getThemeIcon('/mActionAllowIntersections.svg'), '允许重叠', avoidMenu)
        self.mAvoidIntersectionsCurrentLayerAction = QAction(
            QgsApplication.getThemeIcon('/mActionAvoidIntersectionsCurrentLayer.svg'), '当前图层避免重叠', avoidMenu)
        self.mAvoidIntersectionsCurrentLayerAction.setToolTip(
            '当前图层避免重叠。\n注意：该选项会作用于所编辑几何的所有顶点，即使位于当前视图范围之外。')
        self.mAvoidIntersectionsLayersAction = QAction(
            QgsApplication.getThemeIcon('/mActionAvoidIntersectionsLayers.svg'), '跟随高级配置', avoidMenu)
        for action in (self.mAllowIntersectionsAction, self.mAvoidIntersectionsCurrentLayerAction,
                       self.mAvoidIntersectionsLayersAction):
            avoidMenu.addAction(action)
        self.mAvoidIntersectionsModeButton.setMenu(avoidMenu)
        self.mAvoidIntersectionsModeButton.setObjectName('AvoidIntersectionsModeButton')
        self.mAvoidIntersectionsModeButton.triggered.connect(self.avoidIntersectionsModeButtonTriggered)

        # snapping mode button
        self.mModeButton = QToolButton(self)
        self.mModeButton.setToolTip('捕捉模式')
        self.mModeButton.setPopupMode(QToolButton.InstantPopup)
        modeMenu = QMenu('设置捕捉模式', self)
        self.mAllLayersAction = QAction(QgsApplication.getThemeIcon('/mIconSnappingAllLayers.svg'), '所有图层', modeMenu)
        self.mActiveLayerAction = QAction(QgsApplication.getThemeIcon('/mIconSnappingActiveLayer.svg'), '当前图层', modeMenu)
        self.mAdvancedModeAction = QAction(QgsApplication.getThemeIcon('/mIconSnappingAdvanced.svg'), '高级配置', modeMenu)
        modeMenu.addAction(self.mAllLayersAction)
        modeMenu.addAction(self.mActiveLayerAction)
        modeMenu.addAction(self.mAdvancedModeAction)
        if self.mDisplayMode == 'toolbar':
            modeMenu.addSeparator()
            openDialogAction = QAction('打开捕捉选项…', modeMenu)
            openDialogAction.triggered.connect(self.openSnappingOptions)
            modeMenu.addAction(openDialogAction)
        self.mModeButton.setMenu(modeMenu)
        self.mModeButton.setObjectName('SnappingModeButton')
        self.mModeButton.triggered.connect(self.modeButtonTriggered)

        # snapping type button
        self.mTypeButton = QToolButton(self)
        self.mTypeButton.setToolTip('捕捉类型')
        self.mTypeButton.setPopupMode(QToolButton.InstantPopup)
        typeMenu = QMenu('设置捕捉类型', self)
        for snappingType in self.SNAPPING_TYPES:
            action = QAction(QgsSnappingConfig.snappingTypeToIcon(snappingType),
                             QgsSnappingConfig.snappingTypeToString(snappingType), typeMenu)
            action.setData(int(snappingType))
            action.setCheckable(True)
            typeMenu.addAction(action)
            self.mSnappingFlagActions.append(action)
        self.mTypeButton.setMenu(typeMenu)
        self.mTypeButton.setObjectName('SnappingTypeButton')
        self.mTypeButton.triggered.connect(self.typeButtonTriggered)

        # tolerance
        self.mToleranceSpinBox = QgsDoubleSpinBox()
        self.mToleranceSpinBox.setDecimals(5)
        self.mToleranceSpinBox.setMaximum(99999999.99)
        self.mToleranceSpinBox.setToolTip('以所选单位表示的捕捉容差')
        self.mToleranceSpinBox.setObjectName('SnappingToleranceSpinBox')
        self.mToleranceSpinBox.valueChanged.connect(self.changeTolerance)

        # units
        self.mUnitsComboBox = QComboBox()
        self.mUnitsComboBox.addItem('px', int(Qgis.MapToolUnit.Pixels))
        mapCanvasDistanceUnits = QgsUnitTypes.toString(self.mCanvas.mapSettings().mapUnits())
        self.mUnitsComboBox.addItem(mapCanvasDistanceUnits, int(Qgis.MapToolUnit.Project))
        self.mUnitsComboBox.setToolTip(f'捕捉单位类型：像素 (px) 或工程/地图单位 ({mapCanvasDistanceUnits})')
        self.mUnitsComboBox.setObjectName('SnappingUnitComboBox')
        self.mUnitsComboBox.currentIndexChanged.connect(self.changeUnit)

        # tracing offset menu
        self.mTracingOffsetSpinBox = QgsDoubleSpinBox()
        self.mTracingOffsetSpinBox.setRange(-1000000, 1000000)
        self.mTracingOffsetSpinBox.setDecimals(6)
        tracingMenu = QMenu(self)
        tracingWidget = QWidget()
        tracingLayout = QVBoxLayout(tracingWidget)
        tracingLayout.addWidget(QLabel('偏移'))
        tracingLayout.addWidget(self.mTracingOffsetSpinBox)
        tracingWidgetAction = QWidgetAction(tracingMenu)
        tracingWidgetAction.setDefaultWidget(tracingWidget)
        tracingMenu.addAction(tracingWidgetAction)
        self.mEnableTracingAction.setMenu(tracingMenu)

        # edit advanced configuration button
        self.mEditAdvancedConfigButton = QToolButton(self)
        self.mEditAdvancedConfigButton.setPopupMode(QToolButton.InstantPopup)
        self.mEditAdvancedConfigButton.setIcon(QgsApplication.getThemeIcon('/mActionShowAllLayers.svg'))
        self.mEditAdvancedConfigButton.setToolTip('编辑高级配置')
        self.mEditAdvancedConfigButton.setObjectName('EditAdvancedConfigurationButton')
        self.mEditAdvancedConfigMenu = QMenu(self)
        self.mEditAdvancedConfigButton.setMenu(self.mEditAdvancedConfigMenu)

    def setupToolBar(self):
        tb = self.mTb
        tb.addAction(self.mEnabledAction)
        self.mModeAction = tb.addWidget(self.mModeButton)

        editAction = QWidgetAction(self.mEditAdvancedConfigMenu)
        editAction.setDefaultWidget(self.mAdvancedConfigWidget)
        self.mEditAdvancedConfigMenu.addAction(editAction)
        self.mEditAdvancedConfigAction = tb.addWidget(self.mEditAdvancedConfigButton)

        self.mTypeAction = tb.addWidget(self.mTypeButton)
        self.mToleranceAction = tb.addWidget(self.mToleranceSpinBox)
        self.mUnitAction = tb.addWidget(self.mUnitsComboBox)

        tb.addAction(self.mTopologicalEditingAction)
        self.mAvoidIntersectionsModeAction = tb.addWidget(self.mAvoidIntersectionsModeButton)
        tb.addAction(self.mIntersectionSnappingAction)
        tb.addAction(self.mEnableTracingAction)
        tb.addAction(self.mSelfSnappingAction)

    def setupWidget(self):
        self.mMinScaleWidget = QgsScaleWidget()
        self.mMinScaleWidget.setToolTip('启用捕捉的最小比例尺（即最“缩小”的比例尺）')
        self.mMinScaleWidget.setObjectName('SnappingMinScaleSpinBox')
        self.mMinScaleWidget.scaleChanged.connect(self.changeMinScale)

        self.mMaxScaleWidget = QgsScaleWidget()
        self.mMaxScaleWidget.setToolTip('启用捕捉的最大比例尺（即最“放大”的比例尺）')
        self.mMaxScaleWidget.setObjectName('SnappingMaxScaleSpinBox')
        self.mMaxScaleWidget.scaleChanged.connect(self.changeMaxScale)

        self.mSnappingScaleModeButton = QToolButton(self)
        self.mSnappingScaleModeButton.setToolTip('捕捉比例尺模式')
        self.mSnappingScaleModeButton.setPopupMode(QToolButton.InstantPopup)
        scaleModeMenu = QMenu('设置捕捉比例尺模式', self)
        self.mDefaultSnappingScaleAct = QAction(QgsApplication.getThemeIcon('/mIconSnappingOnScale.svg'), '禁用', scaleModeMenu)
        self.mDefaultSnappingScaleAct.setToolTip('禁用比例尺依赖')
        self.mGlobalSnappingScaleAct = QAction(QgsApplication.getThemeIcon('/mIconSnappingOnScale.svg'), '全局', scaleModeMenu)
        self.mGlobalSnappingScaleAct.setToolTip('全局比例尺依赖')
        self.mPerLayerSnappingScaleAct = QAction(QgsApplication.getThemeIcon('/mIconSnappingOnScale.svg'), '逐图层', scaleModeMenu)
        self.mPerLayerSnappingScaleAct.setToolTip('逐图层比例尺依赖')
        for action in (self.mDefaultSnappingScaleAct, self.mGlobalSnappingScaleAct, self.mPerLayerSnappingScaleAct):
            scaleModeMenu.addAction(action)
        self.mSnappingScaleModeButton.setMenu(scaleModeMenu)
        self.mSnappingScaleModeButton.setObjectName('SnappingScaleModeButton')
        self.mSnappingScaleModeButton.triggered.connect(self.snappingScaleModeTriggered)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        enabledButton = QToolButton(self)
        enabledButton.setDefaultAction(self.mEnabledAction)
        layout.addWidget(enabledButton)
        layout.addWidget(self.mModeButton)
        layout.addWidget(self.mTypeButton)
        layout.addWidget(self.mToleranceSpinBox)
        layout.addWidget(self.mUnitsComboBox)
        self.mSnappingScaleModeButton.setDefaultAction(self.mDefaultSnappingScaleAct)
        layout.addWidget(self.mSnappingScaleModeButton)
        layout.addWidget(self.mMinScaleWidget)
        layout.addWidget(self.mMaxScaleWidget)
        for action in (self.mTopologicalEditingAction, self.mIntersectionSnappingAction, self.mSelfSnappingAction):
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            layout.addWidget(button)
        layout.addWidget(self.mAvoidIntersectionsModeButton)

        topLayout = QGridLayout(self)
        topLayout.addLayout(layout, 0, 0, Qt.AlignLeft | Qt.AlignTop)
        topLayout.addWidget(self.mAdvancedConfigWidget, 1, 0)

    # ------------------------------------------------- advanced configuration
    def createAdvancedConfigWidget(self):
        self.mAdvancedConfigWidget = QWidget(self)
        layout = QVBoxLayout(self.mAdvancedConfigWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mAdvancedTable = QTableWidget(0, 7)
        self.mAdvancedTable.setHorizontalHeaderLabels(
            ['图层', '启用', '类型', '容差', '单位', '最小比例尺', '最大比例尺'])
        self.mAdvancedTable.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.mAdvancedTable)
        self.mAdvancedEditors = []
        self.refreshAdvancedConfig()

    def refreshAdvancedConfig(self):
        layers = [l for l in self.mProject.mapLayers().values() if isinstance(l, QgsVectorLayer)]
        table = self.mAdvancedTable
        table.setRowCount(len(layers))
        self.mAdvancedEditors = []
        config = self.mProject.snappingConfig()
        for row, layer in enumerate(layers):
            layerConfig = config.individualLayerSettings(layer)
            table.setItem(row, 0, QTableWidgetItem(layer.name()))
            enabled = QCheckBox()
            enabled.setChecked(layerConfig.enabled())
            kind = QComboBox()
            for action in self.mTypeButton.menu().actions():
                kind.addItem(action.icon(), action.text(), action.data())
            QgsSnappingWidget.selectData(kind, layerConfig.typeFlag())
            tolerance = advancedSpinBox()
            tolerance.setRange(0, 1e6)
            tolerance.setValue(layerConfig.tolerance() if layerConfig.valid() else 12)
            units = QComboBox()
            for index in range(self.mUnitsComboBox.count()):
                units.addItem(self.mUnitsComboBox.itemText(index), self.mUnitsComboBox.itemData(index))
            units.setCurrentIndex(max(0, units.findData(int(layerConfig.units()))))
            minimum, maximum = advancedSpinBox(), advancedSpinBox()
            for spin, value in ((minimum, layerConfig.minimumScale()), (maximum, layerConfig.maximumScale())):
                spin.setRange(0, 1e12)
                spin.setValue(value)
            for column, widget in enumerate([enabled, kind, tolerance, units, minimum, maximum], 1):
                table.setCellWidget(row, column, widget)
            self.mAdvancedEditors.append((layer, enabled, kind, tolerance, units, minimum, maximum))

    def applyAdvancedConfig(self):
        config = self.mProject.snappingConfig()
        for layer, enabled, kind, tolerance, units, minimum, maximum in self.mAdvancedEditors:
            config.setIndividualLayerSettings(layer, QgsSnappingConfig.IndividualLayerSettings(
                enabled.isChecked(), Qgis.SnappingType(kind.currentData()), tolerance.value(),
                Qgis.MapToolUnit(units.currentData()), minimum.value(), maximum.value()))
        self.mProject.setSnappingConfig(config)

    @staticmethod
    def selectData(combo, value):
        # Qgis.SnappingTypes is a SIP flag wrapper; findData does not reliably
        # compare its value against the individual enum members.
        for index in range(combo.count()):
            if int(combo.itemData(index)) == int(value):
                combo.setCurrentIndex(index)
                return
        combo.addItem('自定义类型', int(value))
        combo.setCurrentIndex(combo.count() - 1)

    def editAdvancedConfig(self):
        """Dialog wrapper kept for QgisApp::snappingOptions on the toolbar instance."""
        dialog = QDialog(self)
        dialog.setWindowTitle('项目捕捉设置')
        dialog.resize(900, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.mAdvancedConfigWidget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self.refreshAdvancedConfig()
        if dialog.exec_():
            self.applyAdvancedConfig()

    def openSnappingOptions(self):
        from src.app.qgisapp import QgisApp
        if QgisApp.instance() is not None:
            QgisApp.instance().snappingOptions()

    # ---------------------------------------------------------------- handlers
    def config(self):
        return self.mProject.snappingConfig()

    def setConfig(self, config):
        if not (self.mConfig == config):
            self.mConfig = config

    def enableSnappingAction(self):
        return self.mEnabledAction

    def enableTracingAction(self):
        return self.mEnableTracingAction

    def tracingOffsetSpinBox(self):
        return self.mTracingOffsetSpinBox

    def enableSnapping(self, checked):
        self.toggleSnappingWidgets(checked)
        self.mConfig.setEnabled(checked)
        self.mProject.setSnappingConfig(self.mConfig)

    def toggleSnappingWidgets(self, enabled):
        self.mModeButton.setEnabled(enabled)
        self.mTypeButton.setEnabled(enabled)
        self.mToleranceSpinBox.setEnabled(enabled)
        if self.mSnappingScaleModeButton:
            self.mSnappingScaleModeButton.setEnabled(enabled)
        if self.mMinScaleWidget:
            self.mMinScaleWidget.setEnabled(enabled and self.mConfig.scaleDependencyMode() == QgsSnappingConfig.Global)
        if self.mMaxScaleWidget:
            self.mMaxScaleWidget.setEnabled(enabled and self.mConfig.scaleDependencyMode() == QgsSnappingConfig.Global)
        self.mUnitsComboBox.setEnabled(enabled)
        if getattr(self, 'mEditAdvancedConfigAction', None):
            self.mEditAdvancedConfigAction.setEnabled(enabled)
        if self.mAdvancedConfigWidget:
            self.mAdvancedConfigWidget.setEnabled(enabled)
        self.mIntersectionSnappingAction.setEnabled(enabled)
        self.mSelfSnappingAction.setEnabled(enabled)
        self.mEnableTracingAction.setEnabled(enabled)

    def projectSnapSettingsChanged(self, *args):
        config = self.mProject.snappingConfig()
        if self.mConfig == config:
            return
        self.mConfig = config
        self.mEnabledAction.setChecked(config.enabled())
        mode = config.mode()
        target = {Qgis.SnappingMode.AllLayers: self.mAllLayersAction,
                  Qgis.SnappingMode.ActiveLayer: self.mActiveLayerAction,
                  Qgis.SnappingMode.AdvancedConfiguration: self.mAdvancedModeAction}.get(mode)
        if target is not None and self.mModeButton.defaultAction() is not target:
            self.mModeButton.setDefaultAction(target)
            self.modeChanged()
            self.updateToleranceDecimals()
        for action in self.mSnappingFlagActions:
            action.setChecked(bool(int(config.typeFlag()) & int(action.data())))
            if action.isChecked():
                self.mTypeButton.setDefaultAction(action)
        if int(self.mUnitsComboBox.currentData()) != int(config.units()):
            index = self.mUnitsComboBox.findData(int(config.units()))
            if index >= 0:
                self.mUnitsComboBox.setCurrentIndex(index)
        if abs(self.mToleranceSpinBox.value() - config.tolerance()) > 1e-12:
            self.mToleranceSpinBox.setValue(config.tolerance())
        if self.mMinScaleWidget and self.mMinScaleWidget.scale() != config.minimumScale():
            self.mMinScaleWidget.setScale(config.minimumScale())
        if self.mMaxScaleWidget and self.mMaxScaleWidget.scale() != config.maximumScale():
            self.mMaxScaleWidget.setScale(config.maximumScale())
        if self.mSnappingScaleModeButton:
            scaleTarget = {QgsSnappingConfig.Disabled: self.mDefaultSnappingScaleAct,
                           QgsSnappingConfig.Global: self.mGlobalSnappingScaleAct,
                           QgsSnappingConfig.PerLayer: self.mPerLayerSnappingScaleAct}.get(config.scaleDependencyMode())
            if scaleTarget is not None:
                self.mSnappingScaleModeButton.setDefaultAction(scaleTarget)
        if config.intersectionSnapping() != self.mIntersectionSnappingAction.isChecked():
            self.mIntersectionSnappingAction.setChecked(config.intersectionSnapping())
        if config.selfSnapping() != self.mSelfSnappingAction.isChecked():
            self.mSelfSnappingAction.setChecked(config.selfSnapping())
        self.toggleSnappingWidgets(config.enabled())

    def projectAvoidIntersectionModeChanged(self, *args):
        mode = self.mProject.avoidIntersectionsMode()
        target = {Qgis.AvoidIntersectionsMode.AllowIntersections: self.mAllowIntersectionsAction,
                  Qgis.AvoidIntersectionsMode.AvoidIntersectionsCurrentLayer: self.mAvoidIntersectionsCurrentLayerAction,
                  Qgis.AvoidIntersectionsMode.AvoidIntersectionsLayers: self.mAvoidIntersectionsLayersAction}.get(mode)
        if target is None:
            return
        self.mAvoidIntersectionsModeButton.setDefaultAction(target)
        for action in (self.mAllowIntersectionsAction, self.mAvoidIntersectionsCurrentLayerAction,
                       self.mAvoidIntersectionsLayersAction):
            action.setChecked(action is target)

    def projectTopologicalEditingChanged(self, *args):
        if self.mProject.topologicalEditing() != self.mTopologicalEditingAction.isChecked():
            self.mTopologicalEditingAction.setChecked(self.mProject.topologicalEditing())

    def avoidIntersectionsModeButtonTriggered(self, action):
        if action not in (self.mAllowIntersectionsAction, self.mAvoidIntersectionsCurrentLayerAction,
                          self.mAvoidIntersectionsLayersAction):
            return
        if action is self.mAvoidIntersectionsModeButton.defaultAction():
            return
        self.mAvoidIntersectionsModeButton.setDefaultAction(action)
        mode = {id(self.mAllowIntersectionsAction): Qgis.AvoidIntersectionsMode.AllowIntersections,
                id(self.mAvoidIntersectionsCurrentLayerAction): Qgis.AvoidIntersectionsMode.AvoidIntersectionsCurrentLayer,
                id(self.mAvoidIntersectionsLayersAction): Qgis.AvoidIntersectionsMode.AvoidIntersectionsLayers}[id(action)]
        self.mProject.setAvoidIntersectionsMode(mode)

    def modeButtonTriggered(self, action):
        if action not in (self.mAllLayersAction, self.mActiveLayerAction, self.mAdvancedModeAction):
            return
        if action is self.mModeButton.defaultAction():
            return
        self.mModeButton.setDefaultAction(action)
        mode = {id(self.mAllLayersAction): Qgis.SnappingMode.AllLayers,
                id(self.mActiveLayerAction): Qgis.SnappingMode.ActiveLayer,
                id(self.mAdvancedModeAction): Qgis.SnappingMode.AdvancedConfiguration}[id(action)]
        self.mConfig.setMode(mode)
        self.mProject.setSnappingConfig(self.mConfig)
        self.updateToleranceDecimals()
        self.modeChanged()

    def typeButtonTriggered(self, action):
        if action not in self.mSnappingFlagActions:
            return
        flag = int(action.data())
        typeFlag = int(self.mConfig.typeFlag()) ^ flag
        if typeFlag & flag:
            self.mTypeButton.setDefaultAction(action)
        else:
            for candidate in self.mSnappingFlagActions:
                if typeFlag & int(candidate.data()):
                    self.mTypeButton.setDefaultAction(candidate)
                    break
        self.mConfig.setTypeFlag(Qgis.SnappingTypes(typeFlag))
        self.mProject.setSnappingConfig(self.mConfig)

    def snappingScaleModeTriggered(self, action):
        self.mSnappingScaleModeButton.setDefaultAction(action)
        mode = {id(self.mDefaultSnappingScaleAct): QgsSnappingConfig.Disabled,
                id(self.mGlobalSnappingScaleAct): QgsSnappingConfig.Global,
                id(self.mPerLayerSnappingScaleAct): QgsSnappingConfig.PerLayer}.get(id(action))
        if mode is None:
            return
        self.mMinScaleWidget.setEnabled(mode == QgsSnappingConfig.Global)
        self.mMaxScaleWidget.setEnabled(mode == QgsSnappingConfig.Global)
        self.mConfig.setScaleDependencyMode(mode)
        self.mProject.setSnappingConfig(self.mConfig)

    def changeTolerance(self, tolerance):
        self.mConfig.setTolerance(tolerance)
        self.mProject.setSnappingConfig(self.mConfig)

    def changeMinScale(self, minScale):
        self.mConfig.setMinimumScale(minScale)
        self.mProject.setSnappingConfig(self.mConfig)

    def changeMaxScale(self, maxScale):
        self.mConfig.setMaximumScale(maxScale)
        self.mProject.setSnappingConfig(self.mConfig)

    def changeUnit(self, index):
        self.mConfig.setUnits(Qgis.MapToolUnit(self.mUnitsComboBox.itemData(index)))
        self.mProject.setSnappingConfig(self.mConfig)
        self.updateToleranceDecimals()

    def enableTopologicalEditing(self, enabled):
        self.mProject.setTopologicalEditing(enabled)

    def enableIntersectionSnapping(self, enabled):
        self.mConfig.setIntersectionSnapping(enabled)
        self.mProject.setSnappingConfig(self.mConfig)

    def enableSelfSnapping(self, enabled):
        self.mConfig.setSelfSnapping(enabled)
        self.mProject.setSnappingConfig(self.mConfig)

    def updateToleranceDecimals(self):
        if int(self.mConfig.units()) == int(Qgis.MapToolUnit.Pixels):
            self.mToleranceSpinBox.setDecimals(0)
            return
        unitType = QgsUnitTypes.unitType(self.mCanvas.mapUnits())
        self.mToleranceSpinBox.setDecimals(2 if unitType == Qgis.DistanceUnitType.Standard else 5)

    def modeChanged(self):
        advanced = self.mConfig.mode() == Qgis.SnappingMode.AdvancedConfiguration
        if self.mDisplayMode == 'toolbar':
            self.mTypeAction.setVisible(not advanced)
            self.mToleranceAction.setVisible(not advanced)
            self.mUnitAction.setVisible(not advanced)
            self.mEditAdvancedConfigAction.setVisible(advanced)
        else:
            self.mTypeButton.setVisible(not advanced)
            self.mToleranceSpinBox.setVisible(not advanced)
            self.mUnitsComboBox.setVisible(not advanced)
            self.mAdvancedConfigWidget.setVisible(advanced)
            if self.mSnappingScaleModeButton:
                self.mSnappingScaleModeButton.setVisible(advanced)
            if self.mMinScaleWidget:
                self.mMinScaleWidget.setVisible(advanced)
            if self.mMaxScaleWidget:
                self.mMaxScaleWidget.setVisible(advanced)


def advancedSpinBox():
    """QgsDoubleSpinBox for the advanced table, mirroring upstream clear-button settings."""
    spin = QgsDoubleSpinBox()
    spin.setShowClearButton(False)
    return spin
