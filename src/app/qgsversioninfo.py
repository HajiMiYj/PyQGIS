"""Version service counterpart of src/app/qgsversioninfo.cpp."""
from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import Qgis, QgsNetworkAccessManager


class QgsVersionInfo(QObject):
    versionInfoAvailable = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mReply = None
        self.mLatestVersion = 0
        self.mDownloadInfo = self.mAdditionalHtml = self.mErrorString = ''

    def checkVersion(self):
        if self.mReply is not None: return
        self.mErrorString = ''
        self.mReply = QgsNetworkAccessManager.instance().get(QNetworkRequest(QUrl('https://version.qgis.org/version.txt')))
        self.mReply.finished.connect(self.versionReplyFinished)

    def parseVersion(self, text):
        self.mLatestVersion = 0
        self.mDownloadInfo = self.mAdditionalHtml = ''
        if '#QGIS Version' not in text: raise ValueError('服务器响应缺少 QGIS 版本标记')
        parts = [p.strip() for p in text.split('#QGIS Version', 1)[1].split('|') if p.strip()]
        self.mLatestVersion = int(parts[0])
        if self.mLatestVersion <= 0: raise ValueError('版本号无效')
        self.mDownloadInfo = parts[1] if len(parts) > 1 else ''
        self.mAdditionalHtml = parts[2] if len(parts) > 2 else ''

    def newVersionAvailable(self): return self.mLatestVersion > Qgis.QGIS_VERSION_INT
    def isDevelopmentVersion(self): return 0 < self.mLatestVersion < Qgis.QGIS_VERSION_INT

    # Native accessors (qgsversioninfo.h) used by the welcome page.
    def latestVersion(self): return self.mLatestVersion
    def downloadInfo(self): return self.mDownloadInfo
    def additionalHtml(self): return self.mAdditionalHtml
    def error(self): return self.mError
    def errorString(self): return self.mErrorString

    def versionReplyFinished(self):
        reply, self.mReply = self.mReply, None
        if reply.error() != QNetworkReply.NoError: self.mErrorString = reply.errorString()
        else:
            try: self.parseVersion(bytes(reply.readAll()).decode('utf-8', errors='replace'))
            except (ValueError, IndexError) as error: self.mErrorString = str(error)
        reply.deleteLater()
        self.versionInfoAvailable.emit()

    def cancel(self):
        if self.mReply is not None:
            reply, self.mReply = self.mReply, None
            reply.finished.disconnect(self.versionReplyFinished)
            reply.abort()
            reply.deleteLater()
