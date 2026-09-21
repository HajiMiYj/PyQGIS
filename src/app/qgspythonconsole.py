"""Python console dock, mirroring python/console/console.py's PythonConsole.

Upstream's PythonConsole derives from the C++ QgsCodeEditorDockWidget. That base
class docks itself through QgsDockableWidgetHelper, whose console path calls
QgsDockableWidgetHelper::sAddTabifiedDockWidgetFunction - a std::function static
that PyQt cannot set - so in a Python process the helper never adds the dock to
the main window. A dock that is not part of the main window's dock layout is
invisible to QMainWindow::saveState()/restoreState(), which is why the console
panel never came back after a restart.

This class keeps the identical contract (dockToggleButton, isUserVisible,
setUserVisible, activate, settings save on exit) on top of the ported
QgsDockableWidgetHelper, so the console is a real, remembered dock.
"""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget
from qgis.core import QgsApplication
from qgis.gui import QgsGui

from src.gui.qgsdockablewidgethelper import QgsDockableWidgetHelper


class PythonConsoleDock(QWidget):
    """Console host widget; the helper owns the dock the main window knows about.

    Mirrors QgsCodeEditorDockWidget, which is a plain QWidget (not a QDockWidget):
    the helper wraps it in the dock that joins the main window layout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        title = QCoreApplication.translate('PythonConsole', 'Python Console')
        self.setObjectName('PythonConsole')
        self.setWindowTitle(title)
        # The helper wraps this dock in the dock the main window owns, exactly like
        # the C++ base class does; it must exist before the console asks for its
        # dock/undock button.
        self.mDockableWidgetHelper = QgsDockableWidgetHelper(
            True, title, self, parent, Qt.BottomDockWidgetArea, [], False,
            'PythonConsoleWindow', True)
        self.mDockableWidgetHelper.setDockObjectName('PythonConsole')
        from console.console import PythonConsoleWidget
        self.console = PythonConsoleWidget(self)
        QgsGui.instance().optionsChanged.connect(self.console.updateSettings)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.console)
        self.setFocusProxy(self.console)
        QgsApplication.instance().aboutToQuit.connect(self.onAppExit)

    # --- contract required by console.PythonConsoleWidget ---------------------
    def dockToggleButton(self):
        return self.mDockableWidgetHelper.createDockUndockToolButton()

    def isUserVisible(self):
        return self.mDockableWidgetHelper.isUserVisible()

    def setUserVisible(self, visible):
        self.mDockableWidgetHelper.setUserVisible(visible)

    def activate(self):
        self.activateWindow()
        self.raise_()
        self.setFocus()

    def visibilityChangedConnect(self, slot):
        self.mDockableWidgetHelper.visibilityChanged.connect(slot)

    def onAppExit(self):
        self.console.saveSettingsConsole()

    def closeEvent(self, event):
        # console.saveSettingsConsole() + hide(), like the console's own closeEvent.
        self.console.saveSettingsConsole()
        self.hide()
        event.ignore()