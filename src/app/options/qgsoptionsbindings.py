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

# ---------------------------------------------------------------------------
# Transcribed from src/app/options/qgsoptions.cpp (ctor 97-1318, saveOptions
# 1484-1927) via the audited control table. QgsSettings::Section prefixes are
# folded into the key strings: Core->core/, Gui->gui/, App->app/, Auth->auth/.
# ---------------------------------------------------------------------------

# (control, setter, key, default) - direct value bindings.
PLAIN_BINDINGS = [
    # General
    ('cbxCheckVersion', 'setChecked', 'qgis/checkVersion', True),
    ('cbxProjectDefaultNew', 'setChecked', 'qgis/newProjectDefault', False),
    ('chbAskToSaveProjectChanges', 'setChecked', 'qgis/askToSaveProjectChanges', True),
    ('chbWarnOldProjectVersion', 'setChecked', 'qgis/warnOldProjectVersion', True),
    ('leTemplateFolder', 'setText', 'qgis/projectTemplateDir', ''),
    ('mProjectOnLaunchLineEdit', 'setText', 'qgis/projOpenAtLaunchPath', ''),
    # System
    ('mCustomVariablesChkBx', 'setChecked', 'qgis/customEnvVarsUse', False),
    # CRS and transforms
    ('mCrsAccuracyIndicatorCheck', 'setChecked', 'app/projections/crsAccuracyIndicator', False),
    ('mCrsAccuracySpin', 'setValue', 'app/projections/crsAccuracyWarningThreshold', 0.0),
    ('mPlanimetricMeasurementsComboBox', 'setChecked', 'core/measure/planimetric', False),
    ('mShowDatumTransformDialogCheckBox', 'setChecked', 'app/projections/promptWhenMultipleTransformsExist', False),
    # Data sources
    ('mCheckMonitorDirectories', 'setChecked', 'qgis/monitorDirectoriesInBrowser', True),
    # Canvas and legend
    ('mRespectScreenDpiCheckBox', 'setChecked', 'gui/respect-screen-dpi', False),
    # Map tools
    ('mAlwaysUseDecimalPoint', 'setChecked', 'measure/clipboard-use-decimal-point', False),
    ('mIncludeHeader', 'setChecked', 'measure/clipboard-header', False),
    # Layouts
    ('mGridResolutionSpinBox', 'setValue', 'gui/LayoutDesigner/defaultSnapGridResolution', 10.0),
    ('mOffsetXSpinBox', 'setValue', 'gui/LayoutDesigner/defaultSnapGridOffsetX', 0.0),
    ('mOffsetYSpinBox', 'setValue', 'gui/LayoutDesigner/defaultSnapGridOffsetY', 0.0),
    ('mSnapToleranceSpinBox', 'setValue', 'gui/LayoutDesigner/defaultSnapTolerancePixels', 5),
    # Acceleration / auth
    ('mGPUEnableCheckBox', 'setChecked', 'core/OpenClEnabled', False),
    ('mAutoClearAccessCache', 'setChecked', 'auth/clear_auth_cache_on_errors', True),
    # Digitizing extras
    ('mMarkerSizeSpinBox', 'setValue', 'digitizing/marker-size-mm', 2.0),
]

# (control, key, default, [(label, data)]) - combos storing currentData().
COMBO_BINDINGS = [
    ('mProjectOnLaunchCmbBx', 'qgis/projOpenAtLaunch', 0,
     [('欢迎页', 0), ('最近工程', 1), ('指定工程', 2), ('新建空白工程', 3)]),
    ('mDefaultPathsComboBox', 'qgis/defaultProjectPathsRelative', True,
     [('相对路径', True), ('绝对路径', False)]),
    ('cmbStyle', 'qgis/style', '',
     [(name, name) for name in ('windowsvista', 'Windows', 'Fusion')]),
    ('cmbUITheme', 'UI/UITheme', 'default', [('default', 'default')]),
    ('mEnableMacrosComboBox', 'qgis/enableMacros', 'Ask',
     [('从不', 'Never'), ('询问', 'Ask'), ('仅签名时', 'OnlyWhenSigned'), ('始终', 'Always')]),
    ('mAttrTableViewComboBox', 'qgis/attributeTableView', -1,
     [('记住上次视图', -1), ('表格视图', 0), ('表单视图', 1)]),
    ('cmbAttrTableBehavior', 'qgis/attributeTableBehavior', 0,
     [('显示所有要素', 0), ('显示选中要素', 1), ('显示可见要素', 2)]),
    ('cmbPromptSublayers', 'qgis/promptForSublayers', 0,
     [('始终询问', 0), ('询问，但不含栅格波段', 1), ('从不询问，跳过', 2), ('从不询问，全部加载', 3)]),
    ('mComboCopyFeatureFormat', 'qgis/copyFeatureFormat', 1,
     [('仅属性', 0), ('属性与 WKT', 1), ('GeoJSON', 2)]),
    ('mLayerTreeInsertionMethod', 'qgis/layerTreeInsertionMethod', 0,
     [('插入点之上', 0), ('图层树顶部', 1), ('插入组内最佳位置', 2)]),
    ('mSnappingMainDialogComboBox', 'qgis/mainSnappingWidgetMode', 'dialog',
     [('对话框', 'dialog'), ('停靠面板', 'dock')]),
    ('mDistanceUnitsComboBox', 'qgis/measure/displayunits', 'Meters',
     [(n, n) for n in ('Meters', 'Kilometers', 'Feet', 'Yards', 'Miles', 'NauticalMiles', 'Centimeters', 'Millimeters')]),
    ('mAreaUnitsComboBox', 'qgis/measure/areaunits', 'SquareMeters',
     [(n, n) for n in ('SquareMeters', 'SquareKilometers', 'SquareFeet', 'SquareYards', 'SquareMiles', 'Hectares', 'Acres', 'SquareNauticalMiles')]),
    ('mAngleUnitsComboBox', 'qgis/measure/angleunits', 'Degrees',
     [(n, n) for n in ('Degrees', 'Radians', 'Gon', 'MinutesOfArc', 'SecondsOfArc', 'Turns')]),
    ('mMarkerStyleComboBox', 'digitizing/marker-style', 'Cross',
     [('半透明圆', 'SemiTransparentCircle'), ('十字', 'Cross'), ('无', 'None')]),
    ('mOffsetJoinStyleComboBox', 'digitizing/offset-join-style', 0,
     [('圆角', 0), ('斜接', 1), ('斜切', 2)]),
    ('mOffsetCapStyleComboBox', 'digitizing/offset-cap-style', 0,
     [('圆头', 0), ('平头', 1), ('方头', 2)]),
]

# (control, prefix) - QColor stored as four integer components.
COLOR_BINDINGS = [
    ('mIdentifyHighlightColorButton', 'Map/highlight/color'),
    ('mGridColorButton', 'gui/LayoutDesigner/grid'),
]
