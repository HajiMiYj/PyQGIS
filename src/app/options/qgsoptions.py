"""QgsOptions application port: original form, native options base and explicit apply logic."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QSize, QUrl
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel, QColor, QDesktopServices, QFont
from qgis.PyQt.QtWidgets import QVBoxLayout, QToolBar, QFileDialog, QInputDialog, QListWidgetItem, QMessageBox
from qgis.core import (QgsApplication, QgsSettings, QgsSettingsRegistryCore, QgsCoordinateReferenceSystem,
                       QgsExpressionContextUtils, QgsNetworkAccessManager, QgsLayerTreeModel, Qgis, QgsTolerance,
                       QgsUserColorScheme)
from qgis.gui import QgsOptionsDialogBase, QgsGui
from .qgsoptionsbindings import (BINDINGS, CORE_BINDINGS, ENTRY_BINDINGS,
                                 PLAIN_BINDINGS, COMBO_BINDINGS, COLOR_BINDINGS)
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
        # Geometry validation is a combo whose native save uses currentData().
        self.comboSetting('mValidateGeometries', 'digitizing/validate-geometries',
                          [('关闭', 0), ('QGIS', 1), ('GEOS', 2)], 1)
        self.initRemainingPages()
        self.initLocaleAndFonts()
        self.initRadioGroups()
        self.initSeparators()
        self.initLayoutDefaults()
        self.initPathLists()
        self.initScalesAndMisc()
        self.initVariablesTables()
        self.initColorSchemes()
        self.initGdalDrivers()
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

    # Enum-valued settings native writes through QgsSettings::setEnumValue(), which
    # stores the enum KEY NAME (e.g. "UseCrsOfFirstLayerAdded") rather than an int.
    # A typed int read aborts on those values, so they are mapped explicitly.
    SETTING_ENUM_INDICES = {
        'app/projections/unknownCrsBehavior': {
            'NoAction': 0, 'PromptUserForCrs': 1, 'UseProjectCrs': 2, 'UseDefaultCrs': 3},
        'app/projections/newProjectCrsBehavior': {
            'UseCrsOfFirstLayerAdded': 0, 'UsePresetCrs': 1, 'UseProjectCrs': 1, 'UseDefaultCrs': 1},
        'qgis/layerTreeInsertionMethod': {
            'AboveInsertionPoint': 0, 'TopOfTree': 1, 'OptimalInInsertionGroup': 2},
        'qgis/promptForSublayers': {
            'AlwaysAsk': 0, 'AskExcludingRasterBands': 1, 'NeverAskSkip': 2, 'NeverAskLoadAll': 3},
        'qgis/copyFeatureFormat': {'AttributesOnly': 0, 'AttributesWithWKT': 1, 'GeoJSON': 2},
        'qgis/attributeTableBehavior': {'ShowAll': 0, 'ShowSelected': 1, 'ShowVisible': 2},
        'digitizing/validate-geometries': {'Off': 0, 'QGIS': 1, 'GEOS': 2},
        'digitizing/offset-join-style': {'Round': 0, 'Miter': 1, 'Bevel': 2},
        'digitizing/offset-cap-style': {'Round': 0, 'Flat': 1, 'Square': 2},
    }

    def settingValue(self, key, default):
        """Read a setting, tolerating the enum key names native QGIS stores.

        Native QgsSettings::enumValue() accepts either an int or the enum key
        name; this mirrors that so a QString-typed value cannot abort the read.
        """
        raw = self.mSettings.value(key, None)
        if raw is None:
            return default
        enumIndices = self.SETTING_ENUM_INDICES.get(key)
        if isinstance(raw, str):
            text = raw.strip()
            if enumIndices and text in enumIndices:
                return enumIndices[text]
            if isinstance(default, bool):
                return text.lower() in ('true', '1', 'yes')
            if isinstance(default, float):
                try:
                    return float(text)
                except ValueError:
                    return default
            if isinstance(default, int):
                try:
                    return int(text)
                except ValueError:
                    return default
            return text
        if isinstance(default, bool):
            return bool(raw)
        if isinstance(default, int):
            try:
                return int(raw)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default
        return raw

    def enable(self, name):
        widget = getattr(self, name)
        widget.setEnabled(True)
        widget.setToolTip(widget.toolTip().replace('\n此控件尚未完成移植', ''))
        self.mImplementedControls.add(name)
        return widget

    def bindSetting(self, name, setter, key, default):
        widget = self.enable(name)
        if isinstance(default, QColor):
            try:
                value = self.mSettings.value(key, default, type=QColor)
            except TypeError:
                value = default
        else:
            value = self.settingValue(key, default)
        getattr(widget, setter)(value)
        self.mBindings.append((key, widget, GETTERS[setter]))

    def comboSetting(self, name, key, options, default):
        widget = self.enable(name)
        widget.clear()
        for title, value in options: widget.addItem(title, value)
        index = widget.findData(self.settingValue(key, default))
        widget.setCurrentIndex(max(0, index))
        self.mBindings.append((key, widget, 'currentData'))

    def initRemainingPages(self):
        """Apply the audited ctor/saveOptions bindings transcribed from qgsoptions.cpp."""
        templateDefault = str(Path(QgsApplication.qgisSettingsDirPath()) / 'project_templates')
        for name, setter, key, default in PLAIN_BINDINGS:
            self.bindSetting(name, setter, key, default or (templateDefault if name == 'leTemplateFolder' else default))
        for name, key, default, items in COMBO_BINDINGS:
            self.comboSetting(name, key, items, default)
        # "Show news" is the inverse of the feed's disabled flag
        # (QgsNewsFeedParser::keyForFeed() strips non-alphanumerics from feed.qgis.org).
        self.mNewsFeedDisabledKey = 'core/httpsfeedqgisorg/disabled'
        self.enable('cbxShowNews').setChecked(
            not self.mSettings.value(self.mNewsFeedDisabledKey, False, type=bool))
        # Default project file format is a radio pair over one enum key.
        fileFormat = self.mSettings.value('qgis/defaultProjectFileFormat', 'Qgz', type=str)
        self.enable('mFileFormatQgsButton').setChecked(fileFormat == 'Qgs')
        self.enable('mFileFormatQgzButton').setChecked(fileFormat != 'Qgs')
        # Colors: identify highlight stores name+alpha, the layout grid four ints.
        self.mExtraColorBindings = []
        for name, prefix in COLOR_BINDINGS:
            if prefix.endswith('grid'):
                components = self.mSettings.value(prefix + 'Red', 190, type=int), \
                    self.mSettings.value(prefix + 'Green', 190, type=int), \
                    self.mSettings.value(prefix + 'Blue', 190, type=int), \
                    self.mSettings.value(prefix + 'Alpha', 100, type=int)
                color = QColor(*components)
            else:
                color = QColor(self.mSettings.value(prefix + 'color', '#ffff00', type=str))
                color.setAlpha(self.mSettings.value(prefix + 'colorAlpha', 255, type=int))
            widget = self.enable(name)
            widget.setColor(color)
            widget.setAllowOpacity(True)
            self.mExtraColorBindings.append((name, prefix))

    def initLocaleAndFonts(self):
        # Locale (native reads/writes QgsApplication::settingsLocaleUserLocale /
        # GlobalLocale / ShowGroupSeparator).
        translation = self.mSettings.value('locale/userLocale', '', type=str)
        widget = self.enable('cboTranslation')
        widget.addItem('', '')
        for name in ('en', 'zh_CN', 'zh_TW', 'de', 'fr', 'es', 'ja', 'ru'):
            widget.addItem(name, name)
        widget.setCurrentIndex(max(0, widget.findData(translation)))
        globalLocale = self.mSettings.value('locale/globalLocale', '', type=str)
        globalWidget = self.enable('cboGlobalLocale')
        globalWidget.addItem('', '')
        for name in ('en_US', 'zh_CN', 'de_DE', 'fr_FR', 'es_ES'):
            globalWidget.addItem(name, name)
        globalWidget.setCurrentIndex(max(0, globalWidget.findData(globalLocale)))
        self.bindSetting('cbShowGroupSeparator', 'setChecked', 'locale/showGroupSeparator', False)
        # Application font (native QgisAppStyleSheet /app/fontPointSize, /app/fontFamily).
        self.bindSetting('spinFontSize', 'setValue', 'app/fontPointSize',
                         float(self.font().pointSizeF()))
        family = self.mSettings.value('app/fontFamily', '', type=str)
        familyWidget = self.enable('mFontFamilyComboBox')
        isDefault = not family
        self.enable('mFontFamilyRadioQt').setChecked(isDefault)
        self.enable('mFontFamilyRadioCustom').setChecked(not isDefault)
        familyWidget.setEnabled(not isDefault)
        if not isDefault:
            familyWidget.setCurrentFont(QFont(family))

    def initRadioGroups(self):
        # Unknown-layer CRS behaviour (app/projections/unknownCrsBehavior,
        # QgsOptions::UnknownLayerCrsBehavior: NoAction/Prompt/UseProject/UseDefault).
        behaviour = self.settingValue('app/projections/unknownCrsBehavior', 0)
        for index, name in enumerate(('radCrsNoAction', 'radPromptForProjection',
                                      'radUseProjectProjection', 'radUseGlobalProjection')):
            self.enable(name).setChecked(index == behaviour)
        # New-project CRS behaviour (app/projections/newProjectCrsBehavior).
        newBehaviour = self.settingValue('app/projections/newProjectCrsBehavior', 0)
        self.enable('radProjectUseCrsOfFirstLayer').setChecked(newBehaviour == 0)
        self.enable('radProjectUseDefaultCrs').setChecked(newBehaviour != 0)

    def initSeparators(self):
        # measure/clipboard-separator is one string shared by seven radios.
        separator = self.mSettings.value('measure/clipboard-separator', '\t', type=str)
        known = {'\t': 'mSeparatorTab', ',': 'mSeparatorComma', ';': 'mSeparatorSemicolon',
                 ' ': 'mSeparatorSpace', ':': 'mSeparatorColon'}
        for name in known.values():
            self.enable(name).setChecked(False)
        self.enable('mSeparatorOther')  # always available, checked only for custom text
        if separator in known:
            self.enable(known[separator]).setChecked(True)
        else:
            self.mSeparatorOther.setChecked(True)
        custom = self.enable('mSeparatorCustom')
        custom.setText(separator if separator not in known else '')
        custom.setEnabled(separator not in known)
        self.mSeparatorOther.toggled.connect(custom.setEnabled)

    def initLayoutDefaults(self):
        # gui/LayoutDesigner/gridStyle ("Solid"/"Dots"/"Crosses").
        gridStyle = self.mSettings.value('gui/LayoutDesigner/gridStyle', 'Dots', type=str)
        styleWidget = self.enable('mGridStyleComboBox')
        styleWidget.clear()
        for label, value in (('实线', 'Solid'), ('点', 'Dots'), ('十字', 'Crosses')):
            styleWidget.addItem(label, value)
        styleWidget.setCurrentIndex(max(0, styleWidget.findData(gridStyle)))
        # gui/LayoutDesigner/defaultFont (empty means the Qt default font).
        font = self.mSettings.value('gui/LayoutDesigner/defaultFont', '', type=str)
        fontWidget = self.enable('mComposerFontComboBox')
        if font:
            fontWidget.setCurrentFont(QFont(font))
        else:
            fontWidget.setCurrentFont(self.font())

    def initPathLists(self):
        """Path lists and their add/remove/move buttons, native ctor 361-429."""
        from qgis.PyQt.QtWidgets import QFileDialog, QTreeWidgetItem
        # plugins/searchPathsForPlugins
        self.mPathListBindings = []
        for listName, getter, setter, editable in (
                ('mListPluginPaths', lambda: self.settingList('plugins/searchPathsForPlugins'),
                 lambda paths: self.mSettings.setValue('plugins/searchPathsForPlugins', paths), True),
                ('mListSVGPaths', lambda: list(QgsApplication.svgPaths()),
                 lambda paths: QgsApplication.setSvgPaths(paths), True),
                ('mListComposerTemplatePaths', lambda: list(QgsApplication.layoutTemplatePaths()),
                 lambda paths: self.mSettings.setValue('layout/search-paths-for-templates', paths), True),
                ('mLocalizedDataPathListWidget', lambda: list(QgsApplication.localizedDataPathRegistry().paths()),
                 lambda paths: self.setLocalizedDataPaths(paths), True),
                ('mListHiddenBrowserPaths', lambda: self.settingList('browser/hiddenPaths'),
                 lambda paths: self.mSettings.setValue('browser/hiddenPaths', paths), False)):
            widget = self.enable(listName)
            widget.clear()
            widget.addItems([str(p) for p in getter()])
            if editable:
                for row in range(widget.count()):
                    widget.item(row).setFlags(widget.item(row).flags() | Qt.ItemIsEditable)
            self.mPathListBindings.append((getter, setter, widget))
        # help/helpSearchPath is a tree widget with one column.
        self.mHelpPathDefault = 'https://docs.qgis.org/$qgis_short_version/$qgis_locale/docs/user_manual/'
        helpPaths = self.settingList('help/helpSearchPath') or [self.mHelpPathDefault]
        tree = self.enable('mHelpPathTreeWidget')
        tree.clear()
        for path in helpPaths:
            tree.addTopLevelItem(QTreeWidgetItem([path]))
        self.mHelpPathTree = tree

        def addPath(listName, title):
            path = QFileDialog.getExistingDirectory(self, title)
            if path:
                getattr(self, listName).addItem(path)
        for button, listName, title in (
                ('mBtnAddPluginPath', 'mListPluginPaths', '插件路径'),
                ('mBtnAddSVGPath', 'mListSVGPaths', 'SVG 路径'),
                ('mBtnAddTemplatePath', 'mListComposerTemplatePaths', '模板路径'),
                ('mLocalizedDataPathAddButton', 'mLocalizedDataPathListWidget', '本地化数据路径')):
            self.enable(button).clicked.connect(lambda _=False, n=listName, t=title: addPath(n, t))
        for button, listName in (('mBtnRemovePluginPath', 'mListPluginPaths'),
                                 ('mBtnRemoveSVGPath', 'mListSVGPaths'),
                                 ('mBtnRemoveTemplatePath', 'mListComposerTemplatePaths'),
                                 ('mLocalizedDataPathRemoveButton', 'mLocalizedDataPathListWidget'),
                                 ('mBtnRemoveHiddenPath', 'mListHiddenBrowserPaths')):
            self.enable(button).clicked.connect(
                lambda _=False, n=listName: [getattr(self, n).takeItem(row)
                                             for row in sorted({getattr(self, n).currentRow()}, reverse=True)
                                             if row >= 0])
        for upButton, downButton, listName in (
                ('mLocalizedDataPathUpButton', 'mLocalizedDataPathDownButton', 'mLocalizedDataPathListWidget'),):
            self.enable(upButton).clicked.connect(lambda _=False, n=listName: self.movePathItem(n, -1))
            self.enable(downButton).clicked.connect(lambda _=False, n=listName: self.movePathItem(n, 1))
        self.enable('mBtnAddHelpPath').clicked.connect(self.addHelpPath)
        self.enable('mBtnRemoveHelpPath').clicked.connect(self.removeHelpPath)
        self.enable('mBtnMoveHelpUp').clicked.connect(lambda: self.moveHelpPath(-1))
        self.enable('mBtnMoveHelpDown').clicked.connect(lambda: self.moveHelpPath(1))

    def setLocalizedDataPaths(self, paths):
        """Native setPaths() has no binding; rebuild through register/unregister."""
        registry = QgsApplication.localizedDataPathRegistry()
        for path in list(registry.paths()):
            registry.unregisterPath(path)
        for path in paths:
            registry.registerPath(path)

    def settingList(self, key):
        """QgsSettings list values may come back as a plain string; normalise both."""
        value = self.mSettings.value(key, [])
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return [str(entry) for entry in value]

    def movePathItem(self, listName, delta):
        widget = getattr(self, listName)
        row = widget.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < widget.count():
            return
        item = widget.takeItem(row)
        widget.insertItem(target, item)
        widget.setCurrentRow(target)

    def addHelpPath(self):
        from qgis.PyQt.QtWidgets import QTreeWidgetItem
        value, ok = QInputDialog.getText(self, '添加帮助路径', 'URL 或路径')
        if ok and value.strip():
            self.mHelpPathTree.addTopLevelItem(QTreeWidgetItem([value.strip()]))

    def removeHelpPath(self):
        item = self.mHelpPathTree.currentItem()
        if item is not None:
            self.mHelpPathTree.takeTopLevelItem(self.mHelpPathTree.indexOfTopLevelItem(item))

    def moveHelpPath(self, delta):
        tree = self.mHelpPathTree
        index = tree.indexOfTopLevelItem(tree.currentItem()) if tree.currentItem() is not None else -1
        target = index + delta
        if index < 0 or not 0 <= target < tree.topLevelItemCount():
            return
        item = tree.takeTopLevelItem(index)
        tree.insertTopLevelItem(target, item)
        tree.setCurrentItem(item)

    def initScalesAndMisc(self):
        from qgis.PyQt.QtWidgets import QTreeWidgetItem
        self.enable('pbnImportScales').clicked.connect(lambda: self.importScales())
        self.enable('pbnExportScales').clicked.connect(lambda: self.exportScales())
        self.enable('pbnProjectDefaultSetCurrent').clicked.connect(self.setCurrentProjectDefault)
        self.enable('pbnProjectDefaultReset').clicked.connect(self.resetProjectDefault)
        self.enable('pbnTemplateFolderBrowse').clicked.connect(self.browseTemplateFolder)
        self.enable('pbnTemplateFolderReset').clicked.connect(self.resetTemplateFolder)
        self.enable('mProjectOnLaunchPushBtn').clicked.connect(self.selectProjectOnLaunch)
        self.enable('mRestoreDefaultWindowStateBtn').clicked.connect(self.restoreDefaultWindowState)
        # Bearing/coordinate format editors (defaults/ groups).
        from qgis.core import QgsLocalDefaultSettings
        self.mBearingFormat = QgsLocalDefaultSettings.bearingFormat()
        self.mCoordinateFormat = QgsLocalDefaultSettings.geographicCoordinateFormat()
        self.enable('mCustomizeBearingFormatButton').clicked.connect(self.customizeBearingFormat)
        self.enable('mCustomizeCoordinateFormatButton').clicked.connect(self.customizeCoordinateFormat)
        self.enable('mOpenClDevicesCombo')
        # QgsOpenClUtils is not exposed to Python, which matches a build without
        # OpenCL support: native disables the device chooser in that case.
        self.mOpenClDevicesCombo.addItem('不可用（此构建未提供 OpenCL 接口）', '')
        self.mOpenClDevicesCombo.setEnabled(False)

    def importScales(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入比例尺', '', '文本文件 (*.txt)')
        if not path:
            return
        with open(path, encoding='utf-8') as stream:
            self.setScales([line.strip() for line in stream if line.strip()])

    def exportScales(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出比例尺', 'scales.txt', '文本文件 (*.txt)')
        if not path:
            return
        with open(path, 'w', encoding='utf-8') as stream:
            for row in range(self.mListGlobalScales.count()):
                stream.write(self.mListGlobalScales.item(row).text() + '\n')

    def defaultProjectPath(self):
        return str(Path(QgsApplication.qgisSettingsDirPath()) / 'project_default.qgs')

    def setCurrentProjectDefault(self):
        fileName = self.defaultProjectPath()
        if QgsProject.instance().write(fileName):
            QMessageBox.information(self, '保存默认工程', '当前工程已保存为默认工程')
        else:
            QMessageBox.critical(self, '保存默认工程', '将当前工程保存为默认工程时出错')

    def resetProjectDefault(self):
        fileName = self.defaultProjectPath()
        if Path(fileName).exists():
            Path(fileName).unlink()
        self.cbxProjectDefaultNew.setChecked(False)

    def browseTemplateFolder(self):
        path = QFileDialog.getExistingDirectory(self, '工程模板目录', self.leTemplateFolder.text())
        if path:
            self.leTemplateFolder.setText(path)

    def resetTemplateFolder(self):
        self.leTemplateFolder.setText(str(Path(QgsApplication.qgisSettingsDirPath()) / 'project_templates'))

    def selectProjectOnLaunch(self):
        path, _ = QFileDialog.getOpenFileName(self, '启动时打开的工程', '', 'QGIS 工程 (*.qgz *.qgs)')
        if path:
            self.mProjectOnLaunchLineEdit.setText(path)

    def restoreDefaultWindowState(self):
        if QMessageBox.question(self, '恢复默认窗口状态', '下次启动时恢复默认窗口布局？',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.mSettings.setValue('qgis/restoreDefaultWindowState', True)

    def customizeBearingFormat(self):
        from qgis.gui import QgsBearingNumericFormatDialog
        dialog = QgsBearingNumericFormatDialog(self.mBearingFormat, self)
        dialog.setWindowTitle('方位角格式')
        if dialog.exec_():
            self.mBearingFormat = dialog.format()

    def customizeCoordinateFormat(self):
        from qgis.gui import QgsGeographicCoordinateNumericFormatDialog
        dialog = QgsGeographicCoordinateNumericFormatDialog(self.mCoordinateFormat, False, self)
        dialog.setWindowTitle('坐标格式')
        if dialog.exec_():
            self.mCoordinateFormat = dialog.format()

    def initVariablesTables(self):
        from qgis.PyQt.QtWidgets import QComboBox, QTableWidgetItem
        self.enable('mAddCustomVarBtn').clicked.connect(self.addCustomVariable)
        self.enable('mRemoveCustomVarBtn').clicked.connect(self.removeCustomVariable)
        self.enable('mCurrentVariablesQGISChxBx').setChecked(True)
        self.enable('mCurrentVariablesQGISChxBx').toggled.connect(self.filterCurrentVariables)
        # custom environment variables (qgis/customEnvVars, "apply|name=value")
        customVars = self.mSettings.value('qgis/customEnvVars', [], type=list)
        table = self.enable('mCustomVariablesTable')
        table.setRowCount(0)
        for entry in customVars:
            if '|' not in entry:
                continue
            apply, _, pair = entry.partition('|')
            name, _, value = pair.partition('=')
            self.addCustomEnvVarRow(name, value, apply)
        # current process environment (read-only reference table)
        current = self.enable('mCurrentVariablesTable')
        current.setRowCount(0)
        systemVars = QgsApplication.systemEnvVars()
        for name in sorted(systemVars):
            row = current.rowCount()
            current.insertRow(row)
            for column, text in enumerate((name, systemVars[name], '')):
                current.setItem(row, column, QTableWidgetItem(str(text)))
        self.mCustomVariablesChkBx.toggled.connect(self.customVariablesToggled)
        self.customVariablesToggled(self.mCustomVariablesChkBx.isChecked())

    def addCustomEnvVarRow(self, name='', value='', apply='overwrite'):
        from qgis.PyQt.QtWidgets import QComboBox, QTableWidgetItem
        table = self.mCustomVariablesTable
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(name))
        table.setItem(row, 1, QTableWidgetItem(value))
        combo = QComboBox()
        for label, key in (('覆盖', 'overwrite'), ('仅在未定义时', 'undefined'), ('取消设置', 'unset'),
                           ('前置', 'prepend'), ('追加', 'append'), ('跳过', 'skip')):
            combo.addItem(label, key)
        combo.setCurrentIndex(max(0, combo.findData(apply)))
        table.setCellWidget(row, 2, combo)

    def addCustomVariable(self):
        if self.mCustomVariablesTable.rowCount() == 0 or \
                self.mCustomVariablesTable.item(self.mCustomVariablesTable.rowCount() - 1, 0) is not None:
            self.addCustomEnvVarRow('', '', 'overwrite')

    def removeCustomVariable(self):
        row = self.mCustomVariablesTable.currentRow()
        if row >= 0:
            self.mCustomVariablesTable.removeRow(row)

    def customVariablesToggled(self, enabled):
        self.mCustomVariablesTable.setEnabled(enabled)
        self.mAddCustomVarBtn.setEnabled(enabled)
        self.mRemoveCustomVarBtn.setEnabled(enabled)

    def filterCurrentVariables(self, qgisOnly):
        for row in range(self.mCurrentVariablesTable.rowCount()):
            item = self.mCurrentVariablesTable.item(row, 0)
            hide = bool(qgisOnly) and item is not None and not item.text().lower().startswith('qgis')
            self.mCurrentVariablesTable.setRowHidden(row, hide)

    def saveVariablesTables(self):
        from qgis.PyQt.QtWidgets import QComboBox
        entries = []
        table = self.mCustomVariablesTable
        for row in range(table.rowCount()):
            name = table.item(row, 0).text() if table.item(row, 0) else ''
            value = table.item(row, 1).text() if table.item(row, 1) else ''
            combo = table.cellWidget(row, 2)
            apply = combo.currentData() if isinstance(combo, QComboBox) else 'overwrite'
            if name and value:
                entries.append(f'{apply}|{name}={value}')
        self.mSettings.setValue('qgis/customEnvVars', entries)

    def initColorSchemes(self):
        from qgis.core import QgsCustomColorScheme
        self.enable('mSchemeToolButton').setMenu(self.buildColorSchemeMenu())
        # The form already carries a native QgsColorSchemeList (mTreeCustomColors).
        self.mColorSchemeList = self.enable('mTreeCustomColors')
        schemes = QgsApplication.colorSchemeRegistry().schemes()
        combo = self.enable('mColorSchemesComboBox')
        combo.clear()
        self.mColorSchemeNames = {}
        for scheme in schemes:
            combo.addItem(scheme.schemeName(), scheme.schemeName())
            self.mColorSchemeNames[scheme.schemeName()] = scheme
        # Native preselects the first user-defined scheme.
        custom = [s for s in schemes if isinstance(s, QgsCustomColorScheme)]
        target = custom[0].schemeName() if custom else (schemes[0].schemeName() if schemes else None)
        if target is not None:
            combo.setCurrentIndex(max(0, combo.findData(target)))
        combo.currentIndexChanged.connect(self.colorSchemeChanged)
        self.colorSchemeChanged(combo.currentIndex())
        for button, slot in (('mButtonAddColor', 'addColor'),
                             ('mButtonRemoveColor', 'removeSelection'),
                             ('mButtonCopyColors', 'copyColors'),
                             ('mButtonPasteColors', 'pasteColors'),
                             ('mButtonImportColors', 'showImportColorsDialog'),
                             ('mButtonExportColors', 'showExportColorsDialog')):
            widget = self.enable(button)
            widget.clicked.connect(lambda _=False, m=slot: self.invokeColorSchemeList(m))

    def buildColorSchemeMenu(self):
        from qgis.PyQt.QtWidgets import QMenu
        menu = QMenu(self)
        self.mActionNewPalette = menu.addAction('新建调色板…')
        self.mActionImportPalette = menu.addAction('导入调色板…')
        self.mActionRemovePalette = menu.addAction('删除调色板…')
        self.mActionShowInButtons = menu.addAction('在颜色按钮中显示')
        self.mActionShowInButtons.setCheckable(True)
        self.mActionShowInButtons.setChecked(True)
        self.mActionNewPalette.triggered.connect(self.newColorPalette)
        return menu

    def invokeColorSchemeList(self, method):
        if self.mColorSchemeList is None:
            return
        if method == 'addColor':
            # The no-argument C++ overload is not bound, so pick the colour here
            # (native connects the button straight to QgsColorSchemeList::addColor).
            from qgis.PyQt.QtWidgets import QColorDialog
            color = QColorDialog.getColor(QColor(Qt.white), self, '选择颜色')
            if color.isValid():
                self.mColorSchemeList.addColor(color)
            return
        getattr(self.mColorSchemeList, method)()

    def colorSchemeChanged(self, index):
        name = self.mColorSchemesComboBox.itemData(index)
        scheme = self.mColorSchemeNames.get(name)
        if scheme is None:
            return
        self.mColorSchemeList.setScheme(scheme)
        editable = scheme.isEditable()
        for button in ('mButtonAddColor', 'mButtonRemoveColor', 'mButtonCopyColors', 'mButtonPasteColors',
                       'mButtonImportColors'):
            getattr(self, button).setEnabled(editable)

    def newColorPalette(self):
        name, ok = QInputDialog.getText(self, '新建调色板', '名称')
        if not ok or not name.strip():
            return
        scheme = QgsUserColorScheme(name.strip())
        QgsApplication.colorSchemeRegistry().addColorScheme(scheme)
        self.initColorSchemesSlot = True

    def saveColorSchemes(self):
        if self.mColorSchemeList is not None and self.mColorSchemeList.isDirty():
            self.mColorSchemeList.saveColorsToScheme()

    def initGdalDrivers(self):
        from qgis.PyQt.QtWidgets import QTreeWidgetItem
        self.mLoadedGdalDriverList = False
        self.mSkippedGdalDrivers = set(QgsApplication.skippedGdalDrivers())
        for name in ('lstRasterDrivers', 'lstVectorDrivers'):
            widget = self.enable(name)
            widget.setColumnCount(1)
            widget.setHeaderLabels(['驱动'])
            widget.itemChanged.connect(self.gdalDriverToggled)
        self.populateGdalDrivers()
        self.enable('pbnEditCreateOptions').clicked.connect(
            lambda: self.editGdalDriver(self.cmbEditCreateOptions.currentText()))
        self.enable('pbnEditPyramidsOptions').clicked.connect(lambda: self.editGdalDriver('_pyramids'))
        self.enable('cmbEditCreateOptions')
        self.cmbEditCreateOptions.clear()
        self.cmbEditCreateOptions.addItem('GTiff')

    def populateGdalDrivers(self):
        from qgis.PyQt.QtWidgets import QTreeWidgetItem
        # Native loadGdalDriverList() enumerates drivers through the GDAL C API,
        # so the matching GDAL Python bindings are used here.
        rasterDrivers, vectorDrivers, writeDrivers = [], [], []
        try:
            from osgeo import gdal
        except ImportError:
            gdal = None
        if gdal is not None:
            gdal.AllRegister()
            for index in range(gdal.GetDriverCount()):
                driver = gdal.GetDriver(index)
                if driver is None:
                    continue
                driverName = driver.ShortName
                if driver.GetMetadataItem(gdal.DCAP_RASTER) == 'YES':
                    rasterDrivers.append(driverName)
                if driver.GetMetadataItem(gdal.DCAP_VECTOR) == 'YES':
                    vectorDrivers.append(driverName)
                if driver.GetMetadataItem(gdal.DCAP_CREATE) == 'YES' or \
                        driver.GetMetadataItem(gdal.DCAP_CREATECOPY) == 'YES':
                    writeDrivers.append(driverName)
        for label, drivers in (('lstRasterDrivers', rasterDrivers), ('lstVectorDrivers', vectorDrivers)):
            tree = getattr(self, label)
            tree.blockSignals(True)
            tree.clear()
            for driverName in sorted(set(drivers)):
                item = QTreeWidgetItem([driverName])
                item.setData(0, Qt.UserRole, driverName)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked if driverName in self.mSkippedGdalDrivers else Qt.Checked)
                tree.addTopLevelItem(item)
            tree.blockSignals(False)
        # The "edit create options" combo lists GDAL write drivers, GTiff first.
        if writeDrivers:
            current = self.cmbEditCreateOptions.currentText()
            self.cmbEditCreateOptions.clear()
            self.cmbEditCreateOptions.addItem('GTiff')
            for driverName in sorted(set(writeDrivers)):
                if driverName != 'GTiff':
                    self.cmbEditCreateOptions.addItem(driverName)
            index = self.cmbEditCreateOptions.findText(current)
            if index >= 0:
                self.cmbEditCreateOptions.setCurrentIndex(index)
        self.mLoadedGdalDriverList = True

    def gdalDriverToggled(self, item, column):
        # Native keeps raster/vector siblings for the same driver in sync.
        driver = item.data(0, Qt.UserRole)
        checked = item.checkState(0) == Qt.Checked
        if checked:
            self.mSkippedGdalDrivers.discard(driver)
        else:
            self.mSkippedGdalDrivers.add(driver)
        sender = self.sender()
        for label in ('lstRasterDrivers', 'lstVectorDrivers'):
            tree = getattr(self, label)
            if tree is sender:
                continue
            for index in range(tree.topLevelItemCount()):
                other = tree.topLevelItem(index)
                if other.data(0, Qt.UserRole) == driver:
                    other.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def editGdalDriver(self, driver):
        from qgis.gui import QgsRasterFormatSaveOptionsWidget, QgsRasterPyramidsOptionsWidget
        from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle('编辑创建选项')
        layout = QVBoxLayout(dialog)
        if driver == '_pyramids':
            widget = QgsRasterPyramidsOptionsWidget(dialog, 'gdal')
        else:
            widget = QgsRasterFormatSaveOptionsWidget(dialog, driver or 'GTiff', 'gdal')
        layout.addWidget(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec_()

    def saveGdalDrivers(self):
        QgsApplication.setSkippedGdalDrivers(sorted(self.mSkippedGdalDrivers), [])

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
        for name, prefix in self.mExtraColorBindings:
            color = getattr(self, name).color()
            if prefix.endswith('grid'):
                for component, value in zip(('Red', 'Green', 'Blue', 'Alpha'), color.getRgb()):
                    self.mSettings.setValue(prefix + component, value)
            else:
                self.mSettings.setValue(prefix + 'color', color.name())
                self.mSettings.setValue(prefix + 'colorAlpha', color.alpha())
        self.mSettings.setValue(self.mNewsFeedDisabledKey, not self.cbxShowNews.isChecked())
        self.mSettings.setValue('qgis/defaultProjectFileFormat',
                                'Qgs' if self.mFileFormatQgsButton.isChecked() else 'Qgz')
        # Native writes QgsSettingsRegistryCore::settingsMapScales, which is not
        # exposed to Python; the entry lives at map/default_scales.
        self.mSettings.setValue('map/default_scales', [self.mListGlobalScales.item(i).text() for i in range(self.mListGlobalScales.count())])
        QgsExpressionContextUtils.setGlobalVariables(self.mVariableEditor.variablesInActiveScope())
        self.mDefaultDatumTransformTableWidget.transformContext().writeSettings()
        self.mLocatorOptionsWidget.commitChanges()
        self.saveRemainingPages()
        self.applyToApplication()
        QgsGui.instance().optionsChanged.emit()

    def saveRemainingPages(self):
        """Writes the locale/font, radio group, path list, variable, colour and GDAL state."""
        from qgis.core import QgsLocalDefaultSettings
        self.mSettings.setValue('locale/userLocale', self.cboTranslation.currentData() or '')
        self.mSettings.setValue('locale/globalLocale', self.cboGlobalLocale.currentData() or '')
        self.mSettings.setValue('app/fontPointSize', self.spinFontSize.value())
        if self.mFontFamilyRadioQt.isChecked():
            self.mSettings.remove('app/fontFamily')
        else:
            self.mSettings.setValue('app/fontFamily', self.mFontFamilyComboBox.currentFont().family())
        for index, name in enumerate(('radCrsNoAction', 'radPromptForProjection',
                                      'radUseProjectProjection', 'radUseGlobalProjection')):
            if getattr(self, name).isChecked():
                self.mSettings.setValue('app/projections/unknownCrsBehavior', index)
                break
        self.mSettings.setValue('app/projections/newProjectCrsBehavior',
                                0 if self.radProjectUseCrsOfFirstLayer.isChecked() else 1)
        separator = '\t'
        for name, value in (('mSeparatorTab', '\t'), ('mSeparatorComma', ','), ('mSeparatorSemicolon', ';'),
                            ('mSeparatorSpace', ' '), ('mSeparatorColon', ':')):
            if getattr(self, name).isChecked():
                separator = value
                break
        else:
            separator = self.mSeparatorCustom.text()
        self.mSettings.setValue('measure/clipboard-separator', separator)
        self.mSettings.setValue('gui/LayoutDesigner/gridStyle', self.mGridStyleComboBox.currentData())
        self.mSettings.setValue('gui/LayoutDesigner/defaultFont', self.mComposerFontComboBox.currentFont().family())
        for _getter, setter, widget in self.mPathListBindings:
            setter([widget.item(row).text() for row in range(widget.count())])
        self.mSettings.setValue('help/helpSearchPath', [
            self.mHelpPathTree.topLevelItem(i).text(0) for i in range(self.mHelpPathTree.topLevelItemCount())])
        self.saveVariablesTables()
        self.saveColorSchemes()
        self.saveGdalDrivers()
        QgsLocalDefaultSettings.setBearingFormat(self.mBearingFormat)
        QgsLocalDefaultSettings.setGeographicCoordinateFormat(self.mCoordinateFormat)

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
