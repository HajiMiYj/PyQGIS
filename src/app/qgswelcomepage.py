"""Welcome page, mirroring src/app/qgswelcomepage.cpp.

Upstream 3.34.10 keeps the class but comments out its instantiation, so the
combo entry "启动时打开工程 → 欢迎页" (qgis/projOpenAtLaunch == 0) had nothing to
show. This port keeps the native behaviour alive: recent projects, project
templates, the optional news feed and the version banner, with the native
context menus (open directory, pin/unpin, refresh, remove, clear list).
"""
from pathlib import Path

from qgis.PyQt.QtCore import (Qt, QByteArray, QEvent, QModelIndex, QPoint, QRect, QSize, QUrl,
                              QRegularExpression)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QAbstractItemView, QApplication, QLabel, QListView,
                                 QMenu, QMessageBox, QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout,
                                 QWidget)
from qgis.core import (QgsApplication, QgsFileUtils, QgsNewsFeedModel, QgsNewsFeedParser,
                       QgsNewsFeedProxyModel, QgsSettings, QgsStringUtils)

from .qgsrecentprojectsitemsmodel import QgsRecentProjectItemsModel
from .qgsversioninfo import QgsVersionInfo
from .qgstemplateprojectsmodel import QgsTemplateProjectsModel

FEED_URL = 'https://feed.qgis.org/'


def _delegateModule():
    from .qgsprojectlistitemdelegate import QgsProjectListItemDelegate, QgsNewsItemListItemDelegate
    return QgsProjectListItemDelegate, QgsNewsItemListItemDelegate


