"""QGIS georeferencer application window, backed by native analysis/GDAL APIs."""
import json
import math
from pathlib import Path
from qgis.PyQt import uic, sip
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QMainWindow, QVBoxLayout, QActionGroup, QFileDialog,
                                QMessageBox, QProgressDialog, QApplication, QDialog,
                                QPlainTextEdit, QDialogButtonBox)
from qgis.core import (Qgis, QgsApplication, QgsPointXY, QgsRasterLayer, QgsVectorLayer,
                       QgsRectangle, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsSettings, QgsContrastEnhancement, QgsRasterMinMaxOrigin, QgsProviderRegistry)
from qgis.gui import (QgsMapCanvas, QgsMessageBar, QgsMapToolPan, QgsMapToolZoom,
                      QgsRasterLayerProperties, QgsVectorLayerProperties, QgsDataSourceSelectDialog)
from qgis.analysis import QgsGcpPoint
from .qgsgcplist import QgsGCPList
from .qgsgcplistwidget import QgsGCPListWidget
from .qgsgcpcanvasitem import QgsGCPCanvasItem
from .qgsgeoreftransform import QgsGeorefTransform
from .qgsrasterchangecoords import QgsRasterChangeCoords
from .qgsimagewarper import QgsImageWarper
from .qgsgeoreftooladdpoint import QgsGeorefToolAddPoint
from .qgsgeoreftooldeletepoint import QgsGeorefToolDeletePoint
from .qgsgeoreftoolmovepoint import QgsGeorefToolMovePoint

ROOT = Path(__file__).resolve().parents[3]


class QgsGeoreferencerMainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__(app, Qt.Window)
        uic.loadUi(str(ROOT / 'src/ui/georeferencer/qgsgeorefpluginguibase.ui'), self)
        self.setObjectName('QgsGeoreferencerMainWindow')
        self.mApp = app
        self.mLayer = None
        self.mSourceFile, self.mGCPFile = '', ''
        self.mPoints, self.mResiduals, self.mMarkers = QgsGCPList(), [], []
        self.mDirty = self.mBusy = self.mShutdown = self.mLinking = False
        self.mPreviousMainTool = self.mCoordinateDialog = None
        self.mCanZoomLast = self.mCanZoomNext = False
        self.mTransform = QgsGeorefTransform()
        self.mRasterChangeCoords = None
        crs = app.mProject.crs()
        self.mSettings = dict(method=QgsGeorefTransform.Method.PolynomialOrder1,
                              crs=crs if crs.isValid() else QgsCoordinateReferenceSystem('EPSG:4326'),
                              output='', resampling='near', compression='LZW', load=True,
                              saveGcp=False, zero=False, resolution=None, worldfile=False)
        saved = QgsSettings()
        self.mShowIds = saved.value('Plugin-GeoReferencer/ShowId', True, type=bool)
        self.mShowCoords = saved.value('Plugin-GeoReferencer/ShowCoords', False, type=bool)
        self.mResidualPixels = saved.value('Plugin-GeoReferencer/ResidualPixels', True, type=bool)
        self.mCanvas = QgsMapCanvas(self)
        self.mCanvas.setProject(app.mProject)
        self.mMessageBar = QgsMessageBar(self)
        layout = QVBoxLayout(self.mCentralwidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mMessageBar)
        layout.addWidget(self.mCanvas)
        self.mGCPListWidget = QgsGCPListWidget(self)
        self.horizontalLayout_2.addWidget(self.mGCPListWidget)
        self.menuView.addAction(self.dockWidgetGCPpoints.toggleViewAction())
        self.mTools = {'pan': QgsMapToolPan(self.mCanvas), 'zoomIn': QgsMapToolZoom(self.mCanvas, False),
                       'zoomOut': QgsMapToolZoom(self.mCanvas, True), 'add': QgsGeorefToolAddPoint(self.mCanvas, self),
                       'delete': QgsGeorefToolDeletePoint(self.mCanvas, self), 'move': QgsGeorefToolMovePoint(self.mCanvas, self)}
        self.mMoveDestinationTool = QgsGeorefToolMovePoint(app.mMapCanvas, self, True)
        self.createActions()
        self.mCanvas.setMapTool(self.mTools['pan'])
        self.mCanvas.xyCoordinates.connect(lambda p: self.statusBar().showMessage(f'X: {p.x():.12g}   Y: {p.y():.12g}'))
        self.mCanvas.zoomLastStatusChanged.connect(lambda enabled: self.setZoomStatus('mCanZoomLast', enabled))
        self.mCanvas.zoomNextStatusChanged.connect(lambda enabled: self.setZoomStatus('mCanZoomNext', enabled))
        self.mCanvas.extentsChanged.connect(self.extentsChangedGeorefCanvas)
        app.mMapCanvas.extentsChanged.connect(self.extentsChangedQGisCanvas)
        app.mMapCanvas.destinationCrsChanged.connect(self.updateMarkers)
        self.mCanvas.mapToolSet.connect(self.mapToolChanged)
        if saved.value('Plugin-GeoReferencer/geometry'): self.restoreGeometry(saved.value('Plugin-GeoReferencer/geometry'))
        if saved.value('Plugin-GeoReferencer/state'): self.restoreState(saved.value('Plugin-GeoReferencer/state'))
        self.updateActions()

    def createActions(self):
        slots = dict(mActionOpenRaster=lambda: self.openLayer(True), mActionOpenVector=lambda: self.openLayer(False),
                     mActionStartGeoref=self.georeference, mActionGDALScript=self.generateGDALScript,
                     mActionLoadGCPpoints=self.loadGCPsDialog, mActionSaveGCPpoints=self.saveGCPsDialog,
                     mActionTransformSettings=self.showTransformSettingsDialog, mActionReset=self.reset,
                     mActionPan=lambda: self.setTool('pan'), mActionZoomIn=lambda: self.setTool('zoomIn'),
                     mActionZoomOut=lambda: self.setTool('zoomOut'), mActionAddPoint=lambda: self.setTool('add'),
                     mActionDeletePoint=lambda: self.setTool('delete'), mActionMoveGCPPoint=lambda: self.setTool('move'),
                     mActionZoomToLayer=self.zoomToLayerTool, mActionZoomLast=self.mCanvas.zoomToPreviousExtent,
                     mActionZoomNext=self.mCanvas.zoomToNextExtent, mActionSourceProperties=self.showLayerPropertiesDialog,
                     mActionLocalHistogramStretch=lambda: self.histogramStretch(True),
                     mActionFullHistogramStretch=lambda: self.histogramStretch(False),
                     mActionGeorefConfig=self.showGeorefConfigDialog, mActionQuit=self.close,
                     mActionLinkGeorefToQgis=self.extentsChangedQGisCanvas,
                     mActionLinkQGisToGeoref=self.extentsChangedGeorefCanvas)
        self.mActionGroup = QActionGroup(self)
        self.mActionNames = list(slots)
        self.mToolActions = dict(mActionPan='pan', mActionZoomIn='zoomIn', mActionZoomOut='zoomOut',
                                mActionAddPoint='add', mActionDeletePoint='delete', mActionMoveGCPPoint='move')
        catalog = json.loads((ROOT / 'docs/upstream-toolbar-actions.json').read_text(encoding='utf-8'))
        rows = {a['objectName']: a for a in catalog['actions'] if a['sourceKey'].startswith('georeferencer:')}
        for name, callback in slots.items():
            action = getattr(self, name)
            action.triggered.connect(lambda checked=False, call=callback: self.invoke(call))
            if name in self.mToolActions:
                action.setCheckable(True)
                self.mActionGroup.addAction(action)
                self.mTools[self.mToolActions[name]].setAction(action)
            row = rows.get(name, {})
            if row.get('icon'): action.setIcon(QgsApplication.getThemeIcon(row['icon']))
            toolbar = next((bar for bar in (self.toolBarFile, self.toolBarEdit, self.toolBarView, self.toolBarHistogramStretch)
                            if action in bar.actions()), None)
            note = '原版地理配准窗口 Action；连接源图层、控制点、原生变换器及画布状态。'
            if name == 'mActionStartGeoref': note = '栅格多项式/TPS/线性/Helmert、线性世界文件和原生矢量变换；取消、输出保护及加载。栅格投影变换和 PDF 输出未完成。'
            if name == 'mActionTransformSettings': note = '原版变换设置 UI；方法、CRS、重采样、压缩、分辨率、透明零值、世界文件、保存控制点及加载。PDF 报告/地图和栅格投影变换未完成。'
            if name == 'mActionGDALScript': note = '预览、复制及保存独立 GDAL Python 脚本；栅格与 OGR 矢量、多项式/TPS、图层与子集过滤。'
            if name == 'mActionGeorefConfig': note = '原版配置 UI；控制点 ID/坐标提示与残差单位保存。停靠及 PDF 页面设置未移植。'
            self.mApp.mDynamicActions['georeferencer:' + name] = dict(action=action, handler=getattr(callback, '__name__', name),
                toolbar=row.get('toolbar', ''), toolbarWidget=toolbar, inInterface=True, note=note)

    def invoke(self, callback):
        if self.mBusy: return
        try: return callback()
        except Exception as error:
            self.mMessageBar.pushCritical('地理配准', str(error))
            return False

    def setZoomStatus(self, name, enabled):
        setattr(self, name, enabled)
        self.updateActions()

    def updateActions(self):
        if self.mShutdown: return
        active = self.mLayer is not None and not self.mBusy
        for name in self.mActionNames: getattr(self, name).setEnabled(active)
        for name in ('mActionOpenRaster', 'mActionOpenVector', 'mActionQuit', 'mActionGeorefConfig'):
            getattr(self, name).setEnabled(not self.mBusy)
        self.mActionStartGeoref.setEnabled(active and self.mTransform.mTransformer is not None)
        self.mActionGDALScript.setEnabled(active and self.mTransform.mTransformer is not None)
        self.mActionSaveGCPpoints.setEnabled(active and bool(self.mPoints))
        for action in (self.mActionDeletePoint, self.mActionMoveGCPPoint): action.setEnabled(active and bool(self.mPoints))
        for action in (self.mActionLocalHistogramStretch, self.mActionFullHistogramStretch): action.setEnabled(active and isinstance(self.mLayer, QgsRasterLayer))
        self.mActionZoomLast.setEnabled(active and self.mCanZoomLast)
        self.mActionZoomNext.setEnabled(active and self.mCanZoomNext)
        for action in (self.mActionLinkGeorefToQgis, self.mActionLinkQGisToGeoref): action.setEnabled(active and self.mTransform.mTransformer is not None)

    def setTool(self, name):
        self.restoreMainTool()
        self.mCanvas.setMapTool(self.mTools[name])
        if name == 'move':
            self.mPreviousMainTool = self.mApp.mMapCanvas.mapTool()
            self.mApp.mMapCanvas.setMapTool(self.mMoveDestinationTool)

    def mapToolChanged(self, tool, previous):
        if tool is not self.mTools['move']: self.restoreMainTool()

    def restoreMainTool(self):
        if self.mApp.mMapCanvas.mapTool() is self.mMoveDestinationTool:
            self.mApp.mMapCanvas.setMapTool(self.mPreviousMainTool or self.mApp.mMapTools['pan'])
        self.mPreviousMainTool = None

    def openLayer(self, raster=True, fileName=None, ask=True):
        if self.mBusy: return False
        uri, provider = fileName, 'gdal' if raster else 'ogr'
        if fileName is None:
            if raster:
                fileName, _ = QFileDialog.getOpenFileName(self, '打开栅格', '', QgsProviderRegistry.instance().fileRasterFilters())
                uri = fileName
            else:
                dialog = QgsDataSourceSelectDialog(self.mApp.mBrowserModel, True, Qgis.LayerType.Vector, self)
                dialog.setWindowTitle('打开矢量')
                if not dialog.exec_():
                    dialog.deleteLater()
                    return False
                selected = dialog.uri()
                uri, provider = selected.uri, selected.providerKey
                fileName = QgsProviderRegistry.instance().decodeUri(provider, uri).get('path') or uri
                dialog.deleteLater()
        if not fileName: return False
        context = self.mApp.mProject.transformContext()
        options = QgsRasterLayer.LayerOptions(True, context) if raster else QgsVectorLayer.LayerOptions(context)
        options.skipCrsValidation = True
        layer = (QgsRasterLayer(uri, Path(fileName).stem, provider, options) if raster
                 else QgsVectorLayer(uri, Path(fileName).stem, provider, options))
        if not layer.isValid():
            sip.delete(layer)
            raise ValueError('无法打开源图层')
        coords = None
        try:
            if raster:
                coords = QgsRasterChangeCoords()
                coords.loadRaster(fileName)
            if ask and not self.canClose():
                sip.delete(layer)
                return False
        except Exception:
            if not sip.isdeleted(layer): sip.delete(layer)
            raise
        self.clearSource()
        self.mLayer, self.mSourceFile, self.mRasterChangeCoords = layer, str(fileName), coords
        localSource = Path(fileName).is_file()
        self.mSettings['output'] = (str(Path(fileName).with_name(Path(fileName).stem + '_modified' + ('.tif' if raster else '.gpkg')))
                                    if localSource else '')
        self.mSettings['worldfile'] = False
        if raster and self.mSettings['method'] == QgsGeorefTransform.Method.Projective:
            self.mSettings['method'] = QgsGeorefTransform.Method.PolynomialOrder1
        self.mCanvas.setDestinationCrs(layer.crs())
        self.mCanvas.setLayers([layer])
        self.mCanvas.setRenderFlag(True)
        self.zoomToLayerTool()
        self.mCanvas.clearExtentHistory()
        self.setWindowTitle('地理配准 — ' + Path(fileName).name)
        self.pointsChanged(False)
        self.mGCPFile = self.mSourceFile + '.points' if localSource else ''
        if self.mGCPFile and Path(self.mGCPFile).is_file(): self.loadGCPs(self.mGCPFile)
        return True

    def clearSource(self):
        if self.mCoordinateDialog: self.mCoordinateDialog.reject()
        self.restoreMainTool()
        self.mCanvas.setMapTool(self.mTools['pan'])
        self.mCanvas.setRenderFlag(False)
        self.mCanvas.waitWhileRendering()
        self.mCanvas.setLayers([])
        if self.mLayer: sip.delete(self.mLayer)
        self.mLayer = None
        self.mPoints.clear()
        self.mResiduals.clear()
        self.mSourceFile = self.mGCPFile = ''
        self.mDirty = False
        self.mTransform.mTransformer = None
        self.updateMarkers()

    def reset(self):
        if self.canClose():
            self.clearSource()
            self.mGCPListWidget.mModel.refresh()
            self.updateActions()

    def destinationPoint(self, point):
        crs = point.destinationPointCrs()
        if crs.isValid() and crs != self.mSettings['crs']:
            return QgsCoordinateTransform(crs, self.mSettings['crs'], self.mApp.mProject).transform(point.destinationPoint())
        return point.destinationPoint()

    def addPoint(self, source, destination, crs=None, enabled=True):
        if self.mBusy or self.mLayer is None: return False
        self.mPoints.append(QgsGcpPoint(source, destination, crs or self.mSettings['crs'], enabled))
        self.pointsChanged()
        return True

    def requestPoint(self, source):
        if self.mLayer is None or self.mCoordinateDialog: return
        from .qgsmapcoordsdialog import QgsMapCoordsDialog
        dialog = QgsMapCoordsDialog(self)
        self.mCoordinateDialog = dialog
        dialog.accepted.connect(lambda: self.addPoint(source, dialog.mPoint, dialog.mProjectionSelector.crs()))
        def finished(*unused):
            self.mCoordinateDialog = None
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.show()

    def deletePoints(self, rows):
        if self.mBusy: return
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.mPoints): del self.mPoints[row]
        self.pointsChanged()

    def movePoint(self, index, point, destination=False):
        if destination:
            target = QgsCoordinateTransform(self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mSettings['crs'], self.mApp.mProject).transform(point)
            self.mPoints[index].setDestinationPoint(target)
            self.mPoints[index].setDestinationPointCrs(self.mSettings['crs'])
        else: self.mPoints[index].setSourcePoint(point)
        self.pointsChanged()

    def nearestPoint(self, point, destination=False):
        canvas = self.mApp.mMapCanvas if destination else self.mCanvas
        distances = []
        for index, gcp in enumerate(self.mPoints):
            position = self.pointForCanvas(gcp, destination)
            distances.append((position.sqrDist(point), index))
        if not distances: return None
        distance, index = min(distances)
        return index if distance <= (canvas.mapUnitsPerPixel()*12)**2 else None

    def pointForCanvas(self, point, destination):
        if not destination: return point.sourcePoint()
        return QgsCoordinateTransform(self.mSettings['crs'], self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mApp.mProject).transform(self.destinationPoint(point))

    def previewMove(self, index, point, destination):
        for row, target, marker, canvas in self.mMarkers:
            if row == index and target == destination:
                marker.mPoint = point
                marker.updatePosition()

    def clearMarkers(self):
        for row, destination, item, canvas in self.mMarkers:
            canvas.scene().removeItem(item)
            sip.delete(item)
        self.mMarkers = []

    def updateMarkers(self):
        self.clearMarkers()
        if self.mShutdown or not self.isVisible(): return
        for row, gcp in enumerate(self.mPoints):
            for destination, canvas in ((False, self.mCanvas), (True, self.mApp.mMapCanvas)):
                try:
                    point = self.pointForCanvas(gcp, destination)
                    text = str(row) if self.mShowIds else ''
                    if self.mShowCoords: text += f' ({point.x():.8g}, {point.y():.8g})'
                    self.mMarkers.append((row, destination, QgsGCPCanvasItem(canvas, point, text, gcp.isEnabled()), canvas))
                except Exception: continue

    def pointsChanged(self, dirty=True):
        self.mDirty = self.mDirty or dirty
        valid = self.mTransform.updateParametersFromGcps(self.mPoints, self.mSettings['method'], self.mSettings['crs'],
                                                       self.mApp.mProject.transformContext(), self.mRasterChangeCoords)
        self.mResiduals = []
        for point in self.mPoints:
            try:
                if not valid: raise ValueError()
                source = self.mRasterChangeCoords.toColumnLine(point.sourcePoint()) if self.mRasterChangeCoords else point.sourcePoint()
                target = self.destinationPoint(point)
                if self.mResidualPixels and self.mRasterChangeCoords:
                    fitted = self.mTransform.transform(target, True)
                    residual = (fitted.x()-source.x(), -(fitted.y()-source.y()))
                else:
                    fitted = self.mTransform.transform(source)
                    residual = (fitted.x()-target.x(), fitted.y()-target.y())
            except Exception: residual = (math.nan, math.nan)
            self.mResiduals.append(residual)
        self.mGCPListWidget.mModel.refresh()
        self.updateMarkers()
        self.updateActions()
        residuals = [x*x+y*y for point, (x,y) in zip(self.mPoints,self.mResiduals) if point.isEnabled() and math.isfinite(x+y)]
        self.statusBar().showMessage(f'控制点：{len(self.mPoints)}；RMS：{math.sqrt(sum(residuals)/len(residuals)):.6g}' if residuals else self.mTransform.mError)

    def loadGCPs(self, path):
        points, crs = QgsGCPList.loadGcps(path, self.mSettings['crs'])
        self.mPoints, self.mSettings['crs'], self.mGCPFile = points, crs, str(path)
        self.mDirty = False
        self.pointsChanged(False)
        return True

    def loadGCPsDialog(self):
        path, _ = QFileDialog.getOpenFileName(self, '加载控制点', self.mGCPFile, 'GCP (*.points);;所有文件 (*)')
        if path and self.canClose(): return self.loadGCPs(path)

    def saveGCPs(self, path):
        if Path(path).resolve() == Path(self.mSourceFile).resolve(): raise ValueError('控制点文件不能覆盖源数据')
        self.mPoints.saveGcps(path, self.mSettings['crs'], self.mApp.mProject.transformContext(), self.mResiduals)
        self.mGCPFile, self.mDirty = str(path), False
        return True

    def saveGCPsDialog(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存控制点', self.mGCPFile or self.mSourceFile+'.points', 'GCP (*.points)')
        return self.saveGCPs(path) if path else False

    def showTransformSettingsDialog(self):
        from .qgstransformsettingsdialog import QgsTransformSettingsDialog
        dialog = QgsTransformSettingsDialog(self.mSettings, isinstance(self.mLayer, QgsRasterLayer), self)
        if dialog.exec_():
            self.mSettings = dialog.mSettings
            self.pointsChanged(False)
        dialog.deleteLater()

    def georeference(self):
        if self.mBusy or not self.mLayer: return False
        self.pointsChanged(False)
        if not self.mTransform.mTransformer: raise ValueError(self.mTransform.mError)
        if not self.mSettings['output'] and not self.mSettings['worldfile']: self.showTransformSettingsDialog()
        if not self.mSettings['output'] and not self.mSettings['worldfile']: return False
        output = Path(self.mSettings['output'])
        raster = isinstance(self.mLayer, QgsRasterLayer)
        if not self.mSettings['worldfile']:
            if output.suffix.lower() not in (('.tif', '.tiff') if raster else ('.gpkg',)): raise ValueError('栅格请输出 GeoTIFF，矢量请输出 GeoPackage')
            if output.resolve() == Path(self.mSourceFile).resolve() or output.exists(): raise ValueError('请使用新的输出文件名，不能覆盖源数据或已有文件')
        progress = QProgressDialog('正在地理配准…', '取消', 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        self.mBusy = True
        self.updateActions()
        def advance(value):
            progress.setValue(min(99, int(value)))
            QApplication.processEvents()
            return not progress.wasCanceled()
        try:
            context = self.mApp.mProject.transformContext()
            if self.mSettings['worldfile']:
                if not raster or self.mSettings['method'] != QgsGeorefTransform.Method.Linear: raise ValueError('世界文件仅用于线性栅格变换')
                if self.mRasterChangeCoords.mHasExistingGeoreference:
                    raise ValueError('源栅格已有地理参考，请输出新栅格，避免内部参考覆盖世界文件')
                output = Path(self.mSourceFile).with_suffix('.wld')
                gt = self.mTransform.geoTransform()
                # Exclusive create protects an existing reference sidecar.
                with output.open('x', encoding='ascii') as stream:
                    stream.write('\n'.join(format(v, '.17g') for v in (gt[1], gt[4], gt[2], gt[5], gt[0]+(gt[1]+gt[2])/2, gt[3]+(gt[4]+gt[5])/2))+'\n')
                result = str(output)
            elif raster:
                result = QgsImageWarper.warpRaster(self.mSourceFile, output, self.mPoints, self.mSettings, context,
                                                  self.mRasterChangeCoords, self.mTransform, advance)
            else: result = QgsImageWarper.warpVector(self.mLayer, output, self.mPoints, self.mSettings, context, advance)
            if self.mSettings['saveGcp']: self.saveGCPs(self.mGCPFile or self.mSourceFile+'.points')
            if self.mSettings['load']:
                if raster:
                    layer = QgsRasterLayer(self.mSourceFile if self.mSettings['worldfile'] else result, Path(result).stem)
                    layer.setCrs(self.mSettings['crs'])
                else: layer = QgsVectorLayer(result+'|layername=georeferenced', Path(result).stem, 'ogr')
                if layer.isValid(): self.mApp.addMapLayer(layer)
                else:
                    sip.delete(layer)
                    self.mMessageBar.pushWarning('结果已写入', '无法自动加载，请手动打开输出文件')
            self.mMessageBar.pushSuccess('配准完成', result)
            return result
        except InterruptedError:
            self.mMessageBar.pushInfo('地理配准', '已取消，未创建目标文件')
            return False
        finally:
            progress.close()
            progress.deleteLater()
            self.mBusy = False
            self.updateActions()

    def generateGDALScript(self, path=None):
        self.pointsChanged(False)
        if not self.mTransform.mTransformer: raise ValueError(self.mTransform.mError)
        if self.mSettings['worldfile']: raise ValueError('世界文件模式请直接执行配准；生成脚本用于输出新栅格')
        if not self.mSettings['output']:
            self.showTransformSettingsDialog()
            if not self.mSettings['output']: return False
        if isinstance(self.mLayer, QgsRasterLayer):
            script = QgsImageWarper.generateGDALScript(self.mSourceFile, self.mSettings['output'], self.mPoints, self.mSettings,
                                                   self.mApp.mProject.transformContext(), self.mRasterChangeCoords, self.mTransform)
        else:
            script = QgsImageWarper.generateGDALogr2ogrCommand(self.mLayer, self.mSettings['output'], self.mPoints,
                                                              self.mSettings, self.mApp.mProject.transformContext())
        if path is None: return self.showGDALScript(script)
        return self.saveGDALScript(path, script)

    def saveGDALScript(self, path, script):
        if Path(path).resolve() in (Path(self.mSourceFile).resolve(), Path(self.mSettings['output']).resolve()):
            raise ValueError('脚本不能覆盖源数据或配准输出文件')
        Path(path).write_text(script, encoding='utf-8')
        return str(path)

    def showGDALScript(self, script):
        dialog = QDialog(self)
        dialog.setObjectName('dlgShowGdalScript')
        dialog.setWindowTitle('GDAL Python 脚本')
        dialog.resize(780, 480)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(dialog)
        editor.setObjectName('pteScript')
        editor.setReadOnly(True)
        editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        editor.setPlainText(script)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        copy = buttons.addButton('复制到剪贴板', QDialogButtonBox.ActionRole)
        copy.setObjectName('pbnCopyInClipBoard')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        save = buttons.addButton('保存脚本…', QDialogButtonBox.ActionRole)
        def saveScript():
            path, _ = QFileDialog.getSaveFileName(dialog, '保存 GDAL Python 脚本', '', 'Python (*.py)')
            if path: self.invoke(lambda: self.saveGDALScript(path, editor.toPlainText()))
        save.clicked.connect(saveScript)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()
        dialog.deleteLater()
        return True

    def zoomToLayerTool(self):
        if self.mLayer:
            self.mCanvas.setExtent(self.mLayer.extent())
            self.mCanvas.refresh()

    def centerPoint(self, index):
        for destination, canvas in ((False, self.mCanvas), (True, self.mApp.mMapCanvas)):
            canvas.setCenter(self.pointForCanvas(self.mPoints[index], destination))
            canvas.refresh()

    def extentsChangedGeorefCanvas(self):
        if self.mActionLinkQGisToGeoref.isChecked(): self.linkExtent(False)

    def extentsChangedQGisCanvas(self):
        if self.mActionLinkGeorefToQgis.isChecked(): self.linkExtent(True)

    def linkExtent(self, inverse):
        if self.mLinking or not self.mTransform.mTransformer or self.mBusy or self.mShutdown: return
        self.mLinking = True
        try:
            source = self.mApp.mMapCanvas if inverse else self.mCanvas
            target = self.mCanvas if inverse else self.mApp.mMapCanvas
            extent, points = source.extent(), []
            crsTransform = QgsCoordinateTransform(self.mSettings['crs'], self.mApp.mMapCanvas.mapSettings().destinationCrs(), self.mApp.mProject)
            for i in range(9):
                t = i/8
                for point in (QgsPointXY(extent.xMinimum()+t*extent.width(), extent.yMinimum()), QgsPointXY(extent.xMinimum()+t*extent.width(), extent.yMaximum()),
                              QgsPointXY(extent.xMinimum(), extent.yMinimum()+t*extent.height()), QgsPointXY(extent.xMaximum(), extent.yMinimum()+t*extent.height())):
                    if inverse:
                        point = crsTransform.transform(point, Qgis.TransformDirection.Reverse)
                        point = self.mTransform.transform(point, True)
                        if self.mRasterChangeCoords: point = self.mRasterChangeCoords.toXY(point)
                    else:
                        if self.mRasterChangeCoords: point = self.mRasterChangeCoords.toColumnLine(point)
                        point = crsTransform.transform(self.mTransform.transform(point))
                    points.append(point)
            rectangle = QgsRectangle(min(p.x() for p in points), min(p.y() for p in points), max(p.x() for p in points), max(p.y() for p in points))
            if not rectangle.isEmpty(): target.setExtent(rectangle); target.refresh()
        except Exception as error: self.statusBar().showMessage(str(error), 4000)
        finally: self.mLinking = False

    def histogramStretch(self, local):
        if not isinstance(self.mLayer, QgsRasterLayer): return
        self.mLayer.setContrastEnhancement(QgsContrastEnhancement.StretchToMinimumMaximum, QgsRasterMinMaxOrigin.MinMax,
                                           self.mCanvas.extent() if local else self.mLayer.extent())
        self.mLayer.triggerRepaint()

    def showLayerPropertiesDialog(self):
        if isinstance(self.mLayer, QgsRasterLayer): dialog = QgsRasterLayerProperties(self.mLayer, self.mCanvas, self)
        else: dialog = QgsVectorLayerProperties(self.mCanvas, self.mMessageBar, self.mLayer, self)
        dialog.exec_()
        dialog.deleteLater()
        self.mCanvas.refresh()

    def showGeorefConfigDialog(self):
        dialog = QDialog(self)
        uic.loadUi(str(ROOT / 'src/ui/georeferencer/qgsgeorefconfigdialogbase.ui'), dialog)
        dialog.mShowIDsCheckBox.setChecked(self.mShowIds)
        dialog.mShowCoordsCheckBox.setChecked(self.mShowCoords)
        dialog.mPixelsButton.setChecked(self.mResidualPixels)
        dialog.mMapUnitsButton.setChecked(not self.mResidualPixels)
        for widget in (dialog.mShowDockedCheckBox, dialog.groupBox, dialog.mPdfReportGroupBox):
            widget.setEnabled(False)
            widget.setToolTip('此分支尚未移植')
        if dialog.exec_():
            self.mShowIds, self.mShowCoords = dialog.mShowIDsCheckBox.isChecked(), dialog.mShowCoordsCheckBox.isChecked()
            self.mResidualPixels = dialog.mPixelsButton.isChecked()
            for key, value in [('ShowId',self.mShowIds), ('ShowCoords',self.mShowCoords), ('ResidualPixels',self.mResidualPixels)]:
                QgsSettings().setValue('Plugin-GeoReferencer/'+key, value)
            self.pointsChanged(False)
        dialog.deleteLater()

    def canClose(self):
        if self.mBusy: return False
        if not self.mDirty: return True
        choice = QMessageBox.question(self, '控制点尚未保存', '保存当前控制点？', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if choice == QMessageBox.Cancel: return False
        if choice == QMessageBox.Save:
            try: return bool(self.saveGCPsDialog())
            except Exception as error:
                self.mMessageBar.pushCritical('保存失败', str(error)); return False
        self.mDirty = False
        return True

    def showEvent(self, event):
        super().showEvent(event)
        self.updateMarkers()

    def hideEvent(self, event):
        self.restoreMainTool()
        self.clearMarkers()
        super().hideEvent(event)

    def closeEvent(self, event):
        if not self.mShutdown and not self.canClose(): event.ignore(); return
        self.restoreMainTool()
        QgsSettings().setValue('Plugin-GeoReferencer/geometry', self.saveGeometry())
        QgsSettings().setValue('Plugin-GeoReferencer/state', self.saveState())
        event.accept()

    def shutdown(self):
        if self.mShutdown: return
        self.mShutdown = True
        self.mApp.mMapCanvas.extentsChanged.disconnect(self.extentsChangedQGisCanvas)
        self.mApp.mMapCanvas.destinationCrsChanged.disconnect(self.updateMarkers)
        self.clearSource()
