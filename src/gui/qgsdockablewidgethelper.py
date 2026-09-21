"""Port of the unbound QgsDockableWidgetHelper docking contract."""
from qgis.PyQt.QtCore import Qt, QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QToolButton, QAction, QWidget
from qgis.gui import QgsDockWidget
from qgis.core import QgsApplication, QgsSettings


class QgsDockableWidgetHelper(QObject):
    closed = pyqtSignal()
    dockModeToggled = pyqtSignal(bool)
    visibilityChanged = pyqtSignal(bool)

    def __init__(self, isDocked, windowTitle, widget, ownerWindow, defaultDockArea=Qt.BottomDockWidgetArea,
                 tabifyWith=None, raiseTab=False, windowGeometrySettingsKey='', usePersistentWidget=True):
        super().__init__(ownerWindow)
        self.mWidget, self.mOwnerWindow = widget, ownerWindow
        self.mWindowTitle = windowTitle
        self.mDockArea = defaultDockArea
        self.mObjectName = widget.objectName() + 'Dock'
        self.mDock, self.mDialog = None, None
        self.mIsDocked = None
        self.mKey = windowGeometrySettingsKey or self.mObjectName
        self.mAction = QAction('停靠/取消停靠', widget)
        self.mAction.setIcon(QgsApplication.getThemeIcon('/mDockify.svg'))
        self.mAction.setCheckable(True)
        self.mAction.toggled.connect(self.toggleDockMode)
        self.toggleDockMode(isDocked)

    def widget(self): return self.mWidget
    def dockWidget(self): return self.mDock
    def dialog(self): return self.mDialog
    def isUserVisible(self):
        host = self.mDock if self.mIsDocked else self.mDialog
        return bool(host and host.isVisible())
    def setWindowTitle(self, title):
        self.mWindowTitle = title
        host = self.mDock if self.mIsDocked else self.mDialog
        if host: host.setWindowTitle(title)
    def setDockObjectName(self, name):
        self.mObjectName = name
        if self.mDock: self.mDock.setObjectName(name)
    def createDockUndockAction(self, title, parent):
        self.mAction.setText(title)
        return self.mAction
    def createDockUndockToolButton(self):
        button = QToolButton(self.mWidget)
        button.setDefaultAction(self.mAction)
        return button
    def setUserVisible(self, visible):
        host = self.mDock if self.mIsDocked else self.mDialog
        if not visible and self.mDialog and self.mDialog.isVisible():
            QgsSettings().setValue(self.mKey + '/geometry', self.mDialog.saveGeometry())
        host.setVisible(visible)
        if visible:
            QWidget.show(self.mWidget)
            host.raise_()
        self.visibilityChanged.emit(visible)

    def toggleDockMode(self, docked):
        if self.mIsDocked == docked: return
        old = self.mDock if self.mIsDocked else self.mDialog
        if self.mDialog: QgsSettings().setValue(self.mKey + '/geometry', self.mDialog.saveGeometry())
        self.mWidget.setParent(self.mOwnerWindow)
        if old:
            old.hide()
            if self.mDock:
                self.mOwnerWindow.mPanelMenu.removeAction(old.toggleViewAction())
                self.mOwnerWindow.removeDockWidget(old)
            old.deleteLater()
        self.mDock, self.mDialog = None, None
        self.mIsDocked = docked
        self.mWidget.setWindowFlags(Qt.Widget)
        if docked:
            self.mDock = QgsDockWidget(self.mWindowTitle, self.mOwnerWindow)
            self.mDock.setObjectName(self.mObjectName)
            self.mDock.setWidget(self.mWidget)
            self.mOwnerWindow.addDockWidget(self.mDockArea, self.mDock)
            self.mOwnerWindow.mPanelMenu.addAction(self.mDock.toggleViewAction())
            self.mDock.visibilityChanged.connect(self.visibilityChanged)
        else:
            self.mDialog = QDialog(self.mOwnerWindow, Qt.Window)
            self.mDialog.setObjectName(self.mObjectName + 'Window')
            self.mDialog.setWindowTitle(self.mWindowTitle)
            layout = QVBoxLayout(self.mDialog)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.mWidget)
            self.mDialog.resize(1000, 580)
            stored = QgsSettings().value(self.mKey + '/geometry', b'')
            if stored: self.mDialog.restoreGeometry(stored)
            self.mDialog.finished.connect(lambda _: self.visibilityChanged.emit(False))
        self.mAction.blockSignals(True)
        self.mAction.setChecked(docked)
        self.mAction.blockSignals(False)
        QgsSettings().setValue(self.mKey + '/docked', docked)
        # Native QgsDockableWidgetHelper::toggleDockMode() ends the dock branch with
        # mDock->setUserVisible(true): a freshly created dock is visible, which the
        # caller may then hide. Treating "was the previous host visible" as the new
        # visibility left every docked widget hidden on first creation.
        if docked:
            self.mDock.setUserVisible(True)
            self.visibilityChanged.emit(True)
        self.dockModeToggled.emit(docked)

    def dispose(self):
        self.mWidget.setParent(self.mOwnerWindow)
        host = self.mDock if self.mIsDocked else self.mDialog
        if self.mDock:
            self.mOwnerWindow.mPanelMenu.removeAction(self.mDock.toggleViewAction())
            self.mOwnerWindow.removeDockWidget(self.mDock)
        if host: host.deleteLater()
        self.mDock, self.mDialog = None, None
