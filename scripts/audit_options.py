"""Audit the ported Options dialog: per-page health and control wiring gaps."""
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(r'C:\Users\worker306\Documents\ChatGPT\qgis_python')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, 'C:/OSGeo4W/apps/qgis-ltr/python/plugins')

from qgis.core import QgsApplication
profile = ROOT / '.runtime' / 'opt-audit'
profile.mkdir(parents=True, exist_ok=True)
QgsApplication.setPrefixPath('C:/OSGeo4W/apps/qgis-ltr', True)
app = QgsApplication([], True, str(profile))
app.setOrganizationName('QGIS-Python')
app.setApplicationName('QGIS-Python-3.34')
app.initQgis()
from qgis.gui import QgsGui
QgsGui.editorWidgetRegistry().initEditors()
from src.app.qgisapp import QgisApp
window = QgisApp(customization=False)
from src.app.options.qgsoptions import QgsOptions
dialog = QgsOptions(window, '')

stack = dialog.mOptionsStackedWidget
print('pages in stack     :', stack.count())
print('enabled controls   :', len(dialog.mImplementedControls))
print('form controls      :', len(dialog.mFormControls))
print('bound via mBindings:', len(dialog.mBindings))
print('bound via core     :', len(dialog.mCoreBindings))
print('bound via colors   :', len(getattr(dialog, 'mExtraColorBindings', [])))
print()

# Which enabled controls are recorded as bound anywhere?
bound = set()
for key, widget, getter in dialog.mBindings:
    for name, formWidget in dialog.mFormControls.items():
        if formWidget is widget:
            bound.add(name)
special = {
    'cbxShowNews', 'mFileFormatQgsButton', 'mFileFormatQgzButton', 'mListPluginPaths', 'mListSVGPaths',
    'mListComposerTemplatePaths', 'mLocalizedDataPathListWidget', 'mListHiddenBrowserPaths',
    'mHelpPathTreeWidget', 'cboTranslation', 'cboGlobalLocale', 'mFontFamilyComboBox',
    'mFontFamilyRadioCustom', 'mFontFamilyRadioQt', 'spinFontSize', 'mCustomVariablesTable',
    'mCurrentVariablesTable', 'mCurrentVariablesQGISChxBx', 'mColorSchemesComboBox', 'mTreeCustomColors',
    'lstRasterDrivers', 'lstVectorDrivers', 'cmbEditCreateOptions', 'mSeparatorOther', 'mSeparatorCustom',
    'mOpenClDevicesCombo', 'leProjectGlobalCrs', 'leLayerGlobalCrs', 'mProxyTypeComboBox',
    'mNetworkTimeoutSpinBox', 'mAuthSettings', 'mAuthConfigsGrpBx', 'mDefaultDatumTransformTableWidget',
    'mVariableEditor', 'mNoProxyUrlListWidget', 'mCacheDirectory', 'leProxyHost', 'leProxyPort',
    'leUserAgent', 'grpProxy', 'mCacheSize', 'mProxyTypeComboBox', 'mLocatorOptionsWidget',
    'mTreeCustomColors', 'mCustomVariablesChkBx', 'mPlanimetricMeasurementsComboBox',
    'radCrsNoAction', 'radPromptForProjection', 'radUseProjectProjection', 'radUseGlobalProjection',
    'radProjectUseCrsOfFirstLayer', 'radProjectUseDefaultCrs',
}
for name, prefix in getattr(dialog, 'mExtraColorBindings', []):
    bound.add(name)
unwired = sorted(set(dialog.mImplementedControls) - bound - special)
print('=== enabled but not recorded as saved ({}): ==='.format(len(unwired)))
for name in unwired:
    widget = dialog.mFormControls.get(name) or getattr(dialog, name, None)
    print('   {:42} {}'.format(name, type(widget).__name__ if widget is not None else '?'))
print()

# Walk every page, forcing the lazy GDAL/colour paths, and catch errors.
print('=== per-page walk ===')
failed = []
for index in range(stack.count()):
    stack.setCurrentIndex(index)
    app.processEvents()
    page = stack.widget(index)
    try:
        tree = dialog.mOptionsTreeView
        title = page.objectName() if page is not None else '?'
        print('   [{:2}] {:<40} {}'.format(index, title, type(page).__name__ if page is not None else '?'))
    except Exception as exc:  # pragma: no cover - diagnostic
        failed.append((index, repr(exc)))
print()
print('page errors:', failed or 'none')
sys.stdout.flush()
os._exit(0)
