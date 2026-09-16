import math
from qgis.PyQt.QtCore import QAbstractTableModel, QModelIndex, Qt
from qgis.core import QgsPointXY


class QgsGCPListModel(QAbstractTableModel):
    HEADERS = ('启用', 'ID', '源 X', '源 Y', '目标 X', '目标 Y', 'dX', 'dY', '残差')

    def __init__(self, window):
        super().__init__(window)
        self.mWindow = window

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.mWindow.mPoints)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.HEADERS)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal: return self.HEADERS[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        point = self.mWindow.mPoints[index.row()]
        col = index.column()
        if col == 0 and role == Qt.CheckStateRole: return Qt.Checked if point.isEnabled() else Qt.Unchecked
        if role not in (Qt.DisplayRole, Qt.EditRole): return None
        if col == 0: return ''
        if col == 1: return index.row()
        source = point.sourcePoint()
        try: target = self.mWindow.destinationPoint(point)
        except Exception: target = QgsPointXY(math.nan, math.nan)
        residual = self.mWindow.mResiduals[index.row()] if index.row() < len(self.mWindow.mResiduals) else (math.nan, math.nan)
        values = (source.x(), source.y(), target.x(), target.y(), residual[0], residual[1], math.hypot(*residual))
        value = values[col-2]
        return value if role == Qt.EditRole else format(value, '.12g') if math.isfinite(value) else '—'

    def flags(self, index):
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if self.mWindow.mBusy: return flags
        if index.column() == 0: flags |= Qt.ItemIsUserCheckable
        if 2 <= index.column() <= 5: flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or self.mWindow.mBusy: return False
        point = self.mWindow.mPoints[index.row()]
        col = index.column()
        if col == 0 and role == Qt.CheckStateRole:
            point.setEnabled(value == Qt.Checked)
        elif 2 <= col <= 5 and role == Qt.EditRole:
            try:
                value = float(value)
                if not math.isfinite(value): return False
            except (ValueError, TypeError): return False
            try: xy = point.sourcePoint() if col < 4 else self.mWindow.destinationPoint(point)
            except Exception: return False
            if col % 2 == 0: xy.setX(value)
            else: xy.setY(value)
            if col < 4: point.setSourcePoint(xy)
            else:
                point.setDestinationPoint(xy)
                point.setDestinationPointCrs(self.mWindow.mSettings['crs'])
        else: return False
        self.mWindow.pointsChanged()
        return True

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()
