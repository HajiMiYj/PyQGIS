"""Counterpart of options/qgsrasterrenderingoptions.cpp, using its original form.

This page was absent from the port: every key below (default RGB bands, zoomed
in/out resampling, oversampling, early resampling, contrast enhancement and
min/max limits per band type, cumulative cut, standard deviation factor) was
unreachable from the Options dialog.
"""
from pathlib import Path
from qgis.PyQt import uic
from qgis.core import QgsSettings, QgsRasterLayer, QgsContrastEnhancement, QgsRasterMinMaxOrigin
from qgis.gui import QgsOptionsPageWidget

ROOT = Path(__file__).resolve().parents[2]

ENHANCEMENTS = [
    ('不拉伸', QgsContrastEnhancement.NoEnhancement),
    ('拉伸到最小/最大', QgsContrastEnhancement.StretchToMinimumMaximum),
    ('拉伸并截断到最小/最大', QgsContrastEnhancement.StretchAndClipToMinimumMaximum),
    ('截断到最小/最大', QgsContrastEnhancement.ClipToMinimumMaximum),
]
LIMITS = [
    ('累计像素计数截断', QgsRasterMinMaxOrigin.CumulativeCut),
    ('最小/最大', QgsRasterMinMaxOrigin.MinMax),
    ('均值 ± 标准差', QgsRasterMinMaxOrigin.StdDev),
]
RESAMPLING = [('最近邻', 'nearest neighbour'), ('双线性（2x2 核）', 'bilinear'), ('三次（4x4 核）', 'cubic')]
BAND_TYPES = ('singleBand', 'multiBandSingleByte', 'multiBandMultiByte')
# QgsRasterMinMaxOrigin constants used as native defaults.
CUMULATIVE_CUT_LOWER = 0.02
CUMULATIVE_CUT_UPPER = 0.98
DEFAULT_STDDEV_FACTOR = 2.0


class QgsRasterRenderingOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgsrasterrenderingoptionsbase.ui'), self)
        self.setObjectName('mOptionsPageRasterRendering')
        settings = QgsSettings()

        for widget, key, default in ((self.spnRed, 'defaultRedBand', 1),
                                     (self.spnGreen, 'defaultGreenBand', 2),
                                     (self.spnBlue, 'defaultBlueBand', 3)):
            widget.setValue(settings.value('Raster/' + key, default, type=int))
            widget.setClearValue(default)

        for combo in (self.mZoomedInResamplingComboBox, self.mZoomedOutResamplingComboBox):
            for label, value in RESAMPLING:
                combo.addItem(label, value)
        self.mZoomedInResamplingComboBox.setCurrentIndex(
            max(0, self.mZoomedInResamplingComboBox.findData(
                settings.value('Raster/defaultZoomedInResampling', 'nearest neighbour', type=str))))
        self.mZoomedOutResamplingComboBox.setCurrentIndex(
            max(0, self.mZoomedOutResamplingComboBox.findData(
                settings.value('Raster/defaultZoomedOutResampling', 'nearest neighbour', type=str))))

        # QgsRasterLayer::settingsRasterDefaultOversampling/-EarlyResampling.
        self.spnOversampling.setValue(settings.value('raster/default-oversampling', 2.0, type=float))
        self.spnOversampling.setClearValue(2.0)
        self.mCbEarlyResampling.setChecked(settings.value('raster/default-early-resampling', False, type=bool))

        for combo, name, default in (
                (self.cboxContrastEnhancementAlgorithmSingleBand, 'singleBand',
                 QgsContrastEnhancement.contrastEnhancementAlgorithmString(QgsRasterLayer.SINGLE_BAND_ENHANCEMENT_ALGORITHM)),
                (self.cboxContrastEnhancementAlgorithmMultiBandSingleByte, 'multiBandSingleByte',
                 QgsContrastEnhancement.contrastEnhancementAlgorithmString(QgsRasterLayer.MULTIPLE_BAND_SINGLE_BYTE_ENHANCEMENT_ALGORITHM)),
                (self.cboxContrastEnhancementAlgorithmMultiBandMultiByte, 'multiBandMultiByte',
                 QgsContrastEnhancement.contrastEnhancementAlgorithmString(QgsRasterLayer.MULTIPLE_BAND_MULTI_BYTE_ENHANCEMENT_ALGORITHM))):
            for label, value in ENHANCEMENTS:
                combo.addItem(label, QgsContrastEnhancement.contrastEnhancementAlgorithmString(value))
            combo.setCurrentIndex(max(0, combo.findData(
                settings.value('Raster/defaultContrastEnhancementAlgorithm/' + name, default, type=str))))

        for combo, name, default in (
                (self.cboxContrastEnhancementLimitsSingleBand, 'singleBand',
                 QgsRasterMinMaxOrigin.limitsString(QgsRasterLayer.SINGLE_BAND_MIN_MAX_LIMITS)),
                (self.cboxContrastEnhancementLimitsMultiBandSingleByte, 'multiBandSingleByte',
                 QgsRasterMinMaxOrigin.limitsString(QgsRasterLayer.MULTIPLE_BAND_SINGLE_BYTE_MIN_MAX_LIMITS)),
                (self.cboxContrastEnhancementLimitsMultiBandMultiByte, 'multiBandMultiByte',
                 QgsRasterMinMaxOrigin.limitsString(QgsRasterLayer.MULTIPLE_BAND_MULTI_BYTE_MIN_MAX_LIMITS))):
            for label, value in LIMITS:
                combo.addItem(label, QgsRasterMinMaxOrigin.limitsString(value))
            combo.setCurrentIndex(max(0, combo.findData(
                settings.value('Raster/defaultContrastEnhancementLimits/' + name, default, type=str))))

        lower = settings.value('Raster/cumulativeCutLower', CUMULATIVE_CUT_LOWER, type=float)
        upper = settings.value('Raster/cumulativeCutUpper', CUMULATIVE_CUT_UPPER, type=float)
        self.mRasterCumulativeCutLowerDoubleSpinBox.setValue(100.0 * lower)
        self.mRasterCumulativeCutLowerDoubleSpinBox.setClearValue(100 * CUMULATIVE_CUT_LOWER)
        self.mRasterCumulativeCutUpperDoubleSpinBox.setValue(100.0 * upper)
        self.mRasterCumulativeCutUpperDoubleSpinBox.setClearValue(100 * CUMULATIVE_CUT_UPPER)
        self.spnThreeBandStdDev.setValue(
            settings.value('Raster/defaultStandardDeviation', DEFAULT_STDDEV_FACTOR, type=float))
        self.spnThreeBandStdDev.setClearValue(DEFAULT_STDDEV_FACTOR)

    def apply(self):
        settings = QgsSettings()
        for widget, key in ((self.spnRed, 'defaultRedBand'), (self.spnGreen, 'defaultGreenBand'),
                            (self.spnBlue, 'defaultBlueBand')):
            settings.setValue('Raster/' + key, widget.value())
        for combo, key in ((self.mZoomedInResamplingComboBox, 'defaultZoomedInResampling'),
                           (self.mZoomedOutResamplingComboBox, 'defaultZoomedOutResampling')):
            settings.setValue('Raster/' + key, combo.currentData())
        settings.setValue('raster/default-oversampling', self.spnOversampling.value())
        settings.setValue('raster/default-early-resampling', self.mCbEarlyResampling.isChecked())
        for combo, name in ((self.cboxContrastEnhancementAlgorithmSingleBand, 'singleBand'),
                            (self.cboxContrastEnhancementAlgorithmMultiBandSingleByte, 'multiBandSingleByte'),
                            (self.cboxContrastEnhancementAlgorithmMultiBandMultiByte, 'multiBandMultiByte')):
            settings.setValue('Raster/defaultContrastEnhancementAlgorithm/' + name, combo.currentData())
        for combo, name in ((self.cboxContrastEnhancementLimitsSingleBand, 'singleBand'),
                            (self.cboxContrastEnhancementLimitsMultiBandSingleByte, 'multiBandSingleByte'),
                            (self.cboxContrastEnhancementLimitsMultiBandMultiByte, 'multiBandMultiByte')):
            settings.setValue('Raster/defaultContrastEnhancementLimits/' + name, combo.currentData())
        settings.setValue('Raster/cumulativeCutLower', self.mRasterCumulativeCutLowerDoubleSpinBox.value() / 100.0)
        settings.setValue('Raster/cumulativeCutUpper', self.mRasterCumulativeCutUpperDoubleSpinBox.value() / 100.0)
        settings.setValue('Raster/defaultStandardDeviation', self.spnThreeBandStdDev.value())
