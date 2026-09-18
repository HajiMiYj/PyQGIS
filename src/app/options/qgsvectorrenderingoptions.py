"""Counterpart of options/qgsvectorrenderingoptions.cpp, using its original form.

Absent from the port before: default simplify-drawing configuration, simplify
algorithm and tolerance, provider-side simplification, simplify maximum scale,
and the curve segmentation tolerance/type.
"""
import math
from pathlib import Path
from qgis.PyQt import uic
from qgis.core import (QgsSettings, QgsVectorLayer, QgsVectorSimplifyMethod, QgsAbstractGeometry, Qgis)
from qgis.gui import QgsOptionsPageWidget

ROOT = Path(__file__).resolve().parents[2]

ALGORITHMS = [('距离', 'Distance', QgsVectorSimplifyMethod.Distance),
              ('对齐到网格', 'SnapToGrid', QgsVectorSimplifyMethod.SnapToGrid),
              ('Visvalingam', 'Visvalingam', QgsVectorSimplifyMethod.Visvalingam)]
TOLERANCE_TYPES = [('最大角度', 'MaximumAngle', QgsAbstractGeometry.MaximumAngle),
                   ('最大差值', 'MaximumDifference', QgsAbstractGeometry.MaximumDifference)]


class QgsVectorRenderingOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgsvectorrenderingoptionsbase.ui'), self)
        self.setObjectName('mOptionsPageVectorRendering')
        settings = QgsSettings()

        hints = self.simplifyHints(settings.value('qgis/simplifyDrawingHints', 'NoSimplification'))
        self.mSimplifyDrawingGroupBox.setChecked(hints != QgsVectorSimplifyMethod.NoSimplification)
        self.mSimplifyDrawingSpinBox.setValue(
            settings.value('qgis/simplifyDrawingTol', 1.0, type=float))
        self.mSimplifyDrawingAtProvider.setChecked(
            not settings.value('qgis/simplifyLocal', True, type=bool))

        for label, name, value in TOLERANCE_TYPES:
            self.mToleranceTypeComboBox.addItem(label, value)
        toleranceType = self.toleranceType(settings.value('qgis/segmentationToleranceType', 'MaximumAngle'))
        index = self.mToleranceTypeComboBox.findData(toleranceType)
        if index != -1: self.mToleranceTypeComboBox.setCurrentIndex(index)
        tolerance = settings.value('qgis/segmentationTolerance', '0.01745', type=float)
        if toleranceType == QgsAbstractGeometry.MaximumAngle:
            tolerance = math.degrees(tolerance)  # shown in degrees, stored in radians
        self.mSegmentationToleranceSpinBox.setValue(tolerance)
        self.mSegmentationToleranceSpinBox.setClearValue(1.0)

        scales = Qgis.defaultProjectScales().split(',')
        scales.append('1:1')
        self.mSimplifyMaximumScaleComboBox.updateScales(scales)
        self.mSimplifyMaximumScaleComboBox.setScale(settings.value('qgis/simplifyMaxScale', 1.0, type=float))

        for label, name, value in ALGORITHMS:
            self.mSimplifyAlgorithmComboBox.addItem(label, value)
        self.mSimplifyAlgorithmComboBox.setCurrentIndex(max(0, self.mSimplifyAlgorithmComboBox.findData(
            self.simplifyAlgorithm(settings.value('qgis/simplifyAlgorithm', 'Distance')))))

    @staticmethod
    def simplifyHints(value):
        """Native stores the enum KEY NAMES, possibly several joined by '|'."""
        if isinstance(value, int):
            return value
        hints = QgsVectorSimplifyMethod.NoSimplification
        for name in [part.strip() for part in str(value).split('|') if part.strip()]:
            hints |= getattr(QgsVectorSimplifyMethod, name, QgsVectorSimplifyMethod.NoSimplification)
        return hints

    @staticmethod
    def simplifyAlgorithm(value):
        return value if isinstance(value, int) else getattr(
            QgsVectorSimplifyMethod, str(value), QgsVectorSimplifyMethod.Distance)

    @staticmethod
    def toleranceType(value):
        return value if isinstance(value, int) else getattr(
            QgsAbstractGeometry, str(value), QgsAbstractGeometry.MaximumAngle)

    def apply(self):
        settings = QgsSettings()
        hints = QgsVectorSimplifyMethod.NoSimplification
        if self.mSimplifyDrawingGroupBox.isChecked():
            hints |= QgsVectorSimplifyMethod.GeometrySimplification
            if self.mSimplifyDrawingSpinBox.value() > 1:
                hints |= QgsVectorSimplifyMethod.AntialiasingSimplification
        # Names are written explicitly: several enum values share the number 0, so
        # reverse lookups by value would be ambiguous.
        names = []
        if hints & QgsVectorSimplifyMethod.GeometrySimplification: names.append('GeometrySimplification')
        if hints & QgsVectorSimplifyMethod.AntialiasingSimplification: names.append('AntialiasingSimplification')
        settings.setValue('qgis/simplifyDrawingHints', '|'.join(names) or 'NoSimplification')
        settings.setValue('qgis/simplifyAlgorithm',
                          {value: name for _, name, value in ALGORITHMS}.get(
                              self.mSimplifyAlgorithmComboBox.currentData(), 'Distance'))
        settings.setValue('qgis/simplifyDrawingTol', self.mSimplifyDrawingSpinBox.value())
        settings.setValue('qgis/simplifyLocal', not self.mSimplifyDrawingAtProvider.isChecked())
        settings.setValue('qgis/simplifyMaxScale', self.mSimplifyMaximumScaleComboBox.scale())

        toleranceType = self.mToleranceTypeComboBox.currentData()
        settings.setValue('qgis/segmentationToleranceType',
                          {value: name for _, name, value in TOLERANCE_TYPES}.get(toleranceType, 'MaximumAngle'))
        tolerance = self.mSegmentationToleranceSpinBox.value()
        if toleranceType == QgsAbstractGeometry.MaximumAngle:
            tolerance = math.radians(tolerance)  # internal classes expect radians
        settings.setValue('qgis/segmentationTolerance', tolerance)
