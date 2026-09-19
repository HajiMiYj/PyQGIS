"""Elevation profile controller using native layer, plot and export APIs."""
from pathlib import Path
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer, QSizeF, QSize, QMarginsF
from qgis.PyQt.QtGui import QColor, QPainter, QImage
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QToolBar, QFileDialog, QLabel,
    QSplitter, QMenu, QToolButton, QActionGroup, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QAbstractItemView)
from qgis.core import (Qgis, QgsApplication, QgsGeometry, QgsCoordinateTransform,
    QgsWkbTypes, QgsLayerTree, QgsLayerTreeModel, QgsElevationUtils, QgsSettings,
    QgsUnitTypes, QgsProfileRequest, QgsProfileExporterTask, QgsExpressionContext,
    QgsExpressionContextUtils, QgsAbstractProfileSource, QgsRenderContext, Qgs2DPlot,
    QgsCsException, QgsPointXY)
from qgis.gui import (QgsDockWidget, QgsElevationProfileCanvas, QgsPlotToolPan,
    QgsPlotToolZoom, QgsDoubleSpinBox, QgsLayerTreeView, QgsRubberBand, QgsVertexMarker)
from .qgsmaptoolprofilecurve import QgsMapToolProfileCurve
from .qgsmaptoolprofilecurvefromfeature import QgsMapToolProfileCurveFromFeature
from .qgselevationprofiletoolidentify import QgsElevationProfileToolIdentify
from .qgselevationprofiletoolmeasure import QgsElevationProfileToolMeasure
from src.gui.plot.qgsplottoolxaxiszoom import QgsPlotToolXAxisZoom
from src.gui.elevation.qgselevationprofilelayertreeview import QgsElevationProfileLayerTreeView


class QgsElevationProfileLayersDialog(QDialog):
    def __init__(self, parent, layers):
        super().__init__(parent)
        self.setWindowTitle('添加剖面图层')
        box = QVBoxLayout(self)
        self.listMapLayers = QListWidget()
        self.listMapLayers.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.mLayers = list(layers)
        for layer in self.mLayers:
            item = QListWidgetItem(layer.name(), self.listMapLayers)
            item.setData(Qt.UserRole, layer.id())
        box.addWidget(self.listMapLayers)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.resize(340, 380)

    def selectedLayers(self):
        ids = {item.data(Qt.UserRole) for item in self.listMapLayers.selectedItems()}
        return [layer for layer in self.mLayers if not sip.isdeleted(layer) and layer.id() in ids]


