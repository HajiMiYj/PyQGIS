"""Provider-driven source manager corresponding to qgsdatasourcemanagerdialog.cpp."""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QHBoxLayout, QListWidget, QStackedWidget
from qgis.core import QgsProviderRegistry
from qgis.gui import QgsGui


class QgsDataSourceManagerDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.mApp = app
        self.setObjectName('QgsDataSourceManagerDialog')
        self.setWindowTitle(QCoreApplication.translate('QgsDataSourceManagerDialog', 'Data Source Manager'))
        self.resize(1000, 680)
        layout = QHBoxLayout(self)
        self.mOptionsListWidget = QListWidget()
        self.mOptionsListWidget.setMaximumWidth(190)
        self.mOptionsStackedWidget = QStackedWidget()
        layout.addWidget(self.mOptionsListWidget)
        layout.addWidget(self.mOptionsStackedWidget, 1)
        self.mProviders = []
        for provider in QgsGui.sourceSelectProviderRegistry().providers():
            key = provider.providerKey()
            if key.lower() in ('gpx', 'gps'):
                continue
            widget = provider.createDataSourceWidget(self, Qt.Widget, QgsProviderRegistry.WidgetMode.Embedded)
            if widget is None:
                continue
            if hasattr(widget, 'setMapCanvas'):
                widget.setMapCanvas(app.mMapCanvas)
            widget.addVectorLayer.connect(app.addVectorLayer)
            widget.addRasterLayer.connect(app.addRasterLayer)
            widget.addVectorLayers.connect(app.addVectorLayers)
            widget.addRasterLayers.connect(app.addRasterLayers)
            if hasattr(widget, 'addMeshLayer'):
                widget.addMeshLayer.connect(app.addMeshLayer)
            if hasattr(widget, 'addVectorTileLayer'):
                widget.addVectorTileLayer.connect(app.addVectorTileLayer)
            if hasattr(widget, 'addPointCloudLayer'):
                widget.addPointCloudLayer.connect(app.addPointCloudLayer)
            if hasattr(widget, 'addLayer'):
                widget.addLayer.connect(app.addLayerByType)
            widget.connectionsChanged.connect(app.mBrowserModel.refresh)
            self.mProviders.append((provider.name(), key))
            self.mOptionsListWidget.addItem(provider.text())
            self.mOptionsStackedWidget.addWidget(widget)
        self.mOptionsListWidget.currentRowChanged.connect(self.mOptionsStackedWidget.setCurrentIndex)
        self.mOptionsListWidget.setCurrentRow(0)

    def openPage(self, name):
        for i, (providerName, key) in enumerate(self.mProviders):
            if name.lower() in (providerName.lower(), key.lower()):
                self.mOptionsListWidget.setCurrentRow(i)
                break
        self.show()
        self.raise_()

