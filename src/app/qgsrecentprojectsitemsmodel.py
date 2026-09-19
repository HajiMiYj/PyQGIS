"""Recent-project list model, mirroring src/app/qgsrecentprojectsitemsmodel.cpp.

The welcome page and the "Recent Projects" submenu share this model: it exposes
the native roles used by QgsProjectListItemDelegate (title, path, CRS, pin) and
performs the native existence check (project storages first, then plain files).
"""
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QAbstractListModel, QModelIndex, QDir
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsDataSourceUri

try:
    from .qgsprojectlistitemdelegate import QgsProjectListItemDelegate, QgsProjectPreviewImage
    TitleRole = QgsProjectListItemDelegate.TitleRole
    PathRole = QgsProjectListItemDelegate.PathRole
    NativePathRole = QgsProjectListItemDelegate.NativePathRole
    CrsRole = QgsProjectListItemDelegate.CrsRole
    PinRole = QgsProjectListItemDelegate.PinRole
    AnonymisedNativePathRole = QgsProjectListItemDelegate.AnonymisedNativePathRole
except (ImportError, AttributeError):  # pragma: no cover - delegate is always shipped
    QgsProjectPreviewImage = None
    TitleRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    NativePathRole = Qt.UserRole + 3
    CrsRole = Qt.UserRole + 4
    PinRole = Qt.UserRole + 5
    AnonymisedNativePathRole = Qt.UserRole + 6


@dataclass
class RecentProjectData:
    """QgsRecentProjectItemsModel::RecentProjectData."""

    path: str = ''
    title: str = ''
    previewImagePath: str = ''
    crs: str = ''
    pin: bool = False
    checkedExists: bool = False
    exists: bool = False

    def __eq__(self, other):
        return isinstance(other, RecentProjectData) and other.path == self.path


class QgsRecentProjectItemsModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mRecentProjects = []

    def setRecentProjects(self, recentProjects):
        self.beginResetModel()
        self.mRecentProjects = list(recentProjects)
        self.endResetModel()

    def recentProjects(self):
        return list(self.mRecentProjects)

    def rowCount(self, parent=QModelIndex()):
        return len(self.mRecentProjects)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.mRecentProjects):
            return None
        project = self.mRecentProjects[index.row()]
        if role in (Qt.DisplayRole, TitleRole):
            return project.title if project.title != project.path else Path(project.path).stem
        if role == PathRole:
            return project.path
        if role == NativePathRole:
            return QDir.toNativeSeparators(project.path)
        if role == CrsRole:
            if not project.crs:
                return ''
            crs = QgsCoordinateReferenceSystem.fromOgcWmsCrs(project.crs)
            return f'{project.crs} ({crs.userFriendlyIdentifier()})'
        if role == PinRole:
            return project.pin
        if role == Qt.DecorationRole:
            if not project.previewImagePath or QgsProjectPreviewImage is None:
                return None
            thumbnail = QgsProjectPreviewImage(project.previewImagePath)
            return None if thumbnail.isNull() else thumbnail.pixmap()
        if role in (Qt.ToolTipRole, AnonymisedNativePathRole):
            name = project.path
            storage = QgsApplication.projectStorageRegistry().projectStorageFromUri(name)
            if storage is not None:
                name = QgsDataSourceUri.removePassword(name, True)
            return name
        return None

    def flags(self, index):
        if not index.isValid() or not self.rowCount(index.parent()) or index.row() >= len(self.mRecentProjects):
            return Qt.NoItemFlags
        itemFlags = super().flags(index)
        project = self.mRecentProjects[index.row()]
        # This check can be slow for network based projects, so only run it the first time
        if not project.checkedExists:
            self._checkProject(project)
        if not project.exists:
            itemFlags &= ~Qt.ItemIsEnabled
        return itemFlags

    @staticmethod
    def _checkProject(project):
        storage = QgsApplication.projectStorageRegistry().projectStorageFromUri(project.path)
        if storage is not None:
            path = storage.filePath(project.path)
            if storage.type() == 'geopackage' and not path:
                project.exists = False
            else:
                project.exists = True
        else:
            project.exists = Path(project.path).exists()
        project.checkedExists = True

    def pinProject(self, index):
        self.mRecentProjects[index.row()].pin = True

    def unpinProject(self, index):
        self.mRecentProjects[index.row()].pin = False

    def setRecentProjectsPinned(self, index, pinned):
        self.mRecentProjects[index.row()].pin = pinned

    def removeProject(self, index):
        self.beginRemoveRows(QModelIndex(), index.row(), index.row())
        del self.mRecentProjects[index.row()]
        self.endRemoveRows()

    def recheckProject(self, index):
        self._checkProject(self.mRecentProjects[index.row()])

    def clear(self, clearPinned=False):
        self.beginResetModel()
        if clearPinned:
            self.mRecentProjects.clear()
        else:
            self.mRecentProjects = [project for project in self.mRecentProjects if project.pin]
        self.endResetModel()
