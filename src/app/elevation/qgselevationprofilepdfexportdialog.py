from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, QSignalBlocker
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.core import QgsApplication, QgsLayoutItemPage, QgsLayoutSize, QgsLayoutMeasurementConverter, Qgis
from qgis.gui import QgsGui
from .qgselevationprofileexportsettingswidget import QgsElevationProfileExportSettingsWidget, UI_ROOT


class QgsElevationProfilePdfExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(UI_ROOT / 'qgselevationprofilepdfexportoptionsdialog.ui'), self)
        self.mProfileSettingsWidget = QgsElevationProfileExportSettingsWidget(self)
        self.scrollAreaLayout.addWidget(self.mProfileSettingsWidget)
        self.scrollAreaLayout.addStretch(1)
        self.mConverter = QgsLayoutMeasurementConverter()
        self.mSettingPresetSize = False
        QgsGui.enableAutoGeometryRestore(self)
        self.mPageOrientationComboBox.addItem(QCoreApplication.translate('QgsElevationProfilePdfExportDialog', 'Portrait'), QgsLayoutItemPage.Portrait)
        self.mPageOrientationComboBox.addItem(QCoreApplication.translate('QgsElevationProfilePdfExportDialog', 'Landscape'), QgsLayoutItemPage.Landscape)
        for size in QgsApplication.pageSizeRegistry().entries(): self.mPageSizeComboBox.addItem(size.displayName, size.name)
        self.mPageSizeComboBox.addItem(QCoreApplication.translate('QgsElevationProfilePdfExportDialog', 'Custom'), '')
        self.mSizeUnitsComboBox.setUnit(Qgis.LayoutUnit.Millimeters)
        self.mSizeUnitsComboBox.setConverter(self.mConverter)
        self.mSizeUnitsComboBox.linkToWidget(self.mWidthSpin)
        self.mSizeUnitsComboBox.linkToWidget(self.mHeightSpin)
        self.mLockAspectRatio.setWidthSpinBox(self.mWidthSpin)
        self.mLockAspectRatio.setHeightSpinBox(self.mHeightSpin)
        self.mPageSizeComboBox.setCurrentIndex(self.mPageSizeComboBox.findData('A4'))
        self.mPageOrientationComboBox.setCurrentIndex(self.mPageOrientationComboBox.findData(QgsLayoutItemPage.Landscape))
        self.mPageSizeComboBox.currentIndexChanged.connect(self.pageSizeChanged)
        self.mPageOrientationComboBox.currentIndexChanged.connect(self.orientationChanged)
        self.mWidthSpin.valueChanged.connect(self.setToCustomSize)
        self.mHeightSpin.valueChanged.connect(self.setToCustomSize)
        self.pageSizeChanged()

    def setPlotSettings(self, plot): self.mProfileSettingsWidget.setPlotSettings(plot)
    def updatePlotSettings(self, plot): self.mProfileSettingsWidget.updatePlotSettings(plot)

    def pageSizeMM(self):
        return self.mConverter.convert(QgsLayoutSize(self.mWidthSpin.value(), self.mHeightSpin.value(), self.mSizeUnitsComboBox.unit()), Qgis.LayoutUnit.Millimeters)

    def pageSizeChanged(self, *args):
        preset = self.mPageSizeComboBox.currentData()
        self.mLockAspectRatio.setEnabled(not bool(preset))
        self.mSizeUnitsComboBox.setEnabled(not bool(preset))
        self.mPageOrientationComboBox.setEnabled(bool(preset))
        if not preset: return
        self.mLockAspectRatio.setLocked(False)
        matches = QgsApplication.pageSizeRegistry().find(preset)
        if not matches: return
        size = self.mConverter.convert(matches[0].size, self.mSizeUnitsComboBox.unit())
        width, height = size.width(), size.height()
        if self.mPageOrientationComboBox.currentData() == QgsLayoutItemPage.Landscape: width, height = max(width, height), min(width, height)
        else: width, height = min(width, height), max(width, height)
        self.mSettingPresetSize = True
        try:
            self.mWidthSpin.setValue(width)
            self.mHeightSpin.setValue(height)
        finally: self.mSettingPresetSize = False

    def orientationChanged(self, *args): self.pageSizeChanged()

    def setToCustomSize(self, *args):
        if self.mSettingPresetSize: return
        blocker = QSignalBlocker(self.mPageSizeComboBox)
        self.mPageSizeComboBox.setCurrentIndex(self.mPageSizeComboBox.count() - 1)
        blocker.unblock()
        self.pageSizeChanged()

    def accept(self):
        error = self.mProfileSettingsWidget.validationError()
        size = self.pageSizeMM()
        if size.width() <= 0 or size.height() <= 0: error = '页面宽高必须大于零'
        if error:
            QMessageBox.warning(self, QCoreApplication.translate('QgsLayoutWidgetBase', 'Export Settings'), error)
            return
        super().accept()
