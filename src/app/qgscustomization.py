"""Interface customization using QGIS object paths and its original form.

Like the C++ implementation, Apply saves the configuration for next startup.
Widget capture only changes the draft tree; it never executes the clicked action.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
from qgis.PyQt import sip, uic
from qgis.PyQt.QtCore import QObject, QEvent, Qt, QSettings, QTimer
from qgis.PyQt.QtWidgets import (QApplication, QMainWindow, QDialog, QDialogButtonBox,
    QTreeWidgetItem, QToolBar, QDockWidget, QWidget, QToolButton, QWidgetAction,
    QMenu, QFileDialog, QMessageBox, QRubberBand)
from qgis.core import QgsApplication
from qgis.gui import QgsGui, QgsHelp


ROOT = Path(__file__).resolve().parents[2]
INTERNAL_WIDGETS = {'qt_tabwidget_stackedwidget', 'qt_tabwidget_tabbar'}


class QgsCustomization(QObject):
    def __init__(self, app, settings=None, enabled=None):
        super().__init__(app)
        self.mApp = app
        self.mSettings = settings if settings is not None else app.mSettings
        self.mEnabled = self.mSettings.value('UI/Customization/enabled', False, type=bool) if enabled is None else enabled
        self.pDialog = None
        self.mEntries = {}
        self.mLabels = {}
        self.mHiddenWidgets = []
        self.collectMainWindow()
        QApplication.instance().installEventFilter(self)

    def addEntry(self, path, label='', kind=None, target=None, owner=None):
        path = path.strip('/')
        if any('gps' in part.lower() or 'gpx' in part.lower() for part in path.split('/')): return
        self.mLabels[path] = (label or path.rsplit('/', 1)[-1]).replace('&', '')
        if kind: self.mEntries[path] = (kind, target, owner)

    def collectActions(self, prefix, owner, actions):
        for action in actions:
            if action.isSeparator(): continue
            menu = action.menu()
            name = menu.objectName() if menu else action.objectName()
            if not name: continue
            path = prefix + '/' + name
            self.addEntry(path, action.text(), 'action', action, owner)
            if menu: self.collectActions(path, menu, menu.actions())
            elif isinstance(action, QWidgetAction) and action.defaultWidget():
                widget = action.defaultWidget()
                self.collectActions(path, widget, widget.actions())
                if isinstance(widget, QToolButton) and widget.menu():
                    self.collectActions(path, widget.menu(), widget.menu().actions())

    def collectMainWindow(self):
        for key, label in [('Menus', '菜单'), ('Toolbars', '工具栏'), ('Docks', '面板'),
                           ('StatusBar', '状态栏'), ('Browser', '浏览器'), ('Widgets', '对话框控件')]:
            self.addEntry(key, label)
        self.collectActions('Menus', self.mApp.menuBar(), self.mApp.menuBar().actions())
        for toolbar in self.mApp.findChildren(QToolBar, options=Qt.FindDirectChildrenOnly):
            if not toolbar.objectName(): continue
            path = 'Toolbars/' + toolbar.objectName()
            self.addEntry(path, toolbar.windowTitle(), 'widget', toolbar)
            self.collectActions(path, toolbar, toolbar.actions())
        for dock in self.mApp.findChildren(QDockWidget, options=Qt.FindDirectChildrenOnly):
            if dock.objectName(): self.addEntry('Docks/' + dock.objectName(), dock.windowTitle(), 'widget', dock)
        status = self.mApp.statusBar()
        self.addEntry('StatusBar', '状态栏', 'widget', status)
        for child in status.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if child.objectName() and not child.objectName().startswith('qt_'):
                self.addEntry('StatusBar/' + child.objectName(), child.toolTip(), 'widget', child)
        for key, label in [('special:Home', '用户目录'), ('special:ProjectHome', '工程目录'),
                           ('special:Favorites', '收藏夹'), ('special:Drives', '驱动器'), ('special:Volumes', '卷')]:
            self.addEntry('Browser/' + key, label)
        for provider in QgsApplication.dataItemProviderRegistry().providers():
            if provider.capabilities(): self.addEntry('Browser/' + provider.name(), provider.name())
        source = ROOT / 'resources/customization.xml'
        if source.exists():
            def visit(element, parent):
                name = element.get('objectName', '')
                if not name or 'gps' in name.lower() or 'gpx' in name.lower() or name == 'QgsCustomizationDialogBase': return
                path = parent + '/' + name
                self.addEntry(path, element.get('label', name))
                for child in element: visit(child, path)
            for element in ET.parse(source).getroot(): visit(element, 'Widgets')

    def allowed(self, path):
        if not self.mEnabled: return True
        parts = path.strip('/').split('/')
        return all(self.mSettings.value('Customization/' + '/'.join(parts[:i]), True, type=bool)
                   for i in range(1, len(parts) + 1))

    def updateMainWindow(self):
        if not self.mEnabled: return
        for path, (kind, target, owner) in self.mEntries.items():
            if sip.isdeleted(target) or self.allowed(path): continue
            if kind == 'action':
                if not sip.isdeleted(owner): owner.removeAction(target)
            elif kind == 'widget':
                target.hide()
                self.mHiddenWidgets.append(target)
                if isinstance(target, (QToolBar, QDockWidget)): target.toggleViewAction().setVisible(False)
        for path, (kind, action, owner) in self.mEntries.items():
            if kind != 'action' or not isinstance(action, QWidgetAction) or sip.isdeleted(action): continue
            widget = action.defaultWidget()
            if not isinstance(widget, QToolButton) or not widget.menu(): continue
            choices = [entry for entry in widget.menu().actions() if not entry.isSeparator() and entry.isVisible()]
            if widget.defaultAction() not in choices:
                if choices: widget.setDefaultAction(choices[0])
                else:
                    widget.hide()
                    self.mHiddenWidgets.append(widget)
        self.updateBrowserWidget(self.mApp.mBrowserWidget)

    def updateBrowserWidget(self, widget):
        disabled = ['gpx']
        disabled.extend(path.split('/', 1)[1] for path in self.mLabels
                        if path.startswith('Browser/') and not self.allowed(path))
        widget.setDisabledDataItemsKeys(list(dict.fromkeys(disabled)))

    def openDialog(self):
        if self.pDialog is None:
            self.pDialog = QgsCustomizationDialog(self.mApp, self)
        elif not self.pDialog.isVisible(): self.pDialog.reset()
        self.pDialog.show()
        self.pDialog.raise_()
        self.pDialog.activateWindow()
        return self.pDialog

    def toggleCatch(self):
        if self.pDialog is not None and self.pDialog.isVisible():
            self.pDialog.setCatch(not self.pDialog.catchOn())

    @staticmethod
    def widgetPath(widget):
        parts = []
        current = widget
        while current is not None:
            name = current.objectName()
            if name and name not in INTERNAL_WIDGETS: parts.insert(0, name)
            if isinstance(current, QDialog): return 'Widgets/' + '/'.join(parts)
            current = current.parentWidget()
        return ''

    def customizeWidget(self, dialog):
        def visit(widget):
            for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                path = self.widgetPath(child)
                if path and not self.allowed(path): child.hide()
                else: visit(child)
        visit(dialog)

    def eventFilter(self, receiver, event):
        if self.mApp.mShutdown: return False
        dialog = self.pDialog
        if dialog and dialog.isVisible() and event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress):
            if event.key() == Qt.Key_M and event.modifiers() == Qt.ControlModifier:
                if event.type() == QEvent.ShortcutOverride: event.accept()
                elif not event.isAutoRepeat(): self.toggleCatch()
                return True
        if dialog and (receiver is dialog or isinstance(receiver, QWidget) and dialog.isAncestorOf(receiver)):
            return False
        if event.type() == QEvent.MouseButtonPress and isinstance(receiver, QWidget):
            if dialog and dialog.isVisible() and dialog.catchOn():
                return dialog.switchWidget(receiver, event)
        if event.type() in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            if dialog and dialog.isVisible() and dialog.catchOn(): return True
        if self.mEnabled and event.type() == QEvent.Show and isinstance(receiver, QWidget):
            if receiver in self.mHiddenWidgets: receiver.hide()
            elif isinstance(receiver, QDialog): self.customizeWidget(receiver)
            else:
                path = self.widgetPath(receiver)
                if path and not self.allowed(path): receiver.hide()
        return False

    def shutdown(self):
        QApplication.instance().removeEventFilter(self)
        if self.pDialog is not None: self.pDialog.hide()


class QgsCustomizationDialog(QMainWindow):
    def __init__(self, parent, customization):
        super().__init__(parent, Qt.Window)
        self.mCustomization = customization
        self.mSettings = customization.mSettings
        self.mItems = {}
        self.mCatchBand = None
        uic.loadUi(str(ROOT / 'src/ui/qgscustomizationdialogbase.ui'), self)
        QgsGui.enableAutoGeometryRestore(self)
        self.treeWidget.setHeaderLabels(['对象名称', '名称'])
        self.mLeFilter.setShowSearchIcon(True)
        for path, label in customization.mLabels.items(): self.addItem(path, label)
        self.treeWidget.sortItems(0, Qt.AscendingOrder)
        for i in range(self.treeWidget.topLevelItemCount()): self.treeWidget.topLevelItem(i).setExpanded(True)
        self.treeWidget.resizeColumnToContents(0)
        self.mCustomizationEnabledCheckBox.toggled.connect(self.enableCustomization)
        self.mLeFilter.textChanged.connect(self.filterItems)
        self.actionExpandAll.triggered.connect(self.treeWidget.expandAll)
        self.actionCollapseAll.triggered.connect(self.treeWidget.collapseAll)
        self.actionSelectAll.triggered.connect(self.actionSelectAll_triggered)
        self.actionSave.triggered.connect(self.actionSave_triggered)
        self.actionLoad.triggered.connect(self.actionLoad_triggered)
        for button, callback in [(QDialogButtonBox.Ok, self.ok), (QDialogButtonBox.Apply, self.apply),
                                 (QDialogButtonBox.Cancel, self.cancel), (QDialogButtonBox.Reset, self.reset),
                                 (QDialogButtonBox.Help, self.showHelp)]:
            self.buttonBox.button(button).clicked.connect(callback)
        self.reset()

    def addItem(self, path, label=''):
        if path in self.mItems: return self.mItems[path]
        parentPath, _, name = path.rpartition('/')
        parent = self.addItem(parentPath) if parentPath else self.treeWidget
        item = QTreeWidgetItem(parent, [name or path, label])
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)
        self.mItems[path] = item
        return item

    def item(self, path): return self.mItems.get(path.strip('/'))
    def itemChecked(self, path):
        item = self.item(path)
        return item is not None and item.checkState(0) == Qt.Checked
    def setItemChecked(self, path, checked):
        item = self.item(path)
        if item: item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def settingsToTree(self, settings):
        for key in settings.allKeys():
            if key.startswith('Customization/Widgets/') and not any(word in key.lower() for word in ('gps', 'gpx')):
                self.addItem(key[len('Customization/'):])
        for path in self.mItems: self.setItemChecked(path, settings.value('Customization/' + path, True, type=bool))

    def treeToSettings(self, settings):
        for path in self.mItems: settings.setValue('Customization/' + path, self.itemChecked(path))

    def reset(self):
        self.mSettings.sync()
        self.settingsToTree(self.mSettings)
        self.mCustomizationEnabledCheckBox.setChecked(self.mSettings.value('UI/Customization/enabled', self.mCustomization.mEnabled, type=bool))
        self.enableCustomization(self.mCustomizationEnabledCheckBox.isChecked())
        self.setCatch(False)

    def enableCustomization(self, enabled):
        for widget in (self.treeWidget, self.toolBar, self.mLeFilter): widget.setEnabled(enabled)
        if not enabled: self.setCatch(False)

    def apply(self):
        self.treeToSettings(self.mSettings)
        self.mSettings.setValue('UI/Customization/enabled', self.mCustomizationEnabledCheckBox.isChecked())
        self.mSettings.setValue('Customization/status', 1)
        self.mSettings.sync()
        self.statusBar().showMessage('配置已保存，重新启动应用后生效。取消不会撤回已经应用的配置。')

    def ok(self):
        self.apply()
        self.hide()
    def cancel(self): self.hide()
    def hideEvent(self, event):
        self.setCatch(False)
        super().hideEvent(event)
    def setCatch(self, on):
        self.actionCatch.setChecked(bool(on and self.mCustomizationEnabledCheckBox.isChecked()))
        if not on and self.mCatchBand is not None and not sip.isdeleted(self.mCatchBand): self.mCatchBand.hide()
    def catchOn(self): return self.actionCatch.isChecked()
    def actionSelectAll_triggered(self):
        for item in self.mItems.values(): item.setCheckState(0, Qt.Checked)

    def filterItems(self, text):
        text = text.casefold().strip()
        def visit(item, parentMatches=False):
            matches = parentMatches or not text or text in (item.text(0) + ' ' + item.text(1)).casefold()
            visible = matches
            for i in range(item.childCount()): visible = visit(item.child(i), matches) or visible
            item.setHidden(not visible)
            if text and visible and item.childCount(): item.setExpanded(True)
            return visible
        for i in range(self.treeWidget.topLevelItemCount()): visit(self.treeWidget.topLevelItem(i))

    @staticmethod
    def findAction(button):
        parent = button.parentWidget()
        if parent:
            for action in parent.actions():
                if isinstance(action, QWidgetAction) and action.defaultWidget() is button: return action
        return button.defaultAction()

    def switchWidget(self, widget, event):
        if event.button() != Qt.LeftButton: return False
        path = ''
        if isinstance(widget, QToolButton):
            action = self.findAction(widget)
            toolbar = widget.parentWidget()
            while toolbar is not None and not isinstance(toolbar, QToolBar): toolbar = toolbar.parentWidget()
            if action is not None and toolbar is not None: path = 'Toolbars/' + toolbar.objectName() + '/' + action.objectName()
        elif isinstance(widget, QToolBar): path = 'Toolbars/' + widget.objectName()
        elif isinstance(widget, QMenu):
            action = widget.actionAt(event.pos())
            for key, (kind, target, owner) in self.mCustomization.mEntries.items():
                if kind == 'action' and owner is widget and target is action:
                    path = key
                    break
        if not path:
            path = self.mCustomization.widgetPath(widget)
            if path and path not in self.mItems:
                # Dynamically constructed native controls are absent from the XML.
                self.addItem(path, widget.toolTip() or widget.objectName())
        item = self.item(path)
        if item is not None:
            item.setCheckState(0, Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked)
            self.mLeFilter.clear()
            self.treeWidget.setCurrentItem(item)
            self.treeWidget.scrollToItem(item)
            if self.mCatchBand is not None and not sip.isdeleted(self.mCatchBand): self.mCatchBand.deleteLater()
            self.mCatchBand = QRubberBand(QRubberBand.Rectangle, widget.window())
            self.mCatchBand.setAttribute(Qt.WA_TransparentForMouseEvents)
            from qgis.PyQt.QtCore import QRect, QPoint
            self.mCatchBand.setGeometry(QRect(widget.mapTo(widget.window(), QPoint()), widget.size()))
            self.mCatchBand.show()
            QTimer.singleShot(600, self.mCatchBand.hide)
        # Even unnamed controls must not activate while the catch tool is on.
        return True

    def saveToFile(self, filename):
        settings = QSettings(str(filename), QSettings.IniFormat)
        settings.remove('Customization')
        self.treeToSettings(settings)
        settings.sync()
        if settings.status() != QSettings.NoError: raise OSError('无法写入界面自定义文件')

    def loadFromFile(self, filename):
        settings = QSettings(str(filename), QSettings.IniFormat)
        settings.sync()
        if settings.status() != QSettings.NoError: raise OSError('无法读取界面自定义文件')
        self.settingsToTree(settings)

    def actionSave_triggered(self):
        filename, _ = QFileDialog.getSaveFileName(self, '保存界面自定义', self.mSettings.value('UI/lastCustomizationDir', str(Path.home())), '界面自定义 (*.ini)')
        if not filename: return
        if not filename.lower().endswith('.ini'): filename += '.ini'
        try: self.saveToFile(filename)
        except OSError as error: QMessageBox.warning(self, '界面自定义', str(error))
        self.mSettings.setValue('UI/lastCustomizationDir', str(Path(filename).parent))

    def actionLoad_triggered(self):
        filename, _ = QFileDialog.getOpenFileName(self, '载入界面自定义', self.mSettings.value('UI/lastCustomizationDir', str(Path.home())), '界面自定义 (*.ini)')
        if not filename: return
        try: self.loadFromFile(filename)
        except OSError as error: QMessageBox.warning(self, '界面自定义', str(error))
        self.mSettings.setValue('UI/lastCustomizationDir', str(Path(filename).parent))

    def showHelp(self): QgsHelp.openHelp('introduction/qgis_configuration.html#customization')
