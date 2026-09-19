"""Project template list model, mirroring src/app/qgstemplateprojectsmodel.cpp.

Lists the .qgs/.qgz templates from every standard AppData location plus the
configured qgis/projectTemplateDir, prepends the native "New Empty Project"
entry (with its generated placeholder preview) and watches the directories so
the welcome page updates when a template is added or removed.
"""
import hashlib
from pathlib import Path

from qgis.PyQt.QtCore import (Qt, QTemporaryDir, QDir, QFileInfo, QFileSystemWatcher,
                              QStandardPaths, QSize)
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QPen, QStandardItem, QStandardItemModel
from qgis.core import Qgis, QgsApplication, QgsProject, QgsSettings, QgsZipUtils

try:
    from .qgsprojectlistitemdelegate import QgsProjectListItemDelegate, QgsProjectPreviewImage
    TitleRole = QgsProjectListItemDelegate.TitleRole
    NativePathRole = QgsProjectListItemDelegate.NativePathRole
    CrsRole = QgsProjectListItemDelegate.CrsRole
except (ImportError, AttributeError):  # pragma: no cover - delegate is always shipped
    QgsProjectPreviewImage = None
    TitleRole = Qt.UserRole + 1
    NativePathRole = Qt.UserRole + 3
    CrsRole = Qt.UserRole + 4


class QgsTemplateProjectsModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mTemporaryDir = QTemporaryDir()
        self.mFileSystemWatcher = QFileSystemWatcher(self)
        paths = QStandardPaths.standardLocations(QStandardPaths.AppDataLocation)
        templateDirName = QgsSettings().value(
            'qgis/projectTemplateDir',
            str(Path(QgsApplication.qgisSettingsDirPath()) / 'project_templates'), type=str)
        for templatePath in paths:
            self.addTemplateDirectory(str(Path(templatePath) / 'project_templates'))
        self.addTemplateDirectory(templateDirName)
        self.mFileSystemWatcher.directoryChanged.connect(self.scanDirectory)
        self.setColumnCount(1)
        self.appendRow(self.createEmptyProjectItem())

    def createEmptyProjectItem(self):
        """Native ctor: the "< New Empty Project >" row with a dashed placeholder."""
        item = QStandardItem()
        item.setData(self.tr('New Empty Project'), TitleRole)
        project = QgsProject.instance()

        def updateCrs():
            item.setData(project.crs().userFriendlyIdentifier(), CrsRole)

        project.crsChanged.connect(updateCrs)
        updateCrs()
        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        devicePixelRatio = 1.0
        window = self.parent()
        if window is not None and hasattr(window, 'devicePixelRatioF'):
            devicePixelRatio = window.devicePixelRatioF()
        image = QImage(QSize(int(250 * devicePixelRatio), int(177 * devicePixelRatio)),
                       QImage.Format_ARGB32)
        settings = QgsSettings()
        image.fill(QColor(settings.value('qgis/default_canvas_color_red', 255, type=int),
                          settings.value('qgis/default_canvas_color_green', 255, type=int),
                          settings.value('qgis/default_canvas_color_blue', 255, type=int)))
        painter = QPainter(image)
        painter.setOpacity(0.5)
        painter.setPen(QPen(Qt.gray, 1, Qt.DashLine))
        painter.drawRect(20, 20, image.width() - 40, image.height() - 40)
        painter.end()
        if QgsProjectPreviewImage is not None:
            item.setData(QgsProjectPreviewImage(image).pixmap(), Qt.DecorationRole)
        return item

    def addTemplateDirectory(self, path):
        if QDir(path).exists():
            self.scanDirectory(path)
            self.mFileSystemWatcher.addPath(path)

    def scanDirectory(self, path):
        directory = QDir(path)
        files = directory.entryInfoList(['*.qgs', '*.qgz'])
        # Remove any template from this directory
        for row in range(self.rowCount() - 1, -1, -1):
            if str(self.index(row, 0).data(NativePathRole) or '').startswith(path):
                self.removeRow(row)
        # Refill with templates from this directory
        for file in files:
            item = QStandardItem(file.fileName())
            # Native hashes the path with SHA-224 to get a stable temporary folder.
            fileId = hashlib.sha224(file.filePath().encode('utf-8')).hexdigest()
            target = Path(self.mTemporaryDir.path()) / fileId
            target.mkdir(parents=True, exist_ok=True)
            unzipped, _ = QgsZipUtils.unzip(file.filePath(), str(target))
            if not unzipped:
                continue
            thumbnailPath = target / 'preview.png'
            thumbnail = QgsProjectPreviewImage(str(thumbnailPath)) if QgsProjectPreviewImage else None
            if thumbnail is not None and not thumbnail.isNull():
                item.setData(thumbnail.pixmap(), Qt.DecorationRole)
            item.setData(file.baseName(), TitleRole)
            item.setData(file.filePath(), NativePathRole)
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.appendRow(item)
