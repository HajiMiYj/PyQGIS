"""Exercise every Options control: click every action button, cycle every combo.

Modal dialogs are stubbed so the whole dialog can be driven headlessly; any
handler that raises is reported, which is how unwired or wrong-API slots show up.
"""
import os
import sys
from pathlib import Path

# PyQt5 aborts the process on an unhandled exception raised inside a slot unless a
# custom excepthook is installed; record them so the sweep can continue.
slotErrors = []
sys.excepthook = lambda kind, value, tb: slotErrors.append(repr(value))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(r'C:\Users\worker306\Documents\ChatGPT\qgis_python')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, 'C:/OSGeo4W/apps/qgis-ltr/python/plugins')

from qgis.PyQt.QtWidgets import (QFileDialog, QInputDialog, QMessageBox, QDialog,
                                 QToolButton, QPushButton, QComboBox, QAbstractButton)
from qgis.core import QgsApplication

# Stub every modal entry point the options dialog uses.
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: '')
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ('', ''))
QInputDialog.getText = staticmethod(lambda *a, **k: ('', False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
QMessageBox.critical = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
QDialog.exec_ = lambda self: QDialog.Rejected

profile = ROOT / '.runtime' / 'opt-func'
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

failures = []
clicked = 0
for name, widget in sorted(dialog.mFormControls.items()):
    if name not in dialog.mImplementedControls:
        continue
    if not isinstance(widget, (QToolButton, QPushButton)):
        continue
    if widget.menu() is not None:  # menu buttons: fire each menu action instead
        for action in widget.menu().actions():
            if action.isSeparator():
                continue
            try:
                action.trigger()
                clicked += 1
            except Exception as exc:
                failures.append((name + '::' + (action.text() or '?'), repr(exc)))
        continue
    if not widget.isEnabled():
        continue
    try:
        widget.click()
        clicked += 1
    except Exception as exc:
        failures.append((name, repr(exc)))

cycled = 0
for name, widget in sorted(dialog.mFormControls.items()):
    if name not in dialog.mImplementedControls or not isinstance(widget, QComboBox):
        continue
    for index in range(widget.count()):
        try:
            widget.setCurrentIndex(index)
            cycled += 1
        except Exception as exc:
            failures.append((name + '#%d' % index, repr(exc)))

toggled = 0
for name, widget in sorted(dialog.mFormControls.items()):
    if name not in dialog.mImplementedControls or not isinstance(widget, QAbstractButton):
        continue
    if isinstance(widget, (QToolButton, QPushButton)):
        continue
    try:
        widget.setChecked(not widget.isChecked())
        toggled += 1
    except Exception as exc:
        failures.append((name, repr(exc)))

try:
    dialog.saveOptions()
    saved = 'OK'
except Exception as exc:
    saved = repr(exc)

print('controls exercised : buttons={} combos={} toggles={}'.format(clicked, cycled, toggled))
print('saveOptions        :', saved)
print('slot errors        :', len(slotErrors))
for error in slotErrors:
    print('   ', error)
print('failures           :', len(failures))
for name, error in failures:
    print('   {:<46} {}'.format(name, error))
sys.stdout.flush()
os._exit(0)
