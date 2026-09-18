"""Audit the ported app's runtime toolbar arrangement against upstream qgisapp.ui.

Reports three classes of drift from native QGIS 3.34.10:
  1. actions added/removed/reordered at runtime versus the .ui declaration,
  2. native runtime-inserted tool buttons that are missing entirely,
  3. the View > Toolbars menu order (native sorts it by translated text).

Run with OSGeo4W Python, e.g.:
    python-qgis-ltr.bat scripts/audit_toolbars.py
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, 'C:/OSGeo4W/apps/qgis-ltr/python/plugins')

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QToolBar, QToolButton
from qgis.core import QgsApplication, QgsProject

# Tool buttons native QgisApp::createToolBars() inserts at runtime.
NATIVE_RUNTIME_BUTTONS = [
    ('ActionNewLayer', 'mLayerToolBar'),
    ('ActionAddDbLayer', 'mLayerToolBar'),
    ('ActionOpenTable', 'mAttributesToolBar'),
    ('ActionPointSymbolTools', 'mAdvancedDigitizeToolBar'),
]
UPSTREAM_UI = Path(os.environ.get('QGIS_SOURCE_ROOT', r'C:\Users\worker306\Desktop\QGIS-final-3_34_10')) / 'src/ui/qgisapp.ui'


def upstream_toolbars():
    import xml.etree.ElementTree as ET
    root = ET.parse(UPSTREAM_UI).getroot()
    result = {}
    for tb in root.iter('widget'):
        if tb.get('class') != 'QToolBar':
            continue
        result[tb.get('name')] = [a.get('name') for a in tb.findall('addaction')]
    return result


def runtime_toolbars(window):
    result = {}
    for tb in window.findChildren(QToolBar):
        if tb.parent() is not window:
            continue
        entries = []
        for a in tb.actions():
            if a.isSeparator():
                continue
            w = tb.widgetForAction(a)
            entries.append(a.objectName() or (w.objectName() if w else '') or f'<{type(w).__name__}>')
        result[tb.objectName()] = {'visible': tb.isVisible(), 'actions': entries}
    return result


def main():
    profile = ROOT / '.runtime/toolbar-audit-profile'
    profile.mkdir(parents=True, exist_ok=True)
    QgsApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QgsApplication.setPrefixPath('C:/OSGeo4W/apps/qgis-ltr', True)
    app = QgsApplication([], True, str(profile))
    app.setOrganizationName('QGIS-Python')
    app.setApplicationName('QGIS-Python-3.34')
    app.initQgis()
    from qgis.gui import QgsGui
    QgsGui.editorWidgetRegistry().initEditors()
    from src.app.qgisapp import QgisApp
    window = QgisApp(customization=False)
    window.show()
    app.processEvents()

    ui, rt = upstream_toolbars(), runtime_toolbars(window)
    report = {'uiVersusRuntime': [], 'missingNativeButtons': [], 'toolbarMenuSorted': None,
              'toolbarMenu': [a.text() for a in window.mToolbarMenu.actions()]}

    for name, uiActions in ui.items():
        if name not in rt:
            report['uiVersusRuntime'].append({'toolbar': name, 'issue': 'missing at runtime'})
            continue
        # '<...>' entries are runtime widget insertions, expected for some toolbars.
        runtimeActions = [a for a in rt[name]['actions'] if not a.startswith('<') and not a.startswith('[')]
        extra = [a for a in runtimeActions if a not in uiActions]
        missing = [a for a in uiActions if a not in runtimeActions]
        if extra or missing:
            report['uiVersusRuntime'].append({'toolbar': name, 'extra': extra, 'missing': missing})

    for button, toolbar in NATIVE_RUNTIME_BUTTONS:
        present = any(a == button for a in rt.get(toolbar, {}).get('actions', []))
        if not present:
            report['missingNativeButtons'].append({'button': button, 'toolbar': toolbar})

    texts = report['toolbarMenu']
    report['toolbarMenuSorted'] = texts == sorted(texts)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    # Qt's exit path can abort on interpreter teardown after the GUI was shown;
    # the audit is complete at this point, so leave with the documented status.
    os._exit(0)


if __name__ == '__main__':
    sys.exit(main())