class QgsElevationProfileWidget(QgsDockWidget):
    def __init__(self, app):
        super().__init__('高程剖面', app)
        self.mApp, self.mShutdown = app, False
        self.mProfileCurve = QgsGeometry()
        self.mProfileCrs = app.mMapCanvas.mapSettings().destinationCrs()
        self.mExportTasks = set()
        self.mExcludedLayerIds = set()
        self.mObservedLayers = {}
        self.mUpdatingLayers = False
        self.setObjectName('ElevationProfile')
        content = QWidget(self)
        layout = QVBoxLayout(content)
        self.setWidget(content)
        self.mToolBar = QToolBar(content)
        layout.addWidget(self.mToolBar)
        self.mSplitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.mSplitter)
        self.mLayerTree = QgsLayerTree()
        self.mLayerTreeView = QgsElevationProfileLayerTreeView(self.mLayerTree, self)
        self.mLayerTreeModel = self.mLayerTreeView.layerTreeModel()
        self.mLayerTreeView.populateInitialLayers(app.mProject)
        self.mLayerTreeView.addLayers.connect(self.addLayersInternal)
        self.mLayerTreeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mLayerTreeView.customContextMenuRequested.connect(self.layerContextMenu)
        self.mLayerTreeView.doubleClicked.connect(lambda *_: self.editLayerElevation())
        self.mSplitter.addWidget(self.mLayerTreeView)
        self.mCanvas = QgsElevationProfileCanvas(content)
        self.mCanvas.setProject(app.mProject)
        self.mSplitter.addWidget(self.mCanvas)
        self.mSplitter.setStretchFactor(1, 1)
        self.mSplitter.setSizes([180, 700])
        self.mStatus = QLabel('绘制或拾取剖面线；图层需要启用高程。')
        layout.addWidget(self.mStatus)
        self.mUpdateTimer = QTimer(self)
        self.mUpdateTimer.setSingleShot(True)
        self.mUpdateTimer.setInterval(80)
        self.mUpdateTimer.timeout.connect(self.mCanvas.refresh)
        self.mLayerUpdateTimer = QTimer(self)
        self.mLayerUpdateTimer.setSingleShot(True)
        self.mLayerUpdateTimer.timeout.connect(self.updateCanvasLayers)
        self.mLayerTree.visibilityChanged.connect(self.updateCanvasLayers)
        self.mLayerTree.layerOrderChanged.connect(self.scheduleLayerUpdate)
        self.mLayerTree.removedChildren.connect(self.scheduleLayerUpdate)
        self.mCaptureCurveMapTool = QgsMapToolProfileCurve(app.mMapCanvas, app.mAdvancedDigitizingDockWidget)
        self.mCaptureCurveFromFeatureMapTool = QgsMapToolProfileCurveFromFeature(app.mMapCanvas)
        for tool in (self.mCaptureCurveMapTool, self.mCaptureCurveFromFeatureMapTool):
            tool.curveCaptured.connect(self.setProfileCurve)
        self.mPanTool, self.mZoomTool = QgsPlotToolPan(self.mCanvas), QgsPlotToolZoom(self.mCanvas)
        self.mXAxisZoomTool = QgsPlotToolXAxisZoom(self.mCanvas)
        self.mIdentifyTool = QgsElevationProfileToolIdentify(self.mCanvas, app)
        self.mMeasureTool = QgsElevationProfileToolMeasure(self.mCanvas)
        self.mPlotToolGroup = QActionGroup(self)
        self.setupActions()
        self.mRubberBand = QgsRubberBand(app.mMapCanvas, Qgis.GeometryType.Line)
        self.mRubberBand.setColor(QColor(30, 130, 220, 200))
        self.mRubberBand.setWidth(2)
        self.mToleranceRubberBand = QgsRubberBand(app.mMapCanvas, Qgis.GeometryType.Polygon)
        self.mToleranceRubberBand.setColor(QColor(40, 40, 40, 50))
        self.mHoverMarker = QgsVertexMarker(app.mMapCanvas)
        self.mHoverMarker.setColor(QColor('red'))
        self.mHoverMarker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.mHoverMarker.hide()
        self.mCanvas.setTool(self.mIdentifyTool)
        self.mCanvas.activeJobCountChanged.connect(self.onTotalPendingJobsCountChanged)
        self.mCanvas.canvasPointHovered.connect(self.onCanvasPointHovered)
        self.visibilityChanged.connect(self.visibilityChangedHandler)
        app.mProject.layersWillBeRemoved.connect(self.layersWillBeRemoved)
        app.mProject.layersAdded.connect(self.layersAdded)
        app.mProject.cleared.connect(self.projectCleared)
        app.mMapCanvas.destinationCrsChanged.connect(self.mapCrsChanged)
        self.layersAdded(list(app.mProject.mapLayers().values()))
        self.updateCanvasLayers()
        self.createOrUpdateRubberBands()

    def scheduleLayerUpdate(self, *args):
        # Wait until a drag/reorder has finished removing and reinserting nodes.
        if not self.mUpdatingLayers and not self.mShutdown: self.mLayerUpdateTimer.start(0)

    def addAction(self, name, title, icon, callback, checkable=False, tool=None):
        action = self.mToolBar.addAction(QgsApplication.getThemeIcon('/' + icon), title)
        action.setObjectName(name)
        action.setCheckable(checkable)
        if checkable and tool is None: action.toggled.connect(callback)
        else: action.triggered.connect(lambda _=False: callback())
        if tool is not None:
            tool.setAction(action)
            self.mPlotToolGroup.addAction(action)
        setattr(self, name, action)
        return action

    def setupActions(self):
        self.addAction('addLayerAction', QCoreApplication.translate('QgsElevationProfileWidget', 'Add Layers'), 'mActionAddLayer.svg', self.addLayers)
        show = self.addAction('showLayerTree', QCoreApplication.translate('QgsElevationProfileWidget', 'Show Layer Tree'), 'mIconLayerTree.svg', self.showLayerTreeChanged, True)
        show.setChecked(QgsSettings().value('elevation-profile/show-layer-tree', True, type=bool))
        self.mLayerTreeView.setVisible(show.isChecked())
        self.mToolBar.addSeparator()
        self.addAction('mCaptureCurveAction', '绘制剖面线', 'mActionCaptureLine.svg', lambda: self.mApp.mMapCanvas.setMapTool(self.mCaptureCurveMapTool))
        self.addAction('mCaptureCurveFromFeatureAction', '从地图线要素拾取', 'mActionCaptureCurveFromFeature.svg', lambda: self.mApp.mMapCanvas.setMapTool(self.mCaptureCurveFromFeatureMapTool))
        self.mToolBar.addAction('使用选中线', self.useSelectedFeature)
        self.addAction('mNudgeLeftAction', '向左偏移', 'mActionArrowLeft.svg', self.nudgeLeft)
        self.addAction('mNudgeRightAction', '向右偏移', 'mActionArrowRight.svg', self.nudgeRight)
        self.addAction('clearAction', '清空剖面', 'console/iconClearConsole.svg', self.clear)
        self.mToolBar.addSeparator()
        for name, title, icon, tool in (
            ('identifyToolAction', '识别', 'mActionIdentify.svg', self.mIdentifyTool),
            ('panToolAction', '平移', 'mActionPan.svg', self.mPanTool),
            ('zoomXAxisToolAction', '缩放 X 轴', 'mActionZoomInXAxis.svg', self.mXAxisZoomTool),
            ('zoomToolAction', '框选缩放', 'mActionZoomIn.svg', self.mZoomTool),
            ('measureToolAction', '测量距离和高差', 'mActionMeasure.svg', self.mMeasureTool)):
            self.addAction(name, title, icon, lambda t=tool: self.mCanvas.setTool(t), True, tool)
        self.addAction('resetViewAction', '全图', 'mActionZoomFullExtent.svg', self.mCanvas.zoomFull)
        snapping = self.addAction('enabledSnappingAction', '捕捉剖面', 'mIconSnapping.svg', self.mCanvas.setSnappingEnabled, True)
        snapping.setChecked(True)
        self.mToolBar.addSeparator()
        self.addAction('exportAsPdfAction', '导出 PDF', 'mActionSaveAsPDF.svg', self.exportAsPdf)
        self.addAction('exportAsImageAction', '导出图片', 'mActionSaveMapAsImage.svg', self.exportImage)
        menu = QMenu(self)
        self.mExportActions = []
        for title, mode in [('导出三维要素', Qgis.ProfileExportType.Features3D), ('导出二维剖面', Qgis.ProfileExportType.Profile2D), ('导出距离/高程表', Qgis.ProfileExportType.DistanceVsElevationTable)]:
            action = menu.addAction(title, lambda _=False, m=mode: self.exportResults(m))
            self.mExportActions.append(action)
        button = QToolButton()
        button.setIcon(QgsApplication.getThemeIcon('/mActionFileSaveAs.svg'))
        button.setToolTip('导出剖面数据')
        button.setMenu(menu)
        button.setPopupMode(QToolButton.InstantPopup)
        self.mToolBar.addWidget(button)
        self.mToolBar.addSeparator()
        lock = self.addAction('mLockRatioAction', '锁定轴比例', 'mIconLock.svg', self.axisScaleLockToggled, True)
        lock.setChecked(QgsSettings().value('elevation-profile/lock-axis-scales', False, type=bool))
        self.mTolerance = QgsDoubleSpinBox()
        self.mTolerance.setRange(0, 1e9)
        self.mTolerance.setDecimals(4)
        self.mTolerance.setPrefix('容差：')
        self.mTolerance.setValue(QgsSettings().value('elevation-profile/tolerance', 0.1, type=float))
        self.mTolerance.setKeyboardTracking(False)
        self.mCanvas.setTolerance(self.mTolerance.value())
        self.mTolerance.valueChanged.connect(self.setTolerance)
        self.mToolBar.addWidget(self.mTolerance)
        units = QMenu(QCoreApplication.translate('QgsElevationProfileWidget', 'Distance Units'), self)
        group = QActionGroup(units)
        for unit in (Qgis.DistanceUnit.Kilometers, Qgis.DistanceUnit.Meters,
                     Qgis.DistanceUnit.Centimeters, Qgis.DistanceUnit.Millimeters,
                     Qgis.DistanceUnit.Miles, Qgis.DistanceUnit.NauticalMiles,
                     Qgis.DistanceUnit.Yards, Qgis.DistanceUnit.Feet,
                     Qgis.DistanceUnit.Inches, Qgis.DistanceUnit.Degrees):
            action = units.addAction(QgsUnitTypes.toString(unit))
            action.setCheckable(True)
            action.setData(int(unit))
            group.addAction(action)
            action.triggered.connect(lambda _=False, u=unit: self.mCanvas.setDistanceUnit(u))
        units.aboutToShow.connect(lambda: [a.setChecked(a.data() == int(self.mCanvas.distanceUnit())) for a in units.actions()])
        button = QToolButton()
        button.setText(QCoreApplication.translate('QgsLayoutElevationProfileWidgetBase', 'Unit'))
        button.setMenu(units)
        button.setPopupMode(QToolButton.InstantPopup)
        self.mToolBar.addWidget(button)

    def showLayerTreeChanged(self, visible):
        self.mLayerTreeView.setVisible(visible)
        QgsSettings().setValue('elevation-profile/show-layer-tree', visible)

    def axisScaleLockToggled(self, enabled):
        self.mCanvas.setLockAxisScales(enabled)
        QgsSettings().setValue('elevation-profile/lock-axis-scales', enabled)

    def layersAdded(self, layers):
        for layer in layers:
            if layer.id() in self.mObservedLayers: continue
            properties = layer.elevationProperties()
            if properties is not None:
                properties.changed.connect(self.updateCanvasLayers)
                self.mObservedLayers[layer.id()] = properties
        self.updateCanvasLayers()

    def addLayers(self):
        layers = [layer for layer in self.mApp.mProject.mapLayers().values()
                  if QgsElevationUtils.canEnableElevationForLayer(layer) or (layer.elevationProperties() and layer.elevationProperties().hasElevation())]
        dialog = QgsElevationProfileLayersDialog(self, layers)
        if dialog.exec_(): self.addLayersInternal(dialog.selectedLayers())
        dialog.deleteLater()

    def addLayersInternal(self, layers):
        for layer in layers:
            if self.mApp.mProject.mapLayer(layer.id()) is not layer: continue
            properties = layer.elevationProperties()
            if not ((properties and properties.hasElevation()) or QgsElevationUtils.canEnableElevationForLayer(layer)): continue
            self.mExcludedLayerIds.discard(layer.id())
            QgsElevationUtils.enableElevationForLayer(layer)
            self.mLayerTreeView.addLayer(layer)
            layer.setCustomProperty('_include_in_elevation_profiles', True)
            node = self.mLayerTree.findLayer(layer.id())
            if node: node.setItemVisibilityChecked(True)
        self.mApp.mProject.setDirty(True)
        self.updateCanvasLayers()

    def updateCanvasLayers(self, *args):
        if self.mShutdown or self.mUpdatingLayers: return
        self.mUpdatingLayers = True
        try:
            available = self.mApp.mProject.mapLayers()
            for node in list(self.mLayerTree.findLayers()):
                layer = available.get(node.layerId())
                if layer is None:
                    self.mLayerTree.removeChildNode(node)
            for layer in available.values():
                if layer.id() not in self.mExcludedLayerIds: self.mLayerTreeView.addLayer(layer)
                self.mLayerTreeModel.refreshLayer(layer)
            self.mLayerTreeView.proxyModel().invalidateFilter()
            layers = [node.layer() for node in self.mLayerTree.findLayers() if node.isVisible() and node.layer()
                      and node.layer().elevationProperties() and node.layer().elevationProperties().hasElevation()]
            self.mCanvas.setLayers(list(reversed(layers)))
            self.mUpdateTimer.start()
            if not layers: self.mStatus.setText('没有显示的高程图层；可添加图层或双击图层配置高程。')
        finally: self.mUpdatingLayers = False

    def editLayerElevation(self):
        layer = self.mLayerTreeView.currentLayer()
        if layer: self.mApp.showLayerProperties(layer, 'mOptsPage_Elevation')
        self.updateCanvasLayers()

    def layerContextMenu(self, pos):
        self.mLayerTreeView.setCurrentIndex(self.mLayerTreeView.indexAt(pos))
        menu = QMenu(self)
        menu.addAction('高程属性…', self.editLayerElevation).setEnabled(self.mLayerTreeView.currentLayer() is not None)
        menu.addAction('从此剖面移除', self.removeSelectedLayers)
        menu.addAction('添加图层…', self.addLayers)
        menu.exec_(self.mLayerTreeView.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def removeSelectedLayers(self):
        for layer in self.mLayerTreeView.selectedLayers():
            self.mExcludedLayerIds.add(layer.id())
            node = self.mLayerTree.findLayer(layer.id())
            if node: self.mLayerTree.removeChildNode(node)
        self.updateCanvasLayers()

    def setTolerance(self, value):
        self.mCanvas.setTolerance(value)
        QgsSettings().setValue('elevation-profile/tolerance', value)
        self.createOrUpdateRubberBands()
        self.mUpdateTimer.start()

    def setProfileCurve(self, geometry, resetView=True):
        if geometry.isEmpty() or geometry.type() != QgsWkbTypes.LineGeometry: return False
        if geometry.isMultipart(): geometry = geometry.asGeometryCollection()[0]
        self.mMeasureTool.clear()
        self.mProfileCurve = QgsGeometry(geometry)
        self.mProfileCrs = self.mApp.mMapCanvas.mapSettings().destinationCrs()
        self.mCanvas.setCrs(self.mProfileCrs)
        self.mCanvas.setProfileCurve(self.mProfileCurve.constGet().clone())
        if resetView: self.mCanvas.invalidateCurrentPlotExtent()
        self.createOrUpdateRubberBands()
        self.updateCanvasLayers()
        if self.mApp.mMapCanvas.mapTool() in (self.mCaptureCurveMapTool, self.mCaptureCurveFromFeatureMapTool): self.mApp.setMapTool('pan')
        return True

    def useSelectedFeature(self):
        layer = self.mApp.vectorLayer()
        if not layer or layer.selectedFeatureCount() != 1 or layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.mApp.mMessageBar.pushWarning('高程剖面', '请在一个线图层中选择一个要素')
            return
        geometry = QgsGeometry(layer.selectedFeatures()[0].geometry())
        try: geometry.transform(QgsCoordinateTransform(layer.crs(), self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mApp.mProject))
        except QgsCsException as error:
            self.mApp.mMessageBar.pushWarning('高程剖面', str(error))
            return
        self.setProfileCurve(geometry)

    def nudgeLeft(self): return self.nudgeCurve(Qgis.BufferSide.Left)
    def nudgeRight(self): return self.nudgeCurve(Qgis.BufferSide.Right)

    def nudgeCurve(self, side):
        if self.mProfileCurve.isEmpty(): return False
        distance = self.mTolerance.value() * 2 * (1 if side == Qgis.BufferSide.Left else -1)
        geometry = self.mProfileCurve.offsetCurve(distance, 8, Qgis.JoinStyle.Miter, 2)
        if geometry.isEmpty():
            self.mApp.mMessageBar.pushWarning('高程剖面', '偏移后无法生成有效剖面线')
            return False
        return self.setProfileCurve(geometry, False)

    def createOrUpdateRubberBands(self):
        if not hasattr(self, 'mRubberBand'): return
        valid = not self.mProfileCurve.isEmpty()
        for action in (self.mNudgeLeftAction, self.mNudgeRightAction, self.clearAction, self.exportAsPdfAction, self.exportAsImageAction, *self.mExportActions): action.setEnabled(valid)
        if not valid:
            self.mRubberBand.hide()
            self.mToleranceRubberBand.hide()
            self.mHoverMarker.hide()
            return
        self.mRubberBand.setToGeometry(self.mProfileCurve, self.mProfileCrs)
        self.mRubberBand.setVisible(self.isVisible())
        tolerance = self.mTolerance.value()
        if tolerance > 0:
            self.mToleranceRubberBand.setToGeometry(self.mProfileCurve.buffer(tolerance, 8), self.mProfileCrs)
            self.mToleranceRubberBand.setVisible(self.isVisible())
        else: self.mToleranceRubberBand.hide()

    def onCanvasPointHovered(self, canvasPoint, profilePoint):
        if self.mProfileCurve.isEmpty(): return
        point = self.mProfileCurve.interpolate(profilePoint.distance())
        if point.isEmpty(): self.mHoverMarker.hide(); return
        try:
            transform = QgsCoordinateTransform(self.mProfileCrs, self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mApp.mProject)
            self.mHoverMarker.setCenter(transform.transform(point.asPoint()))
            self.mHoverMarker.setVisible(self.isVisible())
        except QgsCsException: self.mHoverMarker.hide()
        self.mStatus.setText(f'距离 {profilePoint.distance():.6g}；高程 {profilePoint.elevation():.6g}')

    def onTotalPendingJobsCountChanged(self, count):
        self.mStatus.setText('正在生成剖面…' if count else '剖面已更新；可识别、测量或导出')

    def mapCrsChanged(self):
        if self.mProfileCurve.isEmpty(): return
        geometry = QgsGeometry(self.mProfileCurve)
        try: geometry.transform(QgsCoordinateTransform(self.mProfileCrs, self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mApp.mProject))
        except QgsCsException as error:
            self.mApp.mMessageBar.pushWarning('剖面坐标转换', str(error))
            return
        self.setProfileCurve(geometry)

    def clear(self):
        self.mUpdateTimer.stop()
        self.mProfileCurve = QgsGeometry()
        self.mCanvas.clear()
        self.mMeasureTool.clear()
        self.createOrUpdateRubberBands()

    def profileRequest(self):
        if self.mProfileCurve.isEmpty(): return None
        request = QgsProfileRequest(self.mProfileCurve.constGet().clone())
        request.setCrs(self.mProfileCrs)
        request.setTolerance(self.mTolerance.value())
        request.setTransformContext(self.mApp.mProject.transformContext())
        terrain = self.mApp.mProject.elevationProperties().terrainProvider()
        if terrain: request.setTerrainProvider(terrain.clone())
        request.setExpressionContext(QgsExpressionContext([
            QgsExpressionContextUtils.globalScope(), QgsExpressionContextUtils.projectScope(self.mApp.mProject)]))
        return request

    def exportResults(self, exportType, path=None, runAsync=True):
        request = self.profileRequest()
        if request is None: return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, '导出剖面数据', QgsSettings().value('lastProfileExportDir', ''), 'GeoPackage (*.gpkg);;GeoJSON (*.geojson);;CSV (*.csv);;DXF (*.dxf)')
            if not path: return None
        task = QgsProfileExporterTask([layer for layer in self.mCanvas.layers() if isinstance(layer, QgsAbstractProfileSource)], request, exportType, str(path), self.mApp.mProject.transformContext())
        if not runAsync:
            task.run()
            return task
        self.mExportTasks.add(task)
        task.taskCompleted.connect(lambda t=task: self.exportFinished(t))
        task.taskTerminated.connect(lambda t=task: self.exportFinished(t))
        QgsApplication.taskManager().addTask(task)
        return task

    def exportFinished(self, task):
        self.mExportTasks.discard(task)
        if self.mShutdown: return
        if task.result() == QgsProfileExporterTask.ExportResult.Success:
            files = task.createdFiles()
            if files: QgsSettings().setValue('lastProfileExportDir', str(Path(files[0]).parent))
            self.mApp.mMessageBar.pushSuccess('剖面导出', '、'.join(files) or '导出完成')
        else: self.mApp.mMessageBar.pushWarning('剖面导出', task.error() or str(task.result()))

    def plotSettings(self):
        plot = Qgs2DPlot()
        distance, elevation = self.mCanvas.visibleDistanceRange(), self.mCanvas.visibleElevationRange()
        factor = QgsUnitTypes.fromUnitToUnitFactor(self.mCanvas.distanceUnit(), self.mCanvas.crs().mapUnits())
        plot.setXMinimum(distance.lower() / factor)
        plot.setXMaximum(distance.upper() / factor)
        plot.setYMinimum(elevation.lower())
        plot.setYMaximum(elevation.upper())
        # The native canvas' plot() is not bound. Compute readable intervals for
        # its visible ranges instead of using Qgs2DPlot's fixed defaults.
        image = QImage(1, 1, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        try:
            plot.setSize(QSizeF(max(1, self.mCanvas.width()), max(1, self.mCanvas.height())))
            plot.calculateOptimisedIntervals(QgsRenderContext.fromQPainter(painter))
        finally: painter.end()
        return plot

    def exportImage(self, path=None, width=1600, height=900, settingsDialog=None):
        if self.mProfileCurve.isEmpty(): return False
        interactive = path is None
        if interactive: path, _ = QFileDialog.getSaveFileName(self, '导出剖面图', QgsSettings().value('lastProfileExportDir', ''), 'PNG (*.png)')
        if not path: return False
        plot = self.plotSettings()
        if interactive or settingsDialog is not None:
            from .qgselevationprofileimageexportdialog import QgsElevationProfileImageExportDialog
            dialog = settingsDialog or QgsElevationProfileImageExportDialog(self)
            if settingsDialog is None:
                dialog.setImageSize(QSize(width, height))
                dialog.setPlotSettings(plot)
            accepted = dialog.exec_()
            if accepted:
                size = dialog.imageSize()
                width, height = size.width(), size.height()
                dialog.updatePlotSettings(plot)
            if settingsDialog is None: dialog.deleteLater()
            if not accepted: return False
        if width <= 0 or height <= 0: return False
        if not str(path).lower().endswith('.png'): path = str(path) + '.png'
        image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        if image.isNull():
            self.mApp.mMessageBar.pushWarning('剖面导出', '无法分配图片内存，请减小输出宽高')
            return False
        image.fill(QColor('white'))
        painter = QPainter(image)
        try: self.mCanvas.render(QgsRenderContext.fromQPainter(painter), width, height, plot)
        finally: painter.end()
        success = image.save(str(path), 'PNG')
        if not success: self.mApp.mMessageBar.pushWarning('高程剖面', '无法保存图片')
        else: QgsSettings().setValue('lastProfileExportDir', str(Path(path).parent))
        return success

    def exportAsPdf(self, path=None, settingsDialog=None):
        from qgis.PyQt.QtPrintSupport import QPrinter
        from qgis.PyQt.QtGui import QPageSize, QPageLayout
        if self.mProfileCurve.isEmpty(): return False
        interactive = path is None
        if interactive: path, _ = QFileDialog.getSaveFileName(self, '导出剖面 PDF', QgsSettings().value('lastProfileExportDir', ''), 'PDF (*.pdf)')
        if not path: return False
        plot, pageSize = self.plotSettings(), QSizeF(297, 210)
        if interactive or settingsDialog is not None:
            from .qgselevationprofilepdfexportdialog import QgsElevationProfilePdfExportDialog
            dialog = settingsDialog or QgsElevationProfilePdfExportDialog(self)
            if settingsDialog is None: dialog.setPlotSettings(plot)
            accepted = dialog.exec_()
            if accepted:
                pageSize = dialog.pageSizeMM().toQSizeF()
                dialog.updatePlotSettings(plot)
            if settingsDialog is None: dialog.deleteLater()
            if not accepted: return False
        if not str(path).lower().endswith('.pdf'): path = str(path) + '.pdf'
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(path))
        pageLayout = QPageLayout(QPageSize(pageSize, QPageSize.Millimeter), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0))
        pageLayout.setMode(QPageLayout.FullPageMode)
        printer.setPageLayout(pageLayout)
        printer.setFullPage(True)
        printer.setResolution(300)
        painter = QPainter()
        if not painter.begin(printer):
            self.mApp.mMessageBar.pushWarning('剖面导出', '无法创建 PDF')
            return False
        try:
            area = printer.pageRect(QPrinter.DevicePixel)
            context = QgsRenderContext.fromQPainter(painter)
            context.setFlag(Qgis.RenderContextFlag.ForceVectorOutput, True)
            self.mCanvas.render(context, area.width(), area.height(), plot)
        finally: painter.end()
        QgsSettings().setValue('lastProfileExportDir', str(Path(path).parent))
        return True

    def visibilityChangedHandler(self, visible):
        if self.mShutdown: return
        if not visible:
            if self.mApp.mMapCanvas.mapTool() in (self.mCaptureCurveMapTool, self.mCaptureCurveFromFeatureMapTool): self.mApp.setMapTool('pan')
            self.mCaptureCurveMapTool.stopCapturing()
            self.mMeasureTool.clear()
        self.createOrUpdateRubberBands()

    def layersWillBeRemoved(self, ids):
        self.mUpdatingLayers = True
        try:
            for layerId in ids:
                properties = self.mObservedLayers.pop(layerId, None)
                if properties and not sip.isdeleted(properties): properties.changed.disconnect(self.updateCanvasLayers)
                node = self.mLayerTree.findLayer(layerId)
                if node: self.mLayerTree.removeChildNode(node)
                self.mExcludedLayerIds.discard(layerId)
            self.mCanvas.setLayers([layer for layer in self.mCanvas.layers() if layer.id() not in ids])
        finally: self.mUpdatingLayers = False
        self.mUpdateTimer.start()

    def projectCleared(self):
        self.clear()
        self.mExcludedLayerIds.clear()

    def shutdown(self):
        if self.mShutdown: return
        self.mShutdown = True
        self.mUpdateTimer.stop()
        self.mLayerUpdateTimer.stop()
        self.mApp.mProject.layersWillBeRemoved.disconnect(self.layersWillBeRemoved)
        self.mApp.mProject.layersAdded.disconnect(self.layersAdded)
        self.mApp.mProject.cleared.disconnect(self.projectCleared)
        self.mApp.mMapCanvas.destinationCrsChanged.disconnect(self.mapCrsChanged)
        for properties in self.mObservedLayers.values():
            if not sip.isdeleted(properties): properties.changed.disconnect(self.updateCanvasLayers)
        self.mObservedLayers.clear()
        for task in list(self.mExportTasks):
            if not sip.isdeleted(task): task.cancel(); task.waitForFinished()
        self.mExportTasks.clear()
        self.mCanvas.unsetTool(self.mCanvas.tool())
        self.mMeasureTool.dispose()
        for band in (self.mRubberBand, self.mToleranceRubberBand, self.mHoverMarker):
            self.mApp.mMapCanvas.scene().removeItem(band)
            sip.delete(band)
        sip.delete(self.mCanvas)
