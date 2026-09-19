"""Vertex coordinate model/dock counterparts of vertextool/qgsvertexeditor.cpp."""
from math import isfinite
from qgis.PyQt.QtCore import QCoreApplication, Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableView, QToolBar, QAbstractItemView, QApplication, QHeaderView
from qgis.core import QgsProject, QgsPointXY, QgsWkbTypes, QgsCoordinateTransform
from qgis.gui import QgsDockWidget, QgsVertexMarker


class QgsVertexEditorModel(QAbstractTableModel):
    editFailed = pyqtSignal(str)

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.mCanvas, self.mLayer, self.mFeatureId = canvas, None, None
        self.mPoints, self.mColumns = [], ['X', 'Y']

    def setFeature(self, layer, fid=None):
        if self.mLayer:
            self.mLayer.geometryChanged.disconnect(self.geometryChanged)
            self.mLayer.featureDeleted.disconnect(self.featureDeleted)
            self.mLayer.editingStopped.disconnect(self.clear)
        self.mLayer, self.mFeatureId = layer, fid
        if layer:
            layer.geometryChanged.connect(self.geometryChanged)
            layer.featureDeleted.connect(self.featureDeleted)
            layer.editingStopped.connect(self.clear)
        self.reload()

    def clear(self): self.setFeature(None)
    def featureDeleted(self, fid):
        if fid == self.mFeatureId: self.clear()
    def geometryChanged(self, fid, geometry):
        if fid == self.mFeatureId: self.reload()

    def reload(self):
        self.beginResetModel()
        self.mPoints, self.mColumns = [], ['X', 'Y']
        if self.mLayer:
            geometry = self.mLayer.getFeature(self.mFeatureId).geometry()
            self.mPoints = list(geometry.vertices())
            if QgsWkbTypes.hasZ(geometry.wkbType()): self.mColumns.append('Z')
            if QgsWkbTypes.hasM(geometry.wkbType()): self.mColumns.append('M')
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.mPoints)
    def columnCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.mColumns)
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.mColumns[section] if orientation == Qt.Horizontal else section
    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role in (Qt.DisplayRole, Qt.EditRole):
            return getattr(self.mPoints[index.row()], self.mColumns[index.column()].lower())()
    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and self.mLayer and self.mLayer.isEditable(): flags |= Qt.ItemIsEditable
        return flags
    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid() or not self.mLayer or not self.mLayer.isEditable(): return False
        try:
            number = float(value)
            if not isfinite(number): raise ValueError('请输入有限数值')
        except (ValueError, TypeError):
            self.editFailed.emit('坐标必须是有限数值')
            return False
        layer, fid = self.mLayer, self.mFeatureId
        geometry = layer.getFeature(fid).geometry()
        point = geometry.vertexAt(index.row())
        getattr(point, 'set' + self.mColumns[index.column()])(number)
        layer.beginEditCommand('编辑顶点坐标')
        success = geometry.moveVertex(point, index.row()) and layer.changeGeometry(fid, geometry)
        if success: layer.endEditCommand()
        else:
            layer.destroyEditCommand()
            self.editFailed.emit('无法修改此顶点')
        layer.triggerRepaint()
        return bool(success)


class QgsVertexEditor(QgsDockWidget):
    def __init__(self, canvas, parent=None):
        super().__init__('顶点编辑器', parent)
        self.setObjectName('VertexEditor')
        self.mCanvas = canvas
        self.mMarkers = []
        self.mVertexEditorModel = QgsVertexEditorModel(canvas, self)
        self.mTableView = QTableView(self)
        self.mTableView.setModel(self.mVertexEditorModel)
        self.mTableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mTableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.mTableView.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.mHint = QLabel('用顶点工具点击要素；坐标使用图层 CRS。', self)
        self.mHint.setWordWrap(True)
        toolbar = QToolBar(self)
        toolbar.addAction(QCoreApplication.translate('QgsMapCanvas', 'Copy Coordinate'), self.copyVertices)
        toolbar.addAction('定位选中顶点', self.zoomToSelected)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.mHint)
        layout.addWidget(toolbar)
        layout.addWidget(self.mTableView)
        self.setWidget(content)
        content.setMinimumHeight(220)
        self.mTableView.selectionModel().selectionChanged.connect(self.updateMarkers)
        self.mVertexEditorModel.modelReset.connect(self.updateMarkers)
        self.mVertexEditorModel.modelReset.connect(self.updateHint)
        self.mVertexEditorModel.editFailed.connect(self.mHint.setText)
        self.visibilityChanged.connect(self.updateMarkers)
        canvas.destinationCrsChanged.connect(self.updateMarkers)
        QgsProject.instance().layersWillBeRemoved.connect(self.layersRemoved)

    def setVertex(self, layer, fid, index):
        self.mVertexEditorModel.setFeature(layer, fid)
        self.mTableView.selectRow(index)
        self.mTableView.scrollTo(self.mVertexEditorModel.index(index, 0))

    def updateHint(self):
        model = self.mVertexEditorModel
        if model.mLayer:
            self.mHint.setText(f'{model.mLayer.name()} · 要素 {model.mFeatureId} · {model.mLayer.crs().authid()}')
        else: self.mHint.setText('用顶点工具点击要素；坐标使用图层 CRS。')

    def selectedRows(self): return sorted(index.row() for index in self.mTableView.selectionModel().selectedRows())
    def mapPoints(self):
        model = self.mVertexEditorModel
        if not model.mLayer: return []
        transform = QgsCoordinateTransform(model.mLayer.crs(), self.mCanvas.mapSettings().destinationCrs(), QgsProject.instance())
        return [transform.transform(QgsPointXY(model.mPoints[row])) for row in self.selectedRows() if row < len(model.mPoints)]
    def updateMarkers(self, *args):
        for marker in self.mMarkers: self.mCanvas.scene().removeItem(marker)
        self.mMarkers = []
        if not self.isVisible(): return
        for point in self.mapPoints():
            marker = QgsVertexMarker(self.mCanvas)
            marker.setColor(QColor('red'))
            marker.setIconType(QgsVertexMarker.ICON_BOX)
            marker.setCenter(point)
            self.mMarkers.append(marker)
    def zoomToSelected(self):
        points = self.mapPoints()
        if points:
            self.mCanvas.setCenter(points[0])
            self.mCanvas.refresh()
    def copyVertices(self):
        model = self.mVertexEditorModel
        lines = ['\t'.join(model.mColumns)]
        for row in self.selectedRows():
            lines.append('\t'.join(format(model.data(model.index(row, col)), '.15g') for col in range(model.columnCount())))
        QApplication.clipboard().setText('\n'.join(lines))
    def layersRemoved(self, ids):
        layer = self.mVertexEditorModel.mLayer
        if layer and layer.id() in ids: self.mVertexEditorModel.clear()
