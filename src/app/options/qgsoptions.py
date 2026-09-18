"""QgsOptions application port: original form, native options base and explicit apply logic."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QSize, QUrl
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel, QColor, QDesktopServices
from qgis.PyQt.QtWidgets import QVBoxLayout, QToolBar, QFileDialog, QInputDialog, QListWidgetItem
from qgis.core import (QgsApplication, QgsSettings, QgsSettingsRegistryCore, QgsCoordinateReferenceSystem,
                       QgsExpressionContextUtils, QgsNetworkAccessManager, QgsLayerTreeModel, Qgis, QgsTolerance)
from qgis.gui import QgsOptionsDialogBase, QgsGui
from .qgsoptionsbindings import BINDINGS, CORE_BINDINGS, ENTRY_BINDINGS
from .qgsrenderingoptions import QgsRenderingOptionsWidget
from .qgsconfigureshortcutsdialog import QgsConfigureShortcutsDialog

ROOT = Path(__file__).resolve().parents[3]
GETTERS = {'setChecked': 'isChecked', 'setValue': 'value', 'setText': 'text', 'setCurrentIndex': 'currentIndex', 'setColor': 'color', 'setCurrentText': 'currentText'}
# Qgis::defaultProjectScales(), used as the registry entry's default value.
DEFAULT_SCALES = (Qgis.defaultProjectScales().split(',') if hasattr(Qgis, 'defaultProjectScales')
                  else ['1:1000000', '1:500000', '1:250000', '1:100000', '1:50000', '1:25000',
                        '1:10000', '1:5000', '1:2500', '1:1000', '1:500'])


class QgsOptions(QgsOptionsDialogBase):
    def __init__(self, app, currentPage=''):
        super().__init__('Options', app)
        self.mApp, self.mSettings = app, QgsSettings()
        self.mBindings, self.mCoreBindings, self.mPages = [], [], []
        self.mImplementedControls = set()
        uic.loadUi(str(ROOT / 'src/ui/qgsoptionsbase.ui'), self)
        self.setObjectName('QgsOptions')
        self.mTreeModel = QStandardItemModel(self)
        self.createTree()
        self.mOptionsTreeView.setModel(self.mTreeModel)
        self.initOptionsBase(False, '选项')
        self.resize(1000, 720)
        # Disable only controls declared by the form. Native widget internals
        # (auth, projection selectors, etc.) keep their own working actions.
        tree = ET.parse(ROOT / 'src/ui/qgsoptionsbase.ui')
        self.mFormControls = {}
        interactive = {'QLineEdit', 'QComboBox', 'QFontComboBox', 'QSpinBox', 'QDoubleSpinBox', 'QCheckBox', 'QRadioButton', 'QPushButton', 'QToolButton', 'QgsSpinBox', 'QgsDoubleSpinBox', 'QgsColorButton', 'QgsProjectionSelectionWidget', 'QListWidget', 'QTreeWidget', 'QTableWidget'}
        for element in tree.findall('.//widget'):
            name = element.get('name')
            if element.get('class') in interactive:
                widget = getattr(self, name)
                self.mFormControls[name] = widget
                widget.setEnabled(False)
                widget.setToolTip(widget.toolTip() + '\n此控件尚未完成移植')
        for name, setter, key, default in BINDINGS:
            # Display counts need a separate layer-tree indicator implementation.
            self.bindSetting(name, setter, key, default)
        for name, setter, key, default in ENTRY_BINDINGS:
            # Native drives these through QgsSettingsRegistryCore entries, which
            # are not exposed to Python; the raw registry keys are used instead.
            self.bindSetting(name, setter, key, default)
        self.initDigitizing()

    def initDigitizing(self):
        # Geometry validation is a combo whose native save uses currentData().
        self.comboSetting('mValidateGeometries', 'digitizing/validate-geometries',
                          [('关闭', 0), ('QGIS', 1), ('GEOS', 2)], 1)
        self.initGeneral()
        self.initNetwork()
        self.initMapTools()
        self.initNativePages()
        self.mRenderingOptionsWidget = QgsRenderingOptionsWidget(self)
        self.insertPage('渲染', '渲染', QgsApplication.getThemeIcon('/propertyicons/rendering.svg'), self.mRenderingOptionsWidget, 'mOptionsPageMapCanvas', [], 'rendering')
        self.mPages.append(self.mRenderingOptionsWidget)
        for factory in app.mQgisInterface.mOptionsFactories:
            page = factory.createWidget(self)
            if page is None: continue
            self.addPage(factory.title(), factory.title(), factory.icon(), page, factory.path(), factory.key())
            self.mPages.append(page)
            if currentPage and currentPage.lower().replace('options', '') in (factory.title() + page.objectName()).lower():
                currentPage = page.objectName()
        self.buttonBox.helpRequested.connect(lambda: QDesktopServices.openUrl(QUrl('https://docs.qgis.org/3.34/en/docs/user_manual/introduction/qgis_configuration.html')))
        self.restoreOptionsBaseUi('选项')
        if currentPage: self.setCurrentPage(currentPage)
        self.writeCoverage()

    def createTree(self):
        # Depth-first ordering is the order of pages in qgsoptionsbase.ui.
        items = [('常规', 'general', None), ('系统', 'system', None),
                 ('CRS 与转换', 'CRS', 'group'), ('CRS 处理', 'CRS', 'crs'), ('坐标转换', 'CRS', 'crs'),
                 ('数据源', 'attributes', None), ('GDAL', 'gdal', 'data'), ('画布与图例', 'overlay', None),
                 ('地图工具', 'map_tools', None), ('数字化', 'digitizing', 'tools'), ('颜色', 'colors', None),
                 ('布局', 'layouts', None), ('变量', 'expression', None), ('身份认证', 'authentication', None),
                 ('网络', 'network_and_proxy', None), ('定位器', 'search', None), ('加速', 'system', None)]
        groups = {}
        for title, icon, parent in items:
            item = QStandardItem(QgsApplication.getThemeIcon('/propertyicons/' + icon + '.svg'), title)
            item.setEditable(False)
            if parent == 'group':
                item.setSelectable(False)
                item.setData('crs_and_transforms')
                groups['crs'] = item
                self.mTreeModel.appendRow(item)
            elif parent: groups[parent].appendRow(item)
            else:
                self.mTreeModel.appendRow(item)
                if title == '数据源': groups['data'] = item
                if title == '地图工具': groups['tools'] = item
        ide = QStandardItem('IDE')
        ide.setSelectable(False)
        ide.setData('ide')
        self.mTreeModel.appendRow(ide)

    def enable(self, name):
        widget = getattr(self, name)
        widget.setEnabled(True)
        widget.setToolTip(widget.toolTip().replace('\n此控件尚未完成移植', ''))
        self.mImplementedControls.add(name)
        return widget

    def bindSetting(self, name, setter, key, default):
        widget = self.enable(name)
        value = self.mSettings.value(key, default, type=type(default))
        getattr(widget, setter)(value)
        self.mBindings.append((key, widget, GETTERS[setter]))

    def comboSetting(self, name, key, options, default):
        widget = self.enable(name)
        widget.clear()
        for title, value in options: widget.addItem(title, value)
        index = widget.findData(self.mSettings.value(key, default, type=type(default)))
        widget.setCurrentIndex(max(0, index))
        self.mBindings.append((key, widget, 'currentData'))

    def initGeneral(self):
        self.comboSetting('cmbIconSize', 'qgis/toolbarIconSize', [(str(size), size) for size in (16, 24, 32, 48, 64)], 24)
        self.enable('leNullValue').setText(QgsApplication.nullRepresentation())
        self.bindSetting('mMapTipsDelaySpinBox', 'setValue', 'qgis/mapTipsDelay', 850)
        self.comboSetting('cmbScanItemsInBrowser', 'qgis/scanItemsInBrowser2', [('检查文件内容', 'contents'), ('检查扩展名', 'extension')], 'extension')
        self.comboSetting('cmbScanZipInBrowser', 'qgis/scanZipInBrowser2', [('否', 'no'), ('基本扫描', 'basic'), ('完整扫描', 'full')], 'basic')
        self.enable('leProjectGlobalCrs').setCrs(QgsCoordinateReferenceSystem(self.mSettings.value('projections/defaultProjectCrs', 'EPSG:4326')))
        self.enable('leLayerGlobalCrs').setCrs(QgsCoordinateReferenceSystem(self.mSettings.value('Projections/layerDefaultCrs', 'EPSG:4326')))
        self.mColorBindings = []
        for name, prefix, default in [('pbnSelectionColor', 'default_selection_color', QColor(255, 255, 0)), ('pbnCanvasColor', 'default_canvas_color', QColor('white')), ('pbnMeasureColor', 'default_measure_color', QColor(222, 155, 67))]:
            color = QColor(*[self.mSettings.value('qgis/' + prefix + '_' + component, value, type=int) for component, value in zip(('red', 'green', 'blue', 'alpha'), default.getRgb())])
            widget = self.enable(name)
            widget.setColor(color)
            widget.setDefaultColor(default)
            if name == 'pbnSelectionColor': widget.setAllowOpacity(True)
            self.mColorBindings.append((prefix, widget))

    def initNetwork(self):
        self.enable('mNetworkTimeoutSpinBox').setValue(QgsNetworkAccessManager.timeout())
        for name, key in [('leProxyHost', 'proxy/proxyHost'), ('leProxyPort', 'proxy/proxyPort'), ('mCacheDirectory', 'cache/directory')]:
            self.bindSetting(name, 'setText', key, '')
        self.comboSetting('mProxyTypeComboBox', 'proxy/proxyType', [(value, value) for value in ('DefaultProxy', 'Socks5Proxy', 'HttpProxy', 'HttpCachingProxy')], 'DefaultProxy')
        self.mAuthSettings.setDataprovider('proxy')
        self.mAuthSettings.setConfigId(self.mSettings.value('proxy/authcfg', ''))
        self.mAuthSettings.setUsername(self.mSettings.value('proxy/proxyUser', ''))
        self.mAuthSettings.setPassword(self.mSettings.value('proxy/proxyPassword', ''))
        self.enable('mNoProxyUrlListWidget').addItems(self.mSettings.value('proxy/proxyExcludedUrls', [], type=list))
        self.enable('mAddUrlPushButton').clicked.connect(self.addNoProxyUrl)
        self.enable('mRemoveUrlPushButton').clicked.connect(lambda: self.mNoProxyUrlListWidget.takeItem(self.mNoProxyUrlListWidget.currentRow()))
        cache = QgsNetworkAccessManager.instance().cache()
        self.enable('mCacheSize').setValue(int(cache.maximumCacheSize() / 1024) if cache else 51200)
        self.enable('mBrowseCacheDirectory').clicked.connect(self.browseCacheDirectory)
        self.enable('mClearCache').clicked.connect(lambda: QgsNetworkAccessManager.instance().cache().clear() if QgsNetworkAccessManager.instance().cache() else None)
        self.enable('mClearAccessCache').clicked.connect(QgsNetworkAccessManager.instance().clearAccessCache)

    def addNoProxyUrl(self):
        value, ok = QInputDialog.getText(self, '代理例外', 'URL 或主机名')
        if ok and value.strip(): self.mNoProxyUrlListWidget.addItem(value.strip())
    def browseCacheDirectory(self):
        path = QFileDialog.getExistingDirectory(self, '缓存目录', self.mCacheDirectory.text())
        if path: self.mCacheDirectory.setText(path)

    def initMapTools(self):
        for name, key, default in [('spinBoxIdentifyValue', 'Map/searchRadiusMM', 2.0), ('mIdentifyHighlightBufferSpinBox', 'Map/highlight/buffer', .5), ('mIdentifyHighlightMinWidthSpinBox', 'Map/highlight/minWidth', 1.0), ('mDecimalPlacesSpinBox', 'qgis/measure/decimalplaces', 3)]:
            self.bindSetting(name, 'setValue', key, default)
        self.bindSetting('mKeepBaseUnitCheckBox', 'setChecked', 'qgis/measure/keepbaseunit', True)
        self.enable('spinZoomFactor').setValue(round(100 * self.mSettings.value('qgis/zoom_factor', 2.0, type=float)))
        self.spinZoomFactor.setMinimum(101)
        # for name, entryName, choices in [
        #     ('mDefaultSnapTypeComboBox', 'settingsDigitizingDefaultSnapType', [('顶点', Qgis.SnappingType.Vertex), ('线段', Qgis.SnappingType.Segment), ('顶点和线段', Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment)]),
        #     ('mDefaultSnappingToleranceComboBox', 'settingsDigitizingDefaultSnappingToleranceUnit', [('图层单位', QgsTolerance.LayerUnits), ('像素', QgsTolerance.Pixels), ('工程单位', QgsTolerance.ProjectUnits)]),
        #     ('mSearchRadiusVertexEditComboBox', 'settingsDigitizingSearchRadiusVertexEditUnit', [('图层单位', QgsTolerance.LayerUnits), ('像素', QgsTolerance.Pixels), ('工程单位', QgsTolerance.ProjectUnits)])]:
        #     entry = getattr(QgsSettingsRegistryCore, entryName)
        #     widget = self.enable(name)
        #     widget.clear()
        #     for title, value in choices: widget.addItem(title, value)
        #     widget.setCurrentIndex(max(0, widget.findData(entry.value())))
        #     self.mCoreBindings.append((entry, widget, 'currentData'))
        # 使用字符串作为 userData，与 QgsSettings 存储格式一致
        snap_configs = [
            (
                'mDefaultSnapTypeComboBox',
                'qgis/digitizing/default_snap_type',
                [('顶点', 'Vertex'), ('线段', 'Segment'), ('顶点和线段', 'VertexAndSegment')],
                'Vertex'
            ),
            (
                'mDefaultSnappingToleranceComboBox',
                'qgis/digitizing/default_snapping_tolerance_unit',
                [('图层单位', 'LayerUnits'), ('像素', 'Pixels'), ('工程单位', 'ProjectUnits')],
                'Pixels'
            ),
            (
                'mSearchRadiusVertexEditComboBox',
                'qgis/digitizing/search_radius_vertex_edit_unit',
                [('图层单位', 'LayerUnits'), ('像素', 'Pixels'), ('工程单位', 'ProjectUnits')],
                'Pixels'
            ),
        ]

        for widget_name, settings_key, choices, default_val in snap_configs:
            widget = self.enable(widget_name)
            widget.clear()
            for label, data in choices:
                widget.addItem(label, data)
            # 从 QgsSettings 读取当前值
            current = self.mSettings.value(settings_key, default_val, type=str)
            idx = widget.findData(current)
            widget.setCurrentIndex(max(0, idx))
            # 加入 mBindings，saveOptions 中统一保存
            self.mBindings.append((settings_key, widget, 'currentData'))
        self.enable('mListGlobalScales')
        default_scales = [
            '1:1000000', '1:500000', '1:250000', '1:100000', '1:50000',
            '1:25000', '1:10000', '1:5000', '1:2500', '1:1000', '1:500'
        ]
        scales = self.mSettings.value('map/default_scales', default_scales, type=list)
        self.setScales(scales)
        self.enable('pbnAddScale').clicked.connect(self.addScale)
        self.enable('pbnRemoveScale').clicked.connect(lambda: self.mListGlobalScales.takeItem(self.mListGlobalScales.currentRow()))
        self.enable('pbnDefaultScaleValues').clicked.connect(lambda: self.setScales(DEFAULT_SCALES))

    def setScales(self, scales):
        self.mListGlobalScales.clear()
        self.mListGlobalScales.addItems(scales)
    def addScale(self):
        value, ok = QInputDialog.getDouble(self, '添加比例尺', '1 :', 1000, 1, 1e12, 0)
        if ok: self.mListGlobalScales.addItem(f'1:{value:.0f}')

    def initNativePages(self):
        self.mVariableEditor.context().appendScope(QgsExpressionContextUtils.globalScope())
        self.mVariableEditor.reloadContext()
        self.mVariableEditor.setEditableScopeIndex(0)
        from ..locator.qgslocatoroptionswidget import QgsLocatorOptionsWidget
        self.mLocatorOptionsWidget = QgsLocatorOptionsWidget(self.mApp.mLocatorWidget, self)
        QVBoxLayout(self.mOptionsLocatorGroupBox).addWidget(self.mLocatorOptionsWidget)
        # Authentication and coordinate-operation widgets own their controls.
        self.mImplementedControls.update(('mVariableEditor', 'mDefaultDatumTransformTableWidget', 'mAuthConfigsGrpBx', 'mAuthSettings'))

    def accept(self):
        if any(not page.isValid() for page in self.mPages): return
        self.saveOptions()
        super().accept()
    def apply(self): self.accept()
    def saveOptions(self):
        for key, widget, getter in self.mBindings: self.mSettings.setValue(key, getattr(widget, getter)())
        for entry, widget, getter in self.mCoreBindings: entry.setValue(getattr(widget, getter)())
        for page in self.mPages: page.apply()
        QgsApplication.setNullRepresentation(self.leNullValue.text())
        self.mSettings.setValue('projections/defaultProjectCrs', self.leProjectGlobalCrs.crs().authid())
        self.mSettings.setValue('Projections/layerDefaultCrs', self.leLayerGlobalCrs.crs().authid())
        QgsNetworkAccessManager.setTimeout(self.mNetworkTimeoutSpinBox.value())
        self.mSettings.setValue('proxy/authcfg', self.mAuthSettings.configId())
        self.mSettings.setValue('proxy/proxyUser', self.mAuthSettings.username())
        self.mSettings.setValue('proxy/proxyPassword', self.mAuthSettings.password())
        self.mSettings.setValue('proxy/proxyExcludedUrls', [self.mNoProxyUrlListWidget.item(i).text() for i in range(self.mNoProxyUrlListWidget.count())])
        self.mSettings.setValue('cache/size', self.mCacheSize.value() * 1024)
        self.mSettings.setValue('qgis/zoom_factor', self.spinZoomFactor.value() / 100)
        for prefix, widget in self.mColorBindings:
            for component, value in zip(('red', 'green', 'blue', 'alpha'), widget.color().getRgb()):
                self.mSettings.setValue('qgis/' + prefix + '_' + component, value)
        # Native writes QgsSettingsRegistryCore::settingsMapScales, which is not
        # exposed to Python; the entry lives at map/default_scales.
        self.mSettings.setValue('map/default_scales', [self.mListGlobalScales.item(i).text() for i in range(self.mListGlobalScales.count())])
        QgsExpressionContextUtils.setGlobalVariables(self.mVariableEditor.variablesInActiveScope())
        self.mDefaultDatumTransformTableWidget.transformContext().writeSettings()
        self.mLocatorOptionsWidget.commitChanges()
        self.applyToApplication()
        QgsGui.instance().optionsChanged.emit()

    def applyToApplication(self):
        app, settings = self.mApp, self.mSettings
        for toolbar in app.findChildren(QToolBar): toolbar.setIconSize(QSize(self.cmbIconSize.currentData(), self.cmbIconSize.currentData()))
        app.mMapCanvas.enableAntiAliasing(self.mRenderingOptionsWidget.chkAntiAliasing.isChecked())
        app.mMapCanvas.setMapUpdateInterval(self.mRenderingOptionsWidget.spinMapUpdateInterval.value())
        app.mMapCanvas.setWheelFactor(self.spinZoomFactor.value() / 100)
        app.mMapCanvas.setCanvasColor(self.pbnCanvasColor.color())
        app.mMapCanvas.setSelectionColor(self.pbnSelectionColor.color())
        app.mMapCanvas.setMagnificationFactor(self.mRenderingOptionsWidget.doubleSpinBoxMagnifierDefault.value() / 100)
        app.mMagnifierWidget.setDefaultFactor(self.mRenderingOptionsWidget.doubleSpinBoxMagnifierDefault.value() / 100)
        app.mpMapTipsTimer.setInterval(self.mMapTipsDelaySpinBox.value())
        app.mProject.layerTreeRegistryBridge().setNewLayersVisible(self.mRenderingOptionsWidget.chkAddedVisibility.isChecked())
        app.mLayerTreeModel.setFlag(QgsLayerTreeModel.ShowLegendAsTree, self.cbxLegendClassifiers.isChecked())
        app.mScaleWidget.updateScales()
        QgsNetworkAccessManager.instance().setupDefaultProxyAndCache()
        app.mBrowserModel.refresh()
        app.mMapCanvas.refresh()

    def writeCoverage(self):
        unported = sorted(set(self.mFormControls) - self.mImplementedControls)
        (ROOT / 'docs/options-status.json').write_text(json.dumps({'implementedControls': sorted(self.mImplementedControls), 'unportedControls': unported, 'pages': self.mOptionsStackedWidget.count(), 'note': 'Control wiring inventory, not complete behavioral parity.'}, ensure_ascii=False, indent=2), encoding='utf-8')
