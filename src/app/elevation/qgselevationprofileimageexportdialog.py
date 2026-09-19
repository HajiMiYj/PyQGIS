from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, QSize
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.gui import QgsGui
from .qgselevationprofileexportsettingswidget import QgsElevationProfileExportSettingsWidget, UI_ROOT


class QgsElevationProfileImageExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(UI_ROOT / 'qgselevationprofileimageexportoptionsdialog.ui'), self)
        self.mProfileSettingsWidget = QgsElevationProfileExportSettingsWidget(self)
        self.scrollAreaLayout.addWidget(self.mProfileSettingsWidget)
        self.scrollAreaLayout.addStretch(1)
        QgsGui.enableAutoGeometryRestore(self)

    def setPlotSettings(self, plot): self.mProfileSettingsWidget.setPlotSettings(plot)
    def updatePlotSettings(self, plot): self.mProfileSettingsWidget.updatePlotSettings(plot)

    def setImageSize(self, size):
        self.mWidthSpinBox.setValue(size.width())
        self.mHeightSpinBox.setValue(size.height())

    def imageSize(self): return QSize(self.mWidthSpinBox.value(), self.mHeightSpinBox.value())

    def accept(self):
        error = self.mProfileSettingsWidget.validationError()
        if self.imageSize().width() <= 0 or self.imageSize().height() <= 0: error = '图片宽高必须大于零'
        if error:
            QMessageBox.warning(self, QCoreApplication.translate('QgsLayoutWidgetBase', 'Export Settings'), error)
            return
        super().accept()
