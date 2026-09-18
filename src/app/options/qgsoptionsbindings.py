"""Literal bindings extracted by scripts/sync_options.py; special cases live in QgsOptions."""
from qgis.PyQt.QtGui import QColor

BINDINGS = [('leUserAgent', 'setText', 'qgis/networkAndProxy/userAgent', 'Mozilla/5.0'), ('mDefaultCapabilitiesExpirySpinBox', 'setValue', 'qgis/defaultCapabilitiesExpiry', 24), ('mDefaultTileExpirySpinBox', 'setValue', 'qgis/defaultTileExpiry', 24), ('mDefaultTileMaxRetrySpinBox', 'setValue', 'qgis/defaultTileMaxRetry', 3), ('grpProxy', 'setChecked', 'proxy/proxyEnabled', False), ('spinBoxAttrTableRowCache', 'setValue', 'qgis/attributeTableRowCache', 10000), ('mMessageTimeoutSpnBx', 'setValue', 'qgis/messageTimeout', 5), ('mNativeColorDialogsChkBx', 'setChecked', 'qgis/native_color_dialogs', False), ('cbxLegendClassifiers', 'setChecked', 'qgis/showLegendClassifiers', False), ('cbxHideSplash', 'setChecked', 'qgis/hideSplash', False), ('cbxAttributeTableDocked', 'setChecked', 'qgis/dockAttributeTable', False), ('cmbLegendDoubleClickAction', 'setCurrentIndex', 'qgis/legendDoubleClickAction', 0), ('mLegendSymbolMinimumSizeSpinBox', 'setValue', 'qgis/legendsymbolMinimumSize', 0.1), ('mLegendSymbolMaximumSizeSpinBox', 'setValue', 'qgis/legendsymbolMaximumSize', 20.0), ('mLegendGraphicResolutionSpinBox', 'setValue', 'qgis/defaultLegendGraphicResolution', 0), ('mLayerDeleteConfirmationChkBx', 'setChecked', 'qgis/askToDeleteLayers', True), ('reverseWheelZoom', 'setChecked', 'qgis/reverse_wheel_zoom', False)]
CORE_BINDINGS = [('mShowFeatureCountByDefaultCheckBox', 'setChecked', 'settingsLayerTreeShowFeatureCountForNewLayers'), ('mLineWidthSpinBox', 'setValue', 'settingsDigitizingLineWidth'), ('mLineColorToolButton', 'setColor', 'settingsDigitizingLineColor'), ('mFillColorToolButton', 'setColor', 'settingsDigitizingFillColor'), ('mLineGhostCheckBox', 'setChecked', 'settingsDigitizingLineGhost'), ('mDefaultZValueSpinBox', 'setValue', 'settingsDigitizingDefaultZValue'), ('mDefaultMValueSpinBox', 'setValue', 'settingsDigitizingDefaultMValue'), ('mSnappingEnabledDefault', 'setChecked', 'settingsDigitizingDefaultSnapEnabled'), ('mDefaultSnappingToleranceSpinBox', 'setValue', 'settingsDigitizingDefaultSnappingTolerance'), ('mSearchRadiusVertexEditSpinBox', 'setValue', 'settingsDigitizingSearchRadiusVertexEdit'), ('mSnappingMarkerColorButton', 'setColor', 'settingsDigitizingSnapColor'), ('mSnappingTooltipsCheckbox', 'setChecked', 'settingsDigitizingSnapTooltip'), ('mEnableSnappingOnInvisibleFeatureCheckbox', 'setChecked', 'settingsDigitizingSnapInvisibleFeature'), ('mMarkersOnlyForSelectedCheckBox', 'setChecked', 'settingsDigitizingMarkerOnlyForSelected'), ('mMarkerSizeSpinBox', 'setValue', 'settingsDigitizingMarkerSizeMm'), ('chkReuseLastValues', 'setChecked', 'settingsDigitizingReuseLastValues'), ('chkDisableAttributeValuesDlg', 'setChecked', 'settingsDigitizingDisableEnterAttributeValuesDialog'), ('mValidateGeometries', 'setCurrentIndex', 'settingsDigitizingValidateGeometries'), ('mOffsetQuadSegSpinBox', 'setValue', 'settingsDigitizingOffsetQuadSeg'), ('mCurveOffsetMiterLimitComboBox', 'setValue', 'settingsDigitizingOffsetMiterLimit'), ('mTracingConvertToCurveCheckBox', 'setChecked', 'settingsDigitizingConvertToCurve'), ('mTracingCustomAngleToleranceSpinBox', 'setValue', 'settingsDigitizingConvertToCurveAngleTolerance'), ('mTracingCustomDistanceToleranceSpinBox', 'setValue', 'settingsDigitizingConvertToCurveDistanceTolerance')]

