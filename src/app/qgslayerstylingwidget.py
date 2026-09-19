"""Layer styling panel using native renderer widgets and style manager."""
from qgis.PyQt.QtCore import QCoreApplication, Qt, QTimer
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QCheckBox, QPushButton, QLabel
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsAnnotationLayer, QgsStyle
from qgis.gui import QgsRendererPropertiesDialog, QgsMapLayerStyleManagerWidget, QgsSingleBandGrayRendererWidget, QgsSingleBandPseudoColorRendererWidget, QgsMultiBandColorRendererWidget, QgsPalettedRendererWidget, QgsHillshadeRendererWidget


class QgsLayerStylingWidget(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.mApp, self.mLayer, self.mRendererWidget = app, None, None
        self.mTimer = QTimer(self)
        self.mTimer.setSingleShot(True)
        self.mTimer.timeout.connect(self.apply)
        layout = QVBoxLayout(self)
        self.mLayerLabel = QLabel('选择图层以修改样式')
        layout.addWidget(self.mLayerLabel)
        self.mStackedWidget = QTabWidget()
        layout.addWidget(self.mStackedWidget)
        self.mLiveApplyCheck = QCheckBox('实时更新')
        self.mLiveApplyCheck.setChecked(True)
        layout.addWidget(self.mLiveApplyCheck)
        button = QPushButton(QCoreApplication.translate('QgsFeatureFilterWidget', 'Apply'))
        button.clicked.connect(self.apply)
        layout.addWidget(button)
        properties = QPushButton(QCoreApplication.translate('QgsIdentifyResultsDialog', 'Layer Properties…'))
        properties.clicked.connect(lambda: self.mApp.showLayerProperties(self.mLayer) if self.mLayer else None)
        layout.addWidget(properties)
    def setLayer(self, layer):
        if layer is self.mLayer: return
        self.mTimer.stop()
        self.mLayer, self.mRendererWidget = layer, None
        while self.mStackedWidget.count():
            widget = self.mStackedWidget.widget(0)
            self.mStackedWidget.removeTab(0)
            widget.deleteLater()
        self.mLayerLabel.setText(layer.name() if layer else '选择图层以修改样式')
        if layer is None: return
        if isinstance(layer, QgsVectorLayer):
            self.mRendererWidget = QgsRendererPropertiesDialog(layer, QgsStyle.defaultStyle(), True, self)
            self.mRendererWidget.setWindowFlags(Qt.Widget)
            self.mRendererWidget.setMapCanvas(self.mApp.mMapCanvas)
        elif isinstance(layer, QgsRasterLayer):
            widgets = {'singlebandgray': QgsSingleBandGrayRendererWidget, 'singlebandpseudocolor': QgsSingleBandPseudoColorRendererWidget,
                       'multibandcolor': QgsMultiBandColorRendererWidget, 'paletted': QgsPalettedRendererWidget, 'hillshade': QgsHillshadeRendererWidget}
            cls = widgets.get(layer.renderer().type())
            if cls:
                self.mRendererWidget = cls(layer, layer.extent())
                self.mRendererWidget.setMapCanvas(self.mApp.mMapCanvas)
        elif isinstance(layer, QgsAnnotationLayer):
            from .annotations.qgsannotationitempropertieswidget import QgsAnnotationItemPropertiesWidget
            self.mRendererWidget = QgsAnnotationItemPropertiesWidget(layer, self.mApp.mMapCanvas, self)
        if self.mRendererWidget:
            self.mStackedWidget.addTab(self.mRendererWidget, '符号系统')
            self.mRendererWidget.widgetChanged.connect(self.autoApply)
        self.mStyleManager = QgsMapLayerStyleManagerWidget(layer, self.mApp.mMapCanvas, self)
        self.mStackedWidget.addTab(self.mStyleManager, QCoreApplication.translate('DlgRenderingStyles', 'Style'))
    def setAnnotationItem(self, layer, itemId):
        self.setLayer(layer)
        self.mTimer.stop()
        self.mRendererWidget.setItemId(itemId)
        self.mStackedWidget.setCurrentWidget(self.mRendererWidget)
        self.mRendererWidget.focusDefaultWidget()
    def autoApply(self):
        if self.mLiveApplyCheck.isChecked(): self.mTimer.start(180)
    def apply(self):
        if not self.mLayer or not self.mRendererWidget: return
        if isinstance(self.mLayer, (QgsVectorLayer, QgsAnnotationLayer)): self.mRendererWidget.apply()
        else:
            renderer = self.mRendererWidget.renderer()
            if not renderer: return
            self.mLayer.setRenderer(renderer)
        self.mLayer.triggerRepaint()
        node = self.mApp.mProject.layerTreeRoot().findLayer(self.mLayer.id())
        if node: self.mApp.mLayerTreeModel.refreshLayerLegend(node)
        self.mApp.mProject.setDirty(True)