class QgsWelcomePage(QWidget):
    def __init__(self, skipVersionCheck=False, parent=None, app=None):
        super().__init__(parent)
        self.mApp = app
        self.mNewsFeedParser = None
        self.mNewsFeedModel = None
        self.mNewsFeedListView = None
        self.mNewsDelegate = None
        self.mSplitter2 = None
        self.mNewsFeedTitle = None
        settings = QgsSettings()
        self.mRecentProjects = []
        Delegate, NewsDelegate = _delegateModule()

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mSplitter = QSplitter(Qt.Horizontal)
        mainLayout.addWidget(self.mSplitter, 1)

        # --- recent projects -------------------------------------------------
        leftContainer = QWidget()
        leftLayout = QVBoxLayout(leftContainer)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        titleSize = int(QApplication.fontMetrics().height() * 1.4)
        self.mRecentProjectsTitle = QLabel(
            f"<div style='font-size:{titleSize}px;font-weight:bold'>{self.tr('Recent Projects')}</div>")
        self.mRecentProjectsTitle.setContentsMargins(titleSize // 2, titleSize // 6, 0, 0)
        leftLayout.addWidget(self.mRecentProjectsTitle, 0)

        self.mRecentProjectsListView = QListView()
        self.mRecentProjectsListView.setResizeMode(QListView.Adjust)
        self.mRecentProjectsListView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mRecentProjectsListView.customContextMenuRequested.connect(self.showContextMenuForProjects)
        self.mRecentProjectsListView.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.mRecentProjectsModel = QgsRecentProjectItemsModel(self.mRecentProjectsListView)
        self.mRecentProjectsListView.setModel(self.mRecentProjectsModel)
        self.mRecentProjectsDelegate = Delegate(self.mRecentProjectsListView)
        self.mRecentProjectsListView.setItemDelegate(self.mRecentProjectsDelegate)
        leftLayout.addWidget(self.mRecentProjectsListView, 1)
        self.mSplitter.addWidget(leftContainer)

        # --- news feed (only when the Options entry is enabled) --------------
        rightContainer = QWidget()
        rightLayout = QVBoxLayout(rightContainer)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        feedDisabled = QgsSettings().value(
            f'{QgsNewsFeedParser.keyForFeed(FEED_URL)}/disabled', False, type=bool)
        if not feedDisabled:
            self.mSplitter2 = QSplitter(Qt.Vertical)
            rightLayout.addWidget(self.mSplitter2)
            newsContainer = QWidget()
            newsLayout = QVBoxLayout(newsContainer)
            newsLayout.setContentsMargins(0, 0, 0, 0)
            self.mNewsFeedTitle = QLabel(
                f"<div style='font-size:{titleSize}px;font-weight:bold'>{self.tr('News')}</div>")
            self.mNewsFeedTitle.setContentsMargins(titleSize // 2, titleSize // 6, 0, 0)
            newsLayout.addWidget(self.mNewsFeedTitle, 0)
            self.mNewsFeedParser = QgsNewsFeedParser(QUrl(FEED_URL), '', self)
            self.mNewsFeedModel = QgsNewsFeedProxyModel(self.mNewsFeedParser, self)
            self.mNewsFeedListView = QListView()
            self.mNewsFeedListView.setResizeMode(QListView.Adjust)
            self.mNewsFeedListView.setModel(self.mNewsFeedModel)
            self.mNewsFeedListView.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.mNewsDelegate = NewsDelegate(self.mNewsFeedListView)
            self.mNewsFeedListView.setItemDelegate(self.mNewsDelegate)
            self.mNewsFeedListView.setContextMenuPolicy(Qt.CustomContextMenu)
            self.mNewsFeedListView.viewport().installEventFilter(self)
            self.mNewsFeedListView.activated.connect(self.newsItemActivated)
            self.mNewsFeedListView.customContextMenuRequested.connect(self.showContextMenuForNews)
            self.mNewsFeedParser.entryDismissed.connect(self.updateNewsFeedVisibility)
            self.mNewsFeedParser.fetched.connect(self.updateNewsFeedVisibility)
            newsLayout.addWidget(self.mNewsFeedListView, 1)
            self.mNewsFeedParser.fetch()
            self.mSplitter2.addWidget(newsContainer)

        # --- project templates ----------------------------------------------
        templateContainer = QWidget()
        templateLayout = QVBoxLayout(templateContainer)
        templateLayout.setContentsMargins(0, 0, 0, 0)
        templatesTitle = QLabel(
            f"<div style='font-size:{titleSize}px;font-weight:bold'>{self.tr('Project Templates')}</div>")
        templatesTitle.setContentsMargins(titleSize // 2, titleSize // 6, 0, 0)
        templateLayout.addWidget(templatesTitle, 0)
        self.mTemplateProjectsModel = QgsTemplateProjectsModel(self)
        self.mTemplateProjectsListView = QListView()
        self.mTemplateProjectsListView.setResizeMode(QListView.Adjust)
        self.mTemplateProjectsListView.setModel(self.mTemplateProjectsModel)
        self.mTemplateProjectsListView.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.mTemplateProjectsDelegate = Delegate(self.mTemplateProjectsListView)
        self.mTemplateProjectsDelegate.setShowPath(False)
        self.mTemplateProjectsListView.setItemDelegate(self.mTemplateProjectsDelegate)
        self.mTemplateProjectsListView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mTemplateProjectsListView.customContextMenuRequested.connect(self.showContextMenuForTemplates)
        templateLayout.addWidget(self.mTemplateProjectsListView, 1)
        if self.mSplitter2 is not None:
            self.mSplitter2.addWidget(templateContainer)
        else:
            rightLayout.addWidget(templateContainer)

        self.mSplitter.addWidget(rightContainer)
        self.mSplitter.setStretchFactor(0, 4)
        self.mSplitter.setStretchFactor(1, 6)

        # --- version information banner -------------------------------------
        self.mVersionInformation = QTextBrowser()
        self.mVersionInformation.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.mVersionInformation.setReadOnly(True)
        self.mVersionInformation.setOpenExternalLinks(True)
        self.mVersionInformation.setStyleSheet(
            'QTextEdit { background-color: #dff0d8; color:#000000; border: 1px solid #8e998a; '
            'padding-top: 0.25em; max-height: 1.75em; min-height: 1.75em; } '
            'QScrollBar { background-color: rgba(0,0,0,0); } '
            'QScrollBar::add-page,QScrollBar::sub-page,QScrollBar::handle '
            '{ background-color: rgba(0,0,0,0); color: rgba(0,0,0,0); } '
            'QScrollBar::up-arrow,QScrollBar::down-arrow { color: rgb(0,0,0); } ')
        mainLayout.addWidget(self.mVersionInformation)
        self.mVersionInformation.setVisible(False)
        self.mVersionInfo = QgsVersionInfo(self)
        if (not QgsApplication.isRunningFromBuildDir()
                and settings.value('qgis/allowVersionCheck', True, type=bool)
                and settings.value('qgis/checkVersion', True, type=bool) and not skipVersionCheck):
            self.mVersionInfo.versionInfoAvailable.connect(self.versionInfoReceived)
            self.mVersionInfo.checkVersion()

        self.mSplitter.restoreState(settings.value('Windows/WelcomePage/SplitState', QByteArray(), type=QByteArray))
        if self.mSplitter2 is not None:
            self.mSplitter2.restoreState(
                settings.value('Windows/WelcomePage/SplitState2', QByteArray(), type=QByteArray))

        self.mRecentProjectsListView.activated.connect(self.recentProjectItemActivated)
        self.mTemplateProjectsListView.activated.connect(self.templateProjectItemActivated)
        self.updateNewsFeedVisibility()

    # --- lifecycle -----------------------------------------------------------
    def closeEvent(self, event):
        settings = QgsSettings()
        settings.setValue('Windows/WelcomePage/SplitState', self.mSplitter.saveState())
        if self.mSplitter2 is not None and self.mNewsFeedTitle is not None \
                and self.mNewsFeedTitle.isVisible():
            settings.setValue('Windows/WelcomePage/SplitState2', self.mSplitter2.saveState())
        self.mVersionInfo.cancel()
        super().closeEvent(event)

    @staticmethod
    def newsFeedUrl():
        return FEED_URL

    def recentProjectsModel(self):
        return self.mRecentProjectsModel

    def setRecentProjects(self, recentProjects):
        self.mRecentProjects = list(recentProjects)
        self.mRecentProjectsModel.setRecentProjects(recentProjects)

    # --- activation ----------------------------------------------------------
    def recentProjectItemActivated(self, index):
        path = self.mRecentProjectsModel.data(index, self._roles().PathRole)
        if self.mApp is not None and path:
            self.mApp.openProject(path)

    def templateProjectItemActivated(self, index):
        if self.mApp is None:
            return
        role = self._roles().NativePathRole
        value = index.data(role)
        if value is None or value == '':
            self.mApp.newProject()
        else:
            self.mApp.fileNewFromTemplate(value)

    def newsItemActivated(self, index):
        if not index.isValid():
            return
        QDesktopServices.openUrl(index.data(QgsNewsFeedModel.Link))

    def versionInfoReceived(self):
        if self.mVersionInfo.newVersionAvailable():
            self.mVersionInformation.setVisible(True)
            # QStringLiteral(...).arg(tr(...), insertLinks(...)) - built by
            # concatenation because the CSS braces collide with str.format.
            self.mVersionInformation.setText(
                "<style> a, a:visited, a:hover { color:#268300; } </style><b>"
                + self.tr('New QGIS version available') + ':</b> '
                + self._insertLinks(self.mVersionInfo.downloadInfo()))

    @staticmethod
    def _insertLinks(text):
        """QgsStringUtils::insertLinks() returns (text, foundLinks) in PyQGIS."""
        result = QgsStringUtils.insertLinks(text)
        return result[0] if isinstance(result, tuple) else result

    @staticmethod
    def _roles():
        from .qgsprojectlistitemdelegate import QgsProjectListItemDelegate
        return QgsProjectListItemDelegate

    # --- context menus -------------------------------------------------------
    def showContextMenuForProjects(self, point):
        model = self.mRecentProjectsModel
        index = self.mRecentProjectsListView.indexAt(point)
        if model.rowCount() == 0:
            return
        roles = self._roles()
        menu = QMenu(self)
        if index.isValid():
            pin = bool(model.data(index, roles.PinRole))
            path = model.data(index, roles.PathRole) or ''
            if not path:
                return
            storage = QgsApplication.projectStorageRegistry().projectStorageFromUri(path)
            enabled = bool(model.flags(index) & Qt.ItemIsEnabled)
            if enabled:
                if not pin:
                    action = menu.addAction(self.tr('Pin to List'))
                    action.triggered.connect(lambda: self.pinProject(index.row()))
                else:
                    action = menu.addAction(self.tr('Unpin from List'))
                    action.triggered.connect(lambda: self.unpinProject(index.row()))
                if storage is not None:
                    path = storage.filePath(path)
                if path:
                    action = menu.addAction(self.tr('Open Directory…'))
                    # QgsGui::nativePlatformInterface() is not exposed to Python, so open
                    # the containing directory through the platform URL handler instead.
                    action.triggered.connect(
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))))
            else:
                action = menu.addAction(self.tr('Refresh'))
                action.triggered.connect(lambda: model.recheckProject(index))
                showClosestPath = storage is None
                if storage is not None and storage.type() == 'geopackage':
                    match = QRegularExpression(
                        '^(geopackage:)([^\\?]+)\\?(.+)$',
                        QRegularExpression.CaseInsensitiveOption).match(path)
                    if match.hasMatch():
                        path = match.captured(2)
                        showClosestPath = True
                if showClosestPath:
                    closestPath = QgsFileUtils.findClosestExistingPath(path)
                    action = menu.addAction(
                        self.tr('Open “%1”…').replace('%1', str(Path(closestPath))))
                    action.triggered.connect(
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(closestPath)))
            action = menu.addAction(self.tr('Remove from List'))
            action.triggered.connect(lambda: self.removeProject(index.row()))
            menu.addSeparator()
        action = menu.addAction(self.tr('Clear List'))
        action.triggered.connect(self.clearRecentProjects)
        menu.popup(self.mRecentProjectsListView.mapToGlobal(point))
        menu.aboutToHide.connect(menu.deleteLater)

    def showContextMenuForTemplates(self, point):
        index = self.mTemplateProjectsListView.indexAt(point)
        if not index.isValid():
            return
        roles = self._roles()
        fileInfo = Path(index.data(roles.NativePathRole) or '')
        menu = QMenu(self)
        if fileInfo.exists() and fileInfo.is_file():
            action = menu.addAction(self.tr('Delete Template…'))
            action.triggered.connect(lambda: self.deleteTemplate(fileInfo, index))
        menu.popup(self.mTemplateProjectsListView.mapToGlobal(point))
        menu.aboutToHide.connect(menu.deleteLater)

    def deleteTemplate(self, fileInfo, index):
        roles = self._roles()
        answer = QMessageBox.question(
            self, self.tr('Delete Template'),
            self.tr('Do you want to delete the template %1? This action can not be undone.')
            .replace('%1', str(index.data(roles.TitleRole))),
            QMessageBox.Yes | QMessageBox.Cancel)
        if answer == QMessageBox.Yes:
            try:
                Path(fileInfo).unlink()
            except OSError as error:
                if self.mApp is not None:
                    self.mApp.mMessageBar.pushWarning(self.tr('Delete Template'), str(error))

    def showContextMenuForNews(self, point):
        if self.mNewsFeedListView is None:
            return
        index = self.mNewsFeedListView.indexAt(point)
        if not index.isValid():
            return
        key = index.data(QgsNewsFeedModel.Key)
        menu = QMenu(self)
        action = menu.addAction(self.tr('Dismiss'))
        action.triggered.connect(lambda: self.mNewsFeedParser.dismissEntry(key))
        action = menu.addAction(self.tr('Dismiss All'))
        action.triggered.connect(self.mNewsFeedParser.dismissAll)
        menu.addSeparator()
        action = menu.addAction(self.tr('Hide QGIS News…'))
        action.triggered.connect(self.hideNewsFeed)
        menu.popup(self.mNewsFeedListView.mapToGlobal(point))
        menu.aboutToHide.connect(menu.deleteLater)

    def hideNewsFeed(self):
        if QMessageBox.question(
                self, self.tr('QGIS News'),
                self.tr('Are you sure you want to hide QGIS news? (The news feed can be '
                        're-enabled from the QGIS settings dialog.)')) == QMessageBox.Yes:
            self.mNewsFeedParser.dismissAll()
            QgsSettings().setValue(
                f'{QgsNewsFeedParser.keyForFeed(FEED_URL)}/disabled', True)

    # --- model helpers -------------------------------------------------------
    def updateNewsFeedVisibility(self):
        if not self.mNewsFeedModel or not self.mNewsFeedListView or not self.mSplitter2:
            return
        visible = self.mNewsFeedModel.rowCount() > 0
        self.mNewsFeedListView.setVisible(visible)
        self.mNewsFeedTitle.setVisible(visible)
        if not visible:
            self.mSplitter2.setSizes([0, 99999999])
        else:
            self.mSplitter2.restoreState(
                QgsSettings().value('Windows/WelcomePage/SplitState2', QByteArray(), type=QByteArray))
            if self.mSplitter2.sizes()[0] == 0:
                splitSize = self.mSplitter2.height() // 2
                self.mSplitter2.setSizes([splitSize, splitSize])

    def eventFilter(self, obj, event):
        if self.mNewsFeedListView is not None and obj is self.mNewsFeedListView.viewport() \
                and event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                index = self.mNewsFeedListView.indexAt(event.pos())
                if index.isValid():
                    itemClickPoint = event.pos() - self.mNewsFeedListView.visualRect(index).topLeft()
                    dismiss = self.mNewsDelegate.dismissRect()
                    size = self.mNewsDelegate.dismissRectSize()
                    if QRect(dismiss.left(), dismiss.top(), size.width(), size.height()) \
                            .contains(itemClickPoint):
                        self.mNewsFeedParser.dismissEntry(index.data(QgsNewsFeedModel.Key))
                    return True
        return super().eventFilter(obj, event)

    def removeProject(self, row):
        self.mRecentProjectsModel.removeProject(self.mRecentProjectsModel.index(row))
        self.projectsChanged()

    def pinProject(self, row):
        self.mRecentProjectsModel.pinProject(self.mRecentProjectsModel.index(row))
        self.projectsChanged()

    def unpinProject(self, row):
        self.mRecentProjectsModel.unpinProject(self.mRecentProjectsModel.index(row))
        self.projectsChanged()

    def clearRecentProjects(self):
        messageBox = QMessageBox(QMessageBox.Question, self.tr('Recent Projects'),
                                 self.tr('Are you sure you want to clear the list of recent projects?'),
                                 QMessageBox.No | QMessageBox.Yes | QMessageBox.YesToAll, self)
        messageBox.button(QMessageBox.YesToAll).setText(self.tr('Yes, including pinned projects'))
        answer = messageBox.exec_()
        if answer != QMessageBox.No:
            self.mRecentProjectsModel.clear(answer == QMessageBox.YesToAll)
            self.projectsChanged(clearPinned=answer == QMessageBox.YesToAll)

    def projectsChanged(self, clearPinned=False):
        """Push the model state back to QgisApp (native projectRemoved/Pinned/Cleared)."""
        if self.mApp is None:
            return
        self.mApp.setRecentProjects(self.mRecentProjectsModel.recentProjects(),
                                    clearPinned=clearPinned)