# QgsSettingsRegistryCore is not exposed to Python (the binding only carries a
# generic stub), so native entries addressed through it silently failed and left
# whole pages disabled. These are the same entries addressed by the raw keys the
# registry writes: "<tree node>/<entry key>", taken from
# src/core/settings/qgssettingsregistrycore.cpp and src/core/settings/qgssettingstree.h.
ENTRY_BINDINGS = [
    # layer tree
    ('mShowFeatureCountByDefaultCheckBox', 'setChecked', 'core/layer-tree/show-feature-count-for-new-layers', False),
    # digitizing: geometry marking
    ('mLineWidthSpinBox', 'setValue', 'digitizing/line-width', 1),
    ('mLineColorToolButton', 'setColor', 'digitizing/line-color', QColor(255, 0, 0, 200)),
    ('mFillColorToolButton', 'setColor', 'digitizing/fill-color', QColor(255, 0, 0, 30)),
    ('mLineGhostCheckBox', 'setChecked', 'digitizing/line-ghost', False),
    # digitizing: defaults
    ('mDefaultZValueSpinBox', 'setValue', 'digitizing/default-z-value', 0.0),
    ('mDefaultMValueSpinBox', 'setValue', 'digitizing/default-m-value', 0.0),
    ('mSnappingEnabledDefault', 'setChecked', 'digitizing/default-snap-enabled', False),
    ('mDefaultSnappingToleranceSpinBox', 'setValue', 'digitizing/default-snapping-tolerance', 12.0),
    ('mSearchRadiusVertexEditSpinBox', 'setValue', 'digitizing/search-radius-vertex-edit', 10.0),
    # digitizing: snapping feedback
    ('mSnappingMarkerColorButton', 'setColor', 'digitizing/snap-color', QColor(255, 0, 255)),
    ('mSnappingTooltipsCheckbox', 'setChecked', 'digitizing/snap-tooltip', False),
    ('mEnableSnappingOnInvisibleFeatureCheckbox', 'setChecked', 'digitizing/snap-invisible-feature', False),
    ('mMarkersOnlyForSelectedCheckBox', 'setChecked', 'digitizing/marker-only-for-selected', True),
    ('mMarkerSizeSpinBox', 'setValue', 'digitizing/marker-size-mm', 2.0),
    # digitizing: attribute entry
    ('chkReuseLastValues', 'setChecked', 'digitizing/reuse-last-values', False),
    ('chkDisableAttributeValuesDlg', 'setChecked', 'digitizing/disable-enter-attribute-values-dialog', False),
    # digitizing: geometry validation is a combo, populated in initDigitizing
    ('mOffsetQuadSegSpinBox', 'setValue', 'digitizing/offset-quad-seg', 8),
    ('mCurveOffsetMiterLimitComboBox', 'setValue', 'digitizing/offset-miter-limit', 5.0),
    # digitizing: tracing curve conversion
    ('mTracingConvertToCurveCheckBox', 'setChecked', 'digitizing/convert-to-curve', False),
    ('mTracingCustomAngleToleranceSpinBox', 'setValue', 'digitizing/convert-to-curve-angle-tolerance', 1e-6),
    ('mTracingCustomDistanceToleranceSpinBox', 'setValue', 'digitizing/convert-to-curve-distance-tolerance', 1e-6),
]
