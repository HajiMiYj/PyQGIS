"""Port of src/app/dwg/qgsdwgimportdialog.cpp using its original Designer form."""
from pathlib import Path
from qgis.PyQt import uic, sip
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QTableWidgetItem, QProgressDialog, QApplication
from qgis.core import (
    Qgis, QgsProject, QgsSettings, QgsCoordinateReferenceSystem, QgsVectorLayer,
    QgsRectangle, QgsCoordinateTransform, QgsProperty, QgsSymbolLayer,
    QgsLineSymbol, QgsFillSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer,
    QgsNullSymbolRenderer, QgsTextFormat, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsSimpleLineSymbolLayer,
)
from qgis.gui import QgsFileWidget, QgsMapToolPan, QgsGui
from .qgsdwgimporter import QgsDwgImporter


class QgsDwgImportDialog(QDialog):
    BlockImportExpandGeometry = 1
    BlockImportAddInsertPoints = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/qgsdwgimportbase.ui'), self)
        self.setObjectName('QgsDwgImportDialog')
        QgsGui.enableAutoGeometryRestore(self)
        self.mProject = QgsProject.instance()
        self.mPreviewLayers = []
        self.mTables = []
        self.mLoadedDatabase = ''
        self.mBusy = False
        self.mUpdating = False
        self.mLastImport = None
        self.mDatabaseFileWidget.setStorageMode(QgsFileWidget.SaveFile)
        self.mDatabaseFileWidget.setConfirmOverwrite(False)
        self.mDatabaseFileWidget.setFilter('GeoPackage (*.gpkg)')
        self.mSourceDrawingFileWidget.setFilter('CAD (*.dwg *.dxf);;DXF (*.dxf);;DWG (*.dwg)')
        self.mBlockModeComboBox.addItem('展开块几何', self.BlockImportExpandGeometry)
        self.mBlockModeComboBox.addItem('展开块几何并添加插入点', 3)
        self.mBlockModeComboBox.addItem('仅添加块插入点', self.BlockImportAddInsertPoints)
        self.cbUseCurves.setChecked(False)
        self.cbUseCurves.setEnabled(False)
        self.cbUseCurves.setToolTip('当前 GDAL 读取后端不能保证保留原版 CAD 曲线，暂不开放此选项。')
        self.lblMessage.setWordWrap(True)
        self.lblMessage.setText('DXF/DWG 版本支持取决于已安装的 CAD 驱动；曲线、复杂块及特殊文字排版仍有差异。目标包须使用新文件名。')
        self.mPanTool = QgsMapToolPan(self.mMapCanvas)
        self.mMapCanvas.setMapTool(self.mPanTool)
        self.mMapCanvas.setProject(self.mProject)
        self.mMapCanvas.setCanvasColor(Qt.white)
        self.mCrsSelector.setShowAccuracyWarnings(True)
        self.mCrsSelector.setMessage('指定图纸坐标的参考系；导入时不改变原始坐标值。')
        settings = QgsSettings()
        crs = QgsCoordinateReferenceSystem()
        crs.createFromSrsId(settings.value('DwgImport/lastCrs', self.mProject.crs().srsid(), type=int))
        self.mCrsSelector.setCrs(crs if crs.isValid() else self.mProject.crs())
        self.mSourceDrawingFileWidget.setFilePath(settings.value('DwgImport/lastDrawingFile', ''))
        self.mDatabaseFileWidget.setFilePath(settings.value('DwgImport/lastDatabaseFile', ''))
        self.cbMergeLayers.setChecked(settings.value('DwgImport/lastMergeLayers', False, type=bool))
        self.mBlockModeComboBox.setCurrentIndex(max(0, self.mBlockModeComboBox.findData(settings.value('DwgImport/lastBlockImportFlags', 1, type=int))))
        self.mDatabaseFileWidget.fileChanged.connect(self.mDatabaseFileWidget_textChanged)
        self.mSourceDrawingFileWidget.fileChanged.connect(self.drawingFileWidgetFileChanged)
        self.mCrsSelector.crsChanged.connect(self.updateUI)
        self.pbImportDrawing.clicked.connect(self.pbImportDrawing_clicked)
        self.pbLoadDatabase.clicked.connect(self.pbLoadDatabase_clicked)
        self.pbSelectAll.clicked.connect(self.pbSelectAll_clicked)
        self.pbDeselectAll.clicked.connect(self.pbDeselectAll_clicked)
        self.leLayerGroup.textChanged.connect(self.updateUI)
        self.mLayers.itemChanged.connect(self.layersClicked)
        self.buttonBox.helpRequested.connect(self.showHelp)
        self.finished.connect(self.saveSettings)
        self.finished.connect(self.clearPreview)
        self.updateBlockMode()
        self.updateUI()

    def saveSettings(self):
        settings = QgsSettings()
        for key, value in (
            ('lastDrawingFile', self.mSourceDrawingFileWidget.filePath()),
            ('lastDatabaseFile', self.mDatabaseFileWidget.filePath()),
            ('lastCrs', self.mCrsSelector.crs().srsid()),
            ('lastMergeLayers', self.cbMergeLayers.isChecked()),
            ('lastBlockImportFlags', self.mBlockModeComboBox.currentData()),
        ): settings.setValue('DwgImport/' + key, value)

    def updateBlockMode(self):
        dxf = Path(self.mSourceDrawingFileWidget.filePath()).suffix.lower() == '.dxf'
        self.mBlockModeComboBox.setEnabled(dxf and not self.mBusy)
        if not dxf: self.mBlockModeComboBox.setCurrentIndex(0)

    def updateUI(self, *unused):
        source = Path(self.mSourceDrawingFileWidget.filePath())
        database = Path(self.mDatabaseFileWidget.filePath())
        self.pbImportDrawing.setEnabled(not self.mBusy and source.is_file() and database.suffix.lower() == '.gpkg'
                                       and database.parent.is_dir() and self.mCrsSelector.crs().isValid())
        self.pbLoadDatabase.setEnabled(not self.mBusy and database.is_file())
        loaded = self.mLoadedDatabase and str(database.resolve()) == self.mLoadedDatabase
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(bool(not self.mBusy and loaded and self.selectedLayers() and self.leLayerGroup.text().strip()))

    def drawingFileWidgetFileChanged(self, filename):
        self.updateBlockMode()
        if filename:
            self.mDatabaseFileWidget.setFilePath(str(Path(filename).with_suffix('.gpkg')))
            self.leLayerGroup.setText(Path(filename).stem)
        self.updateUI()

    def mDatabaseFileWidget_textChanged(self, *unused):
        self.clearPreview()
        self.mTables = []
        self.mLoadedDatabase = ''
        self.mLayers.setRowCount(0)
        self.updateUI()

    def selectedLayers(self):
        return [(self.mLayers.item(row, 0).text(), self.mLayers.item(row, 1).checkState() == Qt.Checked)
                for row in range(self.mLayers.rowCount()) if self.mLayers.item(row, 0).checkState() == Qt.Checked]

    def pbImportDrawing_clicked(self):
        if self.mBusy: return False
        self.mBusy = True
        self.groupBox.setEnabled(False)
        self.mGroupBox.setEnabled(False)
        self.buttonBox.setEnabled(False)
        self.updateUI()
        progress = QProgressDialog('正在读取 CAD 图纸…', '取消', 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        def advance(count):
            progress.setLabelText(f'正在导入图纸，已读取 {count} 个实体…')
            QApplication.processEvents()
            return not progress.wasCanceled()
        try:
            flags = self.mBlockModeComboBox.currentData()
            importer = QgsDwgImporter(self.mDatabaseFileWidget.filePath(), self.mCrsSelector.crs())
            counts = importer.importDrawing(self.mSourceDrawingFileWidget.filePath(),
                                            bool(flags & self.BlockImportExpandGeometry), False,
                                            bool(flags & self.BlockImportAddInsertPoints), advance)
            self.mLastImport = {'driver': importer.mDriver, 'counts': counts, 'warnings': importer.mWarnings}
            self.bar.pushSuccess('CAD', f'已导入 {sum(counts.values())} 个几何。')
            for warning in importer.mWarnings: self.bar.pushWarning('CAD', warning)
            return self.pbLoadDatabase_clicked()
        except InterruptedError:
            self.bar.pushInfo('CAD', '已取消，未创建目标包。')
        except Exception as error:
            self.bar.pushCritical('导入失败', str(error))
        finally:
            progress.close()
            progress.deleteLater()
            self.mBusy = False
            self.groupBox.setEnabled(True)
            self.mGroupBox.setEnabled(True)
            self.buttonBox.setEnabled(True)
            self.updateBlockMode()
            self.updateUI()
        return False

    def pbLoadDatabase_clicked(self):
        from osgeo import gdal
        self.clearPreview()
        self.mLoadedDatabase, self.mTables = '', []
        self.mUpdating = True
        self.mLayers.setSortingEnabled(False)
        self.mLayers.setRowCount(0)
        database = None
        try:
            path = Path(self.mDatabaseFileWidget.filePath()).resolve()
            database = gdal.OpenEx(str(path), gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=['GPKG'])
            if database is None: raise ValueError('无法打开 GeoPackage。')
            metadata = database.GetLayerByName('layers')
            if metadata is None or metadata.GetLayerDefn().GetFieldIndex('name') < 0:
                raise ValueError('所选包不含 CAD 图层目录。请先通过 CAD 导入创建包。')
            for table in QgsDwgImporter.TABLES:
                layer = database.GetLayerByName(table)
                if layer is not None and all(layer.GetLayerDefn().GetFieldIndex(field) >= 0 for field in ('layer', 'space', 'block')):
                    self.mTables.append(table)
            if not self.mTables: raise ValueError('所选包不含可加载的 CAD 几何表。')
            names = {}
            for feature in metadata:
                attrs = feature.items()
                if attrs.get('name') is not None:
                    names[str(attrs['name'])] = (attrs.get('ocolor') is None or attrs['ocolor'] >= 0) and not (attrs.get('flags', 0) or 0) & 1
            for row, (name, visible) in enumerate(sorted(names.items())):
                self.mLayers.insertRow(row)
                for col, text, checked in ((0, name, True), (1, '', visible)):
                    item = QTableWidgetItem(text)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self.mLayers.setItem(row, col, item)
            self.mLayers.resizeColumnToContents(0)
            self.mLoadedDatabase = str(path)
            if not self.leLayerGroup.text().strip(): self.leLayerGroup.setText(path.stem)
            return True
        except Exception as error:
            self.mTables = []
            self.bar.pushCritical('加载失败', str(error))
            return False
        finally:
            if database is not None: database.Close()
            database = None
            self.mLayers.setSortingEnabled(True)
            self.mUpdating = False
            self.updateUI()
            self.updatePreview()

    def createLayer(self, layerFilter, table):
        # All geometry tables share one package while preview/project providers
        # coexist. Keep their SQLite journal mode consistent, including subset
        # readers (the 3.34 provider otherwise opens some of them with NOLOCK).
        layer = QgsVectorLayer(self.mLoadedDatabase + '|layername=' + table + '|option:QGIS_FORCE_WAL=ON', table, 'ogr')
        if not layer.isValid():
            sip.delete(layer)
            return None
        subset = (layerFilter + ' AND ' if layerFilter else '') + '"space"=0 AND "block"=-1'
        if not layer.setSubsetString(subset):
            sip.delete(layer)
            raise ValueError('无法设置 CAD 图层过滤条件。')
        if layer.featureCount() == 0:
            sip.delete(layer)
            return None
        if table == 'texts':
            layer.setRenderer(QgsNullSymbolRenderer())
            if layer.fields().indexFromName('text') >= 0:
                settings = QgsPalLayerSettings()
                settings.fieldName = 'text'
                settings.wrapChar = '\\P'
                textFormat = QgsTextFormat()
                textFormat.setSizeUnit(Qgis.RenderUnit.MapUnits)
                settings.setFormat(textFormat)
                settings.placement = QgsPalLayerSettings.OverPoint
                props = settings.dataDefinedProperties()
                for prop, field in ((QgsPalLayerSettings.Size, 'height'), (QgsPalLayerSettings.Color, 'color'),
                                    (QgsPalLayerSettings.FontSizeUnit, 'height_unit'), (QgsPalLayerSettings.Family, 'font'),
                                    (QgsPalLayerSettings.Bold, 'bold'), (QgsPalLayerSettings.Italic, 'italic'),
                                    (QgsPalLayerSettings.Underline, 'underline'), (QgsPalLayerSettings.Strikeout, 'strikeout'),
                                    (QgsPalLayerSettings.Hali, 'hali'), (QgsPalLayerSettings.Vali, 'vali')):
                    if layer.fields().indexFromName(field) >= 0: props.setProperty(prop, QgsProperty.fromField(field))
                # Original libdxfrw packages contain alignment enums rather
                # than the normalized OGR anchor strings written by this port.
                if all(layer.fields().indexFromName(name) >= 0 for name in ('etype', 'textgen', 'alignh', 'alignv')):
                    props.setProperty(QgsPalLayerSettings.Hali, QgsProperty.fromExpression(
                        "CASE WHEN etype=19 THEN CASE WHEN textgen%3=2 THEN 'Center' WHEN textgen%3=0 THEN 'Right' ELSE 'Left' END "
                        "ELSE CASE WHEN alignh=1 THEN 'Center' WHEN alignh=2 THEN 'Right' ELSE 'Left' END END"))
                    props.setProperty(QgsPalLayerSettings.Vali, QgsProperty.fromExpression(
                        "CASE WHEN etype=19 THEN CASE WHEN textgen<4 THEN 'Top' WHEN textgen<7 THEN 'Half' ELSE 'Bottom' END "
                        "ELSE CASE WHEN alignv=1 THEN 'Bottom' WHEN alignv=2 THEN 'Half' WHEN alignv=3 THEN 'Top' ELSE 'Base' END END"))
                if layer.fields().indexFromName('interlin') >= 0:
                    props.setProperty(QgsPalLayerSettings.MultiLineHeight, QgsProperty.fromExpression('CASE WHEN interlin<0 THEN 1 ELSE interlin*1.5 END'))
                props.setProperty(QgsPalLayerSettings.PositionX, QgsProperty.fromExpression('$x'))
                props.setProperty(QgsPalLayerSettings.PositionY, QgsProperty.fromExpression('$y'))
                props.setProperty(QgsPalLayerSettings.LabelRotation, QgsProperty.fromExpression('360-coalesce("angle",0)'))
                props.setProperty(QgsPalLayerSettings.AlwaysShow, QgsProperty.fromValue(True))
                layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
                layer.setLabelsEnabled(True)
        else:
            if table == 'hatches':
                symbol = QgsFillSymbol.createSimple({'outline_style': 'no'})
                colorProperty = QgsSymbolLayer.PropertyFillColor
            elif table in ('lines', 'polylines'):
                symbol = self.lineSymbol(layer, table)
                colorProperty = QgsSymbolLayer.PropertyStrokeColor
            else:
                symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'size': '1', 'outline_style': 'no'})
                colorProperty = QgsSymbolLayer.PropertyFillColor
            if layer.fields().indexFromName('color') >= 0:
                symbol.symbolLayer(0).setDataDefinedProperty(colorProperty, QgsProperty.fromField('color'))
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        return layer

    @staticmethod
    def lineSymbol(layer, table):
        fields = {field.name() for field in layer.fields()}
        symbol = QgsLineSymbol()
        symbol.deleteSymbolLayer(0)
        def addLine(unit, condition='', dashUnit=None):
            line = QgsSimpleLineSymbolLayer()
            line.setWidthUnit(unit)
            line.setPenJoinStyle(Qt.MiterJoin)
            line.setPenCapStyle(Qt.FlatCap)
            if 'color' in fields: line.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeColor, QgsProperty.fromField('color'))
            if 'linewidth' in fields: line.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth, QgsProperty.fromField('linewidth'))
            if condition: line.setDataDefinedProperty(QgsSymbolLayer.PropertyLayerEnabled, QgsProperty.fromExpression(condition))
            for prop, field in ((QgsSymbolLayer.PropertyCapStyle, 'capstyle'), (QgsSymbolLayer.PropertyJoinStyle, 'joinstyle')):
                if field in fields: line.setDataDefinedProperty(prop, QgsProperty.fromField(field))
            if dashUnit is not None:
                line.setUseCustomDashPattern(True)
                line.setCustomDashPatternUnit(dashUnit)
                line.setDataDefinedProperty(QgsSymbolLayer.PropertyCustomDash, QgsProperty.fromField('dash_pattern'))
            symbol.appendSymbolLayer(line)
            return line
        if table == 'polylines' and 'width' in fields:
            # Port the two mutually exclusive strokes from the original dialog:
            # polyline geometric width in map units, otherwise paper lineweight.
            line = addLine(Qgis.RenderUnit.MapUnits, 'coalesce("width",0)>0')
            line.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth, QgsProperty.fromField('width'))
            addLine(Qgis.RenderUnit.Millimeters, 'coalesce("width",0)<=0')
        elif {'linewidth_unit', 'dash_pattern', 'dash_unit'} <= fields:
            for name, unit in (('MM', Qgis.RenderUnit.Millimeters), ('MapUnit', Qgis.RenderUnit.MapUnits)):
                widthFilter = f'coalesce("linewidth_unit",\'MM\')=\'{name}\''
                addLine(unit, widthFilter + " AND coalesce(\"dash_pattern\",'')=''")
                for dashName, dashUnit in (('MM', Qgis.RenderUnit.Millimeters), ('MapUnit', Qgis.RenderUnit.MapUnits)):
                    addLine(unit, widthFilter + f' AND coalesce("dash_pattern",\'\')<>\'\' AND "dash_unit"=\'{dashName}\'', dashUnit)
        else:
            addLine(Qgis.RenderUnit.Millimeters)
        return symbol

    def createLayers(self, layerNames):
        quoted = ["'" + name.replace("'", "''") + "'" for name in layerNames]
        layerFilter = '"layer" IN (' + ','.join(quoted) + ')' if quoted else ''
        layers = []
        try:
            for table in self.mTables:
                layer = self.createLayer(layerFilter, table)
                if layer is not None: layers.append(layer)
            return layers
        except Exception:
            for layer in layers: sip.delete(layer)
            raise

    def clearPreview(self):
        self.mMapCanvas.stopRendering()
        self.mMapCanvas.setLayers([])
        for layer in self.mPreviewLayers:
            if not sip.isdeleted(layer): sip.delete(layer)
        self.mPreviewLayers = []

    def updatePreview(self):
        self.clearPreview()
        names = [name for name, visible in self.selectedLayers() if visible]
        if not self.mLoadedDatabase or not names: return
        try:
            self.mPreviewLayers = self.createLayers(names)
            if not self.mPreviewLayers: return
            crs = self.mPreviewLayers[0].crs()
            self.mMapCanvas.setDestinationCrs(crs)
            self.mMapCanvas.setLayers(self.mPreviewLayers)
            extent = QgsRectangle()
            for layer in self.mPreviewLayers:
                transform = QgsCoordinateTransform(layer.crs(), crs, self.mProject)
                extent.combineExtentWith(transform.transformBoundingBox(layer.extent()))
            if extent.width() == 0 and extent.height() == 0: extent.grow(1)
            extent.scale(1.1)
            self.mMapCanvas.setExtent(extent)
            self.mMapCanvas.refresh()
        except Exception as error:
            self.bar.pushWarning('预览', str(error))

    def layersClicked(self, *unused):
        if self.mUpdating: return
        self.updateUI()
        self.updatePreview()

    def updateCheckState(self, state):
        self.mUpdating = True
        for row in range(self.mLayers.rowCount()): self.mLayers.item(row, 0).setCheckState(state)
        self.mUpdating = False
        self.layersClicked()

    def pbSelectAll_clicked(self): self.updateCheckState(Qt.Checked)
    def pbDeselectAll_clicked(self): self.updateCheckState(Qt.Unchecked)

    def buttonBox_accepted(self):
        if self.mBusy or not self.buttonBox.button(QDialogButtonBox.Ok).isEnabled(): return False
        # Prepare and validate all providers before mutating the project tree.
        batches = []
        try:
            selected = self.selectedLayers()
            if self.cbMergeLayers.isChecked():
                batches.append((None, True, self.createLayers([name for name, visible in selected])))
            else:
                for name, visible in selected: batches.append((name, visible, self.createLayers([name])))
            if not any(layers for name, visible, layers in batches): raise ValueError('所选图层没有可加载的模型空间几何。')
        except Exception as error:
            for name, visible, layers in batches:
                for layer in layers: sip.delete(layer)
            self.bar.pushCritical('加载失败', str(error))
            return False
        group = self.mProject.layerTreeRoot().addGroup(self.leLayerGroup.text().strip())
        for name, visible, layers in batches:
            if not layers: continue
            target = group.addGroup(name) if name is not None else group
            for layer in layers:
                self.mProject.addMapLayer(layer, False)
                target.addLayer(layer)
            target.setItemVisibilityChecked(visible)
            target.setExpanded(False)
        group.setExpanded(False)
        return True

    def accept(self):
        if self.buttonBox_accepted(): super().accept()

    def reject(self):
        if not self.mBusy: super().reject()

    def showHelp(self):
        QDesktopServices.openUrl(QUrl('https://docs.qgis.org/3.34/en/docs/user_manual/managing_data_source/opening_data.html#importing-a-dxf-or-dwg-file'))
