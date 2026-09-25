"""Python counterpart of the QGIS 3.34 identify results dock."""

from html import escape
from pathlib import Path

from qgis.PyQt import sip, uic
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtPrintSupport import QPrinter, QPrintDialog
from qgis.PyQt.QtWidgets import (QActionGroup, QComboBox, QDialog, QMenu, QTableWidgetItem,
                                 QTextBrowser, QToolButton, QTreeWidgetItem, QWidget)
from qgis.core import (QgsApplication, QgsCoordinateTransform, QgsFeatureRequest,
                       QgsProject, QgsRasterDataProvider, QgsRasterLayer, Qgis,
                       QgsSettings, QgsVariantUtils, QgsVectorLayer)
from qgis.gui import QgsDockWidget, QgsGui, QgsHighlight, QgsMapToolIdentify
from .qgsidentifyplot import QgsIdentifyPlot


class QgsIdentifyResultsDialog(QDialog):
    def __init__(self, canvas, app):
        super().__init__(app)
        uic.loadUi(str(Path(__file__).resolve().parents[1] / 'ui/qgsidentifyresultsbase.ui'), self)
        self.mCanvas = canvas
        self.mApp = app
        self.mResults = []
        self.mHighlights = []
        self.mHtmlByResult = {}
        self.mWidgetCaches = {}
        oldPlotWidget = self.findChild(QWidget, 'mPlot')
        self.mPlot = QgsIdentifyPlot(self.stackedWidgetPage3)
        self.mPlot.setObjectName('mPlot')
        self.stackedWidgetPage3.layout().replaceWidget(oldPlotWidget, self.mPlot)
        oldPlotWidget.hide()
        oldPlotWidget.deleteLater()
        self.mDock = QgsDockWidget('识别结果', app)
        self.mDock.setObjectName('IdentifyResultsDock')
        self.mDock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.mDock.setWidget(self)
        app.addDockWidget(Qt.RightDockWidgetArea, self.mDock)
        app.mPanelMenu.addAction(self.mDock.toggleViewAction())
        self.mDock.hide()

        settings = QgsSettings()
        self.lstResults.setColumnCount(2)
        self.lstResults.setHeaderLabels(['要素', '值'])
        self.lstResults.setSortingEnabled(False)
        self.lstResults.setColumnWidth(0, settings.value('Windows/Identify/columnWidth', 220, type=int))
        self.mExpandNewAction.setChecked(settings.value('Map/identifyExpand', False, type=bool))
        self.mActionAutoFeatureForm.setChecked(settings.value('Map/identifyAutoFeatureForm', False, type=bool))
        self.mActionHideDerivedAttributes.setChecked(settings.value('Map/hideDerivedAttributes', False, type=bool))
        self.mActionHideNullValues.setChecked(settings.value('Map/hideNullValues', False, type=bool))
        self.mIdentifyToolbar.setIconSize(app.iconSize(True))
        self.initSelectionModes()

        for label, mode in [('当前图层', QgsMapToolIdentify.ActiveLayer),
                            ('从上到下，找到第一个即停止', QgsMapToolIdentify.TopDownStopAtFirst),
                            ('从上到下', QgsMapToolIdentify.TopDownAll),
                            ('选择图层', QgsMapToolIdentify.LayerSelection)]:
            self.cmbIdentifyMode.addItem(label, mode)
        mode = settings.value('Map/identifyMode', int(QgsMapToolIdentify.ActiveLayer), type=int)
        index = self.cmbIdentifyMode.findData(mode)
        self.cmbIdentifyMode.setCurrentIndex(index if index >= 0 else 0)
        self.cmbIdentifyMode.currentIndexChanged.connect(
            lambda _: settings.setValue('Map/identifyMode', int(self.identifyMode())))
        for label in ('树', '表', '图表'):
            self.cmbViewMode.addItem(label)
        self.cmbViewMode.currentIndexChanged.connect(self.stackedWidget.setCurrentIndex)
        self.cmbViewMode.setEnabled(False)
        self.lblViewMode.setEnabled(False)

        self.mOpenFormAction.triggered.connect(self.featureForm)
        self.mExpandAction.triggered.connect(self.lstResults.expandAll)
        self.mCollapseAction.triggered.connect(self.lstResults.collapseAll)
        self.mExpandNewAction.toggled.connect(lambda checked: settings.setValue('Map/identifyExpand', checked))
        self.mClearResultsAction.triggered.connect(self.clear)
        self.mActionCopy.triggered.connect(self.copyFeature)
        self.mActionPrint.triggered.connect(self.printCurrentItem)
        self.mActionPrint.setEnabled(False)
        self.lstResults.currentItemChanged.connect(self.currentItemChanged)
        self.lstResults.itemDoubleClicked.connect(self.itemActivated)
        self.lstResults.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lstResults.customContextMenuRequested.connect(self.showContextMenu)
        for action, key in ((self.mActionAutoFeatureForm, 'Map/identifyAutoFeatureForm'),
                            (self.mActionHideDerivedAttributes, 'Map/hideDerivedAttributes'),
                            (self.mActionHideNullValues, 'Map/hideNullValues')):
            action.toggled.connect(lambda checked, setting=key: self.changeSetting(setting, checked))
        self.mActionAutoFeatureForm.toggled.connect(self.autoFeatureFormToggled)
        self.autoFeatureFormToggled(self.mActionAutoFeatureForm.isChecked())
        settingsButton = QToolButton(self.mIdentifyToolbar)
        settingsButton.setIcon(QgsApplication.getThemeIcon('/mActionOptions.svg'))
        settingsButton.setToolTip('识别设置')
        settingsButton.setPopupMode(QToolButton.InstantPopup)
        settingsMenu = QMenu(settingsButton)
        for action in (self.mActionAutoFeatureForm, self.mActionHideDerivedAttributes,
                       self.mActionHideNullValues):
            settingsMenu.addAction(action)
        settingsButton.setMenu(settingsMenu)
        self.mIdentifyToolbar.addWidget(settingsButton)
        self.mIdentifyToolbar.addSeparator()
        self.mIdentifyToolbar.addAction(self.mHelpToolAction)
        self.mHelpToolAction.triggered.connect(lambda: app.mActionHelpContents.trigger())
        self.updateActions()

    def identifyMode(self):
        return self.cmbIdentifyMode.currentData()

    def initSelectionModes(self):
        self.mSelectModeButton = QToolButton(self.mIdentifyToolbar)
        self.mSelectModeButton.setPopupMode(QToolButton.MenuButtonPopup)
        self.mSelectModeMenu = QMenu(self.mSelectModeButton)
        self.mSelectModeGroup = QActionGroup(self)
        self.mSelectionActions = (
            self.mActionSelectFeatures,
            self.mActionSelectFeaturesOnMouseOver,
            self.mActionSelectPolygon,
            self.mActionSelectFreehand,
            self.mActionSelectRadius,
        )
        for mode, action in enumerate(self.mSelectionActions):
            action.setCheckable(True)
            action.setData(mode)
            self.mSelectModeGroup.addAction(action)
            self.mSelectModeMenu.addAction(action)
            action.triggered.connect(lambda checked, chosen=action: self.setSelectionMode(chosen))
        self.mSelectModeButton.setMenu(self.mSelectModeMenu)
        self.mSelectModeButton.setDefaultAction(self.mActionSelectFeatures)
        self.mActionSelectFeatures.setChecked(True)
        self.mIdentifyToolbar.insertWidget(self.mOpenFormAction, self.mSelectModeButton)

    def setSelectionMode(self, action):
        self.mSelectModeButton.setDefaultAction(action)
        action.setChecked(True)
        tool = self.mApp.mMapTools.get('identify') if hasattr(self.mApp, 'mMapTools') else None
        if tool is not None:
            tool.setSelectionMode(int(action.data()))
            self.mCanvas.setMapTool(tool)

    def changeSetting(self, key, checked):
        QgsSettings().setValue(key, checked)
        self.rebuild()

    def autoFeatureFormToggled(self, checked):
        self.mActionSelectFeaturesOnMouseOver.setEnabled(not checked)
        if checked and self.mActionSelectFeaturesOnMouseOver.isChecked():
            self.setSelectionMode(self.mActionSelectFeatures)

    def showResults(self, results):
        self.mResults = list(results)
        self.rebuild()
        if self.mResults:
            self.mDock.show()
            self.mDock.raise_()
            if len(self.mResults) == 1 and self.mActionAutoFeatureForm.isChecked():
                self.lstResults.setCurrentItem(self._featureItems[0])
                self.featureForm()
        else:
            self.mApp.statusBar().showMessage('此位置未找到要素', 2000)

    def rebuild(self):
        self.clearHighlights()
        self.lstResults.clear()
        self.tblResults.setRowCount(0)
        self.mPlot.clear()
        self.mHtmlByResult.clear()
        self._relatedResults = {}
        self._featureItems = []
        layers = {}
        rasterFound = False
        for index, result in enumerate(self.mResults):
            layer = result.mLayer
            if layer is None:
                continue
            layerItem = layers.get(layer.id())
            if layerItem is None:
                layerItem = QTreeWidgetItem(self.lstResults, [layer.name(), ''])
                layerItem.setData(0, Qt.UserRole, index)
                layers[layer.id()] = layerItem
                if isinstance(layer, QgsRasterLayer) and layer.isValid():
                    self.addRasterFormatSelector(layerItem, layer)
            feature = result.mFeature
            valid = feature.isValid()
            label = result.mLabel or (str(feature.id()) if valid else layer.name())
            if valid and isinstance(layer, QgsVectorLayer):
                displayField = layer.displayField()
                if displayField and displayField in feature.fields().names():
                    label = str(feature.attribute(displayField))
            featureItem = QTreeWidgetItem(layerItem, [label, str(feature.id()) if valid else ''])
            featureItem.setData(0, Qt.UserRole, index)
            self._featureItems.append(featureItem)
            if valid and isinstance(layer, QgsVectorLayer) and not self.mActionHideDerivedAttributes.isChecked():
                self.addVectorActionItems(featureItem, result)
            if valid:
                for fieldIndex, (field, value) in enumerate(zip(feature.fields(), feature.attributes())):
                    if isinstance(layer, QgsVectorLayer):
                        setup = QgsGui.editorWidgetRegistry().findBest(layer, field.name())
                        if setup.type() == 'Hidden':
                            continue
                        formatter = QgsApplication.fieldFormatterRegistry().fieldFormatter(setup.type())
                        if formatter is not None:
                            cacheKey = (layer.id(), fieldIndex)
                            if cacheKey not in self.mWidgetCaches:
                                self.mWidgetCaches[cacheKey] = formatter.createCache(
                                    layer, fieldIndex, setup.config())
                            displayed = formatter.representValue(
                                layer, fieldIndex, setup.config(), self.mWidgetCaches[cacheKey], value)
                        else:
                            displayed = field.displayString(value)
                    else:
                        displayed = field.displayString(value)
                    if QgsVariantUtils.isNull(value) and self.mActionHideNullValues.isChecked():
                        continue
                    attributeItem = QTreeWidgetItem(featureItem, [field.displayName(), displayed])
                    attributeItem.setData(0, Qt.UserRole + 1, fieldIndex)
                    attributeItem.setToolTip(1, displayed)
                    self.addTableRow(layer.name(), feature.id(), field.displayName(), value)
                if isinstance(layer, QgsVectorLayer):
                    self.addRelatedFeatures(featureItem, result)
            if not self.mActionHideDerivedAttributes.isChecked() and result.mDerivedAttributes:
                derivedItem = QTreeWidgetItem(featureItem, ['(派生)', ''])
                for key, value in result.mDerivedAttributes.items():
                    QTreeWidgetItem(derivedItem, [str(key), str(value)])
                    self.addTableRow(layer.name(), feature.id() if valid else '', key, value)
            html = self.htmlForResult(result) if isinstance(layer, QgsRasterLayer) else ''
            for key, value in result.mAttributes.items():
                if not html:
                    QTreeWidgetItem(featureItem, [str(key), str(value)])
                self.addTableRow(layer.name(), feature.id() if valid else '', key, value)
            if isinstance(layer, QgsRasterLayer):
                if html:
                    self.mHtmlByResult[index] = html
                    htmlItem = QTreeWidgetItem(featureItem, ['HTML', ''])
                    htmlItem.setSizeHint(1, QSize(0, 180))
                    browser = QTextBrowser(self.lstResults)
                    browser.setOpenExternalLinks(True)
                    browser.setHtml(html)
                    self.lstResults.setItemWidget(htmlItem, 1, browser)
                self.mPlot.addCurve(result.mAttributes, layer.name())
            rasterFound = rasterFound or isinstance(layer, QgsRasterLayer)
            if self.mExpandNewAction.isChecked():
                layerItem.setExpanded(True)
                featureItem.setExpanded(True)
        self.cmbViewMode.setEnabled(rasterFound)
        self.lblViewMode.setEnabled(rasterFound)
        if not rasterFound:
            self.cmbViewMode.setCurrentIndex(0)
        self.updateActions()

    def addVectorActionItems(self, featureItem, result):
        layer = result.mLayer
        fieldActions = [action for action in layer.actions().actions('Feature')
                        if action.runable() and not action.isEnabledOnlyWhenEditable()]
        registryActions = [action for action in QgsGui.mapLayerActionRegistry().mapLayerActions(
            layer, context=self.mApp.createMapLayerActionContext())
            if not action.isEnabledOnlyWhenEditable()]
        if not layer.fields() and not fieldActions and not registryActions:
            return
        group = QTreeWidgetItem(featureItem, ['(动作)', ''])
        if layer.fields():
            item = QTreeWidgetItem(group, ['', '编辑要素表单' if layer.isEditable() else '查看要素表单'])
            item.setIcon(0, QgsApplication.getThemeIcon('/mActionFormView.svg'))
            item.setData(0, Qt.UserRole + 2, 'edit')
        for action in fieldActions:
            item = QTreeWidgetItem(group, ['', action.name()])
            item.setIcon(0, QgsApplication.getThemeIcon('/mAction.svg'))
            item.setData(0, Qt.UserRole + 2, 'action')
            item.setData(0, Qt.UserRole + 3, action.id())
        for action in registryActions:
            item = QTreeWidgetItem(group, ['', action.text()])
            item.setIcon(0, QgsApplication.getThemeIcon('/mAction.svg'))
            item.setData(0, Qt.UserRole + 2, 'map_layer_action')
            item.setData(0, Qt.UserRole + 3, action)

    def addRelatedFeatures(self, featureItem, result):
        for relation in QgsProject.instance().relationManager().referencedRelations(result.mLayer):
            children = list(relation.getRelatedFeatures(result.mFeature))
            if not children:
                continue
            relationItem = QTreeWidgetItem(featureItem, [f'{relation.name()} [{len(children)}]', ''])
            relatedLayer = relation.referencingLayer()
            for feature in children:
                label = str(feature.attribute(relatedLayer.displayField())) \
                    if relatedLayer.displayField() in feature.fields().names() else str(feature.id())
                childItem = QTreeWidgetItem(relationItem, [label, str(feature.id())])
                self._relatedResults[id(childItem)] = QgsMapToolIdentify.IdentifyResult(
                    relatedLayer, feature, {})
                for field, value in zip(feature.fields(), feature.attributes()):
                    if not (QgsVariantUtils.isNull(value) and self.mActionHideNullValues.isChecked()):
                        QTreeWidgetItem(childItem, [field.displayName(), field.displayString(value)])

    def itemActivated(self, item, column):
        result = self.resultForItem(item)
        marker = item.data(0, Qt.UserRole + 2)
        if marker == 'action' and result is not None and isinstance(result.mLayer, QgsVectorLayer):
            result.mLayer.actions().doActionFeature(item.data(0, Qt.UserRole + 3), result.mFeature)
        elif marker == 'map_layer_action' and result is not None:
            item.data(0, Qt.UserRole + 3).triggerForFeature(
                result.mLayer, result.mFeature, self.mApp.createMapLayerActionContext())
        elif marker == 'edit':
            self.featureForm()

    def addRasterFormatSelector(self, layerItem, layer):
        provider = layer.dataProvider()
        if provider is None:
            return
        combo = QComboBox(self.lstResults)
        currentFormat = QgsRasterDataProvider.identifyFormatFromName(
            str(layer.customProperty('identify/format', '')))
        for fmt in (Qgis.RasterIdentifyFormat.Html, Qgis.RasterIdentifyFormat.Feature,
                    Qgis.RasterIdentifyFormat.Text, Qgis.RasterIdentifyFormat.Value):
            if provider.capabilities() & QgsRasterDataProvider.identifyFormatToCapability(fmt):
                combo.addItem(QgsRasterDataProvider.identifyFormatLabel(fmt), fmt)
        if combo.count() <= 1:
            combo.deleteLater()
            return
        index = combo.findData(currentFormat)
        if index >= 0:
            combo.setCurrentIndex(index)
        formatItem = QTreeWidgetItem(layerItem, [' 格式', ''])
        self.lstResults.setItemWidget(formatItem, 1, combo)
        combo.currentIndexChanged.connect(
            lambda _, selectedLayer=layer, selector=combo: self.formatChanged(selectedLayer, selector.currentData()))

    def formatChanged(self, layer, fmt):
        if fmt is None:
            return
        layer.setCustomProperty('identify/format', QgsRasterDataProvider.identifyFormatName(fmt))
        tool = self.mApp.mMapTools.get('identify') if hasattr(self.mApp, 'mMapTools') else None
        if tool is not None and tool.mLastIdentify is not None:
            tool.repeatIdentify()

    @staticmethod
    def htmlForResult(result):
        attributes = result.mAttributes
        if not attributes:
            return ''
        fmt = str(result.mLayer.customProperty('identify/format', '')).lower()
        key, value = next(iter(attributes.items()))
        if fmt == 'html' or str(key).lower() == 'html':
            return str(value)
        if fmt == 'text' or str(key).lower() == 'text':
            return f'<pre style="font-family:monospace">{escape(str(value))}</pre>'
        if str(value).lstrip().lower().startswith(('<html', '<!doctype html')):
            return str(value)
        return ''

    def addTableRow(self, layer, fid, name, value):
        row = self.tblResults.rowCount()
        self.tblResults.insertRow(row)
        for column, data in enumerate((layer, fid, name, value)):
            self.tblResults.setItem(row, column, QTableWidgetItem(str(data)))

    def resultForItem(self, item):
        node = item
        while node is not None:
            related = self._relatedResults.get(id(node))
            if related is not None:
                return related
            node = node.parent()
        index = self.resultIndexForItem(item)
        return self.mResults[index] if index is not None else None

    def resultIndexForItem(self, item):
        while item is not None:
            index = item.data(0, Qt.UserRole)
            if isinstance(index, int) and 0 <= index < len(self.mResults):
                return index
            item = item.parent()
        return None

    def currentItemChanged(self, current, previous):
        self.clearHighlights()
        result = self.resultForItem(current)
        feature = result.mFeature if result else None
        canUseFeature = bool(result and isinstance(result.mLayer, QgsVectorLayer)
                             and feature.isValid())
        self.mOpenFormAction.setEnabled(canUseFeature)
        self.mActionCopy.setEnabled(canUseFeature)
        self.mActionPrint.setEnabled(self.resultIndexForItem(current) in self.mHtmlByResult)
        if current is not None and current.parent() is None and result is not None:
            self.highlightResults(result.mLayer)
        elif canUseFeature and feature.hasGeometry():
            highlight = QgsHighlight(self.mCanvas, feature, result.mLayer)
            highlight.setColor(QColor(255, 0, 0))
            highlight.setFillColor(QColor(255, 0, 0, 40))
            highlight.show()
            self.mHighlights.append(highlight)

    def updateActions(self):
        result = self.resultForItem(self.lstResults.currentItem())
        enabled = bool(result and isinstance(result.mLayer, QgsVectorLayer)
                       and result.mFeature.isValid())
        self.mOpenFormAction.setEnabled(enabled)
        self.mActionCopy.setEnabled(enabled)
        self.mActionPrint.setEnabled(self.resultIndexForItem(self.lstResults.currentItem()) in self.mHtmlByResult)

    def printCurrentItem(self):
        html = self.mHtmlByResult.get(self.resultIndexForItem(self.lstResults.currentItem()))
        if not html:
            return
        printer = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(printer, self).exec_() == QDialog.Accepted:
            browser = QTextBrowser()
            browser.setHtml(html)
            browser.document().print_(printer)

    def clearHighlights(self):
        for highlight in self.mHighlights:
            highlight.hide()
            sip.delete(highlight)
        self.mHighlights.clear()

    def clear(self):
        self.mResults.clear()
        self.mWidgetCaches.clear()
        self.rebuild()

    def featureForm(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result and isinstance(result.mLayer, QgsVectorLayer) and result.mFeature.isValid():
            self.mApp.mQgisInterface.openFeatureForm(result.mLayer, result.mFeature)

    def copyFeature(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if not result or not isinstance(result.mLayer, QgsVectorLayer) or not result.mFeature.isValid():
            return
        from qgis.core import QgsFeature
        layer, feature = result.mLayer, result.mFeature
        self.mApp.mClipboard = (layer.fields(), layer.crs(), [QgsFeature(feature)], layer.wkbType())
        values = '\t'.join(field.name() for field in layer.fields()) + '\n'
        values += '\t'.join(str(value) for value in feature.attributes())
        QgsApplication.clipboard().setText(values)
        self.mApp.updateActionState()

    def zoomToFeature(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if not result or not result.mFeature.isValid() or not result.mFeature.hasGeometry():
            return
        rectangle = result.mFeature.geometry().boundingBox()
        transform = QgsCoordinateTransform(result.mLayer.crs(), self.mCanvas.mapSettings().destinationCrs(),
                                           QgsProject.instance())
        rectangle = transform.transformBoundingBox(rectangle)
        if rectangle.width() == 0 or rectangle.height() == 0:
            rectangle.grow(self.mCanvas.mapUnitsPerPixel() * 20)
        else:
            rectangle.scale(1.2)
        self.mCanvas.setExtent(rectangle)
        self.mCanvas.refresh()

    def copyAttributeValue(self):
        item = self.lstResults.currentItem()
        if item is not None and item.childCount() == 0:
            QgsApplication.clipboard().setText(item.text(1))

    def copyFeatureAttributes(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result is None:
            return
        feature = result.mFeature
        attributes = ([(field.displayName(), value) for field, value in
                       zip(feature.fields(), feature.attributes())] if feature.isValid() else [])
        attributes.extend(result.mAttributes.items())
        QgsApplication.clipboard().setText(
            '\n'.join(f'{name}\t{value}' for name, value in attributes))

    def toggleFeatureSelection(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result is None or not isinstance(result.mLayer, QgsVectorLayer) or not result.mFeature.isValid():
            return
        fid = result.mFeature.id()
        if fid in result.mLayer.selectedFeatureIds():
            result.mLayer.deselect(fid)
        else:
            result.mLayer.select(fid)

    def highlightLayer(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result is None:
            return
        self.clearHighlights()
        self.highlightResults(result.mLayer)

    def highlightAll(self):
        self.clearHighlights()
        self.highlightResults()

    def highlightResults(self, onlyLayer=None):
        for result in self.mResults:
            if onlyLayer is not None and result.mLayer is not onlyLayer:
                continue
            if not isinstance(result.mLayer, QgsVectorLayer) or not result.mFeature.isValid() \
                    or not result.mFeature.hasGeometry():
                continue
            highlight = QgsHighlight(self.mCanvas, result.mFeature, result.mLayer)
            highlight.setColor(QColor(255, 0, 0))
            highlight.setFillColor(QColor(255, 0, 0, 40))
            highlight.show()
            self.mHighlights.append(highlight)

    def activateLayer(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result is not None:
            self.mApp.setActiveLayer(result.mLayer)

    def selectFeatureByAttribute(self):
        item = self.lstResults.currentItem()
        result = self.resultForItem(item)
        if item is None or result is None or not isinstance(result.mLayer, QgsVectorLayer):
            return
        fieldIndex = next((i for i, field in enumerate(result.mLayer.fields())
                           if item.text(0) in (field.name(), field.displayName())), -1)
        if fieldIndex < 0 or not result.mFeature.isValid():
            return
        wanted = result.mFeature.attribute(fieldIndex)
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry)
        request.setSubsetOfAttributes([fieldIndex], result.mLayer.fields())
        ids = [feature.id() for feature in result.mLayer.getFeatures(request)
               if feature.attribute(fieldIndex) == wanted]
        result.mLayer.selectByIds(ids)

    def copyGetFeatureInfoUrl(self):
        result = self.resultForItem(self.lstResults.currentItem())
        if result is not None:
            QgsApplication.clipboard().setText(str(result.mParams.get('getFeatureInfoUrl', '')))

    def showContextMenu(self, point):
        menu = QMenu(self.lstResults)
        item = self.lstResults.itemAt(point)
        if item is not None:
            self.lstResults.setCurrentItem(item)
        result = self.resultForItem(item)
        if result and isinstance(result.mLayer, QgsVectorLayer) and result.mFeature.isValid():
            menu.addAction(self.mOpenFormAction)
            menu.addAction('缩放到要素', self.zoomToFeature)
            menu.addAction('切换要素选择状态', self.toggleFeatureSelection)
            menu.addAction(self.mActionCopy)
            menu.addAction('复制要素属性', self.copyFeatureAttributes)
            if item.childCount() == 0:
                menu.addAction('复制属性值', self.copyAttributeValue)
                if any(item.text(0) in (field.name(), field.displayName())
                       for field in result.mLayer.fields()):
                    menu.addAction('按属性值选择要素', self.selectFeatureByAttribute)
        if result is not None:
            if isinstance(result.mLayer, QgsRasterLayer) and result.mParams.get('getFeatureInfoUrl'):
                menu.addAction('复制 GetFeatureInfo 请求 URL', self.copyGetFeatureInfoUrl)
            menu.addSeparator()
            menu.addAction('清除高亮', self.clearHighlights)
            menu.addAction('高亮全部', self.highlightAll)
            menu.addAction('高亮图层', self.highlightLayer)
            menu.addAction('激活图层', self.activateLayer)
            menu.addAction('图层属性…', lambda: self.mApp.showLayerProperties(result.mLayer))
        menu.addSeparator()
        menu.addAction(self.mClearResultsAction)
        menu.addAction(self.mExpandAction)
        menu.addAction(self.mCollapseAction)
        if result is not None and isinstance(result.mLayer, QgsVectorLayer) and result.mFeature.isValid():
            fieldIndex = next((i for i, field in enumerate(result.mLayer.fields())
                               if item.text(0) in (field.name(), field.displayName())), 0)
            fieldActions = [action for action in result.mLayer.actions().actions('Field')
                            if action.runable() and (not action.isEnabledOnlyWhenEditable()
                                                    or result.mLayer.isEditable())]
            registryActions = [action for action in QgsGui.mapLayerActionRegistry().mapLayerActions(
                result.mLayer, context=self.mApp.createMapLayerActionContext())
                if not action.isEnabledOnlyWhenEditable() or result.mLayer.isEditable()]
            if fieldActions or registryActions:
                menu.addSeparator()
            for action in fieldActions:
                menu.addAction(action.name(), lambda checked=False, selected=action, field=fieldIndex:
                               result.mLayer.actions().doActionFeature(selected.id(), result.mFeature, field))
            for action in registryActions:
                menu.addAction(action.text(), lambda checked=False, selected=action:
                               selected.triggerForFeature(result.mLayer, result.mFeature,
                                                          self.mApp.createMapLayerActionContext()))
        menu.exec_(self.lstResults.viewport().mapToGlobal(point))

    def saveSettings(self):
        QgsSettings().setValue('Windows/Identify/columnWidth', self.lstResults.columnWidth(0))
        QgsSettings().setValue('Windows/Identify/columnWidthTable', self.tblResults.columnWidth(0))
        self.clearHighlights()
