from pathlib import Path
import math
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import Qgis, QgsMesh, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsExpressionContextGenerator, QgsGeometry, QgsPointXY, QgsMeshTransformVerticesByExpression, QgsProject
from qgis.gui import QgsDockWidget, QgsRubberBand, QgsGui


class _MeshExpressionContextGenerator(QgsExpressionContextGenerator):
    def createExpressionContext(self):
        return QgsExpressionContext([QgsExpressionContextUtils.meshExpressionScope(QgsMesh.Vertex)])


class QgsMeshTransformCoordinatesDockWidget(QgsDockWidget):
    calculationUpdated = pyqtSignal()
    aboutToBeApplied = pyqtSignal()
    applied = pyqtSignal()

    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.mTool = tool
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/mesh/qgsmeshtransformcoordinatesdockwidgetbase.ui'), self)
        self.setObjectName('QgsMeshTransformCoordinatesDockWidget')
        self.setWindowTitle('变换网孔顶点坐标')
        QgsGui.enableAutoGeometryRestore(self)
        self.mInputLayer, self.mInputVertices = None, []
        self.mIsCalculated, self.mIsResultValid = False, False
        self.mTransformVertices = None
        self.mUpdating = False
        self.mPreview = QgsRubberBand(tool.canvas(), Qgis.GeometryType.Point)
        self.mPreview.setColor(QColor('magenta'))
        self.mPreview.setIconSize(8)
        self.mExpressionContextGenerator = _MeshExpressionContextGenerator()
        for axis in 'XYZ':
            edit = getattr(self, 'mExpressionEdit' + axis)
            check = getattr(self, 'mCheckBox' + axis)
            edit.setExpression('$vertex_' + axis.lower())
            edit.registerExpressionContextGenerator(self.mExpressionContextGenerator)
            edit.setEnabled(False)
            check.toggled.connect(edit.setEnabled)
            check.toggled.connect(self.updateButton)
            edit.expressionChanged.connect(self.updateButton)
        self.mButtonImport.setCheckable(True)
        self.mButtonImport.toggled.connect(self.onImportVertexClicked)
        self.mButtonPreview.clicked.connect(self.calculate)
        self.mButtonApply.clicked.connect(self.apply)
        self.visibilityChanged.connect(lambda visible: self.clearPreview() if not visible else self.updateSelection())
        self.updateSelection()

    def clearPreview(self):
        self.mPreview.reset(Qgis.GeometryType.Point)
        self.mPreview.hide()
        self.mIsCalculated, self.mIsResultValid = False, False
        self.mTransformVertices = None
        self.mButtonApply.setEnabled(False)

    def isCalculated(self): return self.mIsCalculated
    def isResultValid(self): return self.mIsResultValid
    def transformedVertex(self, index):
        if self.mTransformVertices is None or not self.mIsCalculated: return None
        return self.mTransformVertices.transformedVertex(self.mInputLayer, index)

    def updateSelection(self):
        self.setInput(self.mTool.layer(), sorted(self.mTool.mSelectedVertices))

    def setInput(self, layer, vertexIndexes):
        self.clearPreview()
        self.mInputLayer = layer
        self.mInputVertices = list(vertexIndexes)
        count = len(self.mInputVertices)
        if layer is None: message = '没有活动网孔图层'
        elif not layer.isEditable(): message = f'网孔“{layer.name()}”未开启编辑'
        else: message = f'网孔“{layer.name()}”：已选择 {count} 个顶点；表达式使用图层坐标系'
        self.mLabelInformation.setText(message)
        self.mButtonImport.setEnabled(layer is not None and layer.isEditable())
        self.importVertexCoordinates()
        self.updateButton()

    def updateButton(self, *unused):
        if self.mUpdating: return
        self.clearPreview()
        enabled = bool(self.mInputLayer and self.mInputLayer.isEditable() and self.mInputVertices)
        checked = [getattr(self, 'mExpressionEdit'+axis) for axis in 'XYZ' if getattr(self, 'mCheckBox'+axis).isChecked()]
        # QgsExpressionLineEdit's cached validation may lag its changed signal.
        # Parse the current text, including mesh-scope functions, synchronously.
        context = self.mExpressionContextGenerator.createExpressionContext()
        valid = True
        for edit in checked:
            expression = QgsExpression(edit.expression())
            expression.prepare(context)
            valid = valid and bool(edit.expression().strip()) and not expression.hasParserError()
        self.mButtonPreview.setEnabled(enabled and bool(checked) and valid)
        self.calculationUpdated.emit()

    def transformation(self):
        layer = self.mInputLayer
        if layer is not self.mTool.layer() or not self.mTool.editor() or not self.mInputVertices: return None
        expressions = [getattr(self, 'mExpressionEdit'+axis).expression() if getattr(self, 'mCheckBox'+axis).isChecked() else '' for axis in 'XYZ']
        if not any(expressions):
            self.mTool.warning('请勾选要变换的坐标')
            return None
        transform = QgsMeshTransformVerticesByExpression()
        transform.setInputVertices(self.mInputVertices)
        transform.setExpressions(*expressions)
        if not transform.calculate(layer):
            self.mTool.warning(transform.message() or '表达式错误，或变换会破坏网孔拓扑/几何')
            return None
        for index in self.mInputVertices:
            point = transform.transformedVertex(layer, index)
            if not all(math.isfinite(value) for value in (point.x(), point.y(), point.z())):
                self.mTool.warning('变换结果包含无效或非有限坐标，未应用')
                return None
        return transform

    def calculate(self):
        self.clearPreview()
        if not self.mButtonPreview.isEnabled(): return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.mTransformVertices = self.transformation()
            self.mIsCalculated = True
            self.mIsResultValid = self.mTransformVertices is not None
            self.mButtonApply.setEnabled(self.mIsResultValid)
            if self.mIsResultValid:
                points = [self.mTool.toMapCoordinates(self.mInputLayer, QgsPointXY(self.transformedVertex(i))) for i in self.mInputVertices]
                self.mPreview.setToGeometry(QgsGeometry.fromMultiPointXY(points), None)
                self.mPreview.show()
            self.calculationUpdated.emit()
            return self.mIsResultValid
        finally: QApplication.restoreOverrideCursor()

    def preview(self): return self.calculate()

    def apply(self):
        if not self.mIsCalculated or not self.mIsResultValid or self.mInputLayer is not self.mTool.layer(): return False
        if self.mInputVertices != sorted(self.mTool.mSelectedVertices) or not self.mTool.editor():
            self.updateSelection()
            return False
        # Retain the calculated object locally while native meshEdited signals
        # invalidate the dock's cached preview during advancedEdit().
        transform = self.mTransformVertices
        self.aboutToBeApplied.emit()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.mTool.editor().advancedEdit(transform)
            self.mTool.onEdit()
            self.applied.emit()
            return True
        finally: QApplication.restoreOverrideCursor()

    def importCoordinates(self):
        self.mButtonImport.setChecked(True)
        self.importVertexCoordinates()

    def onImportVertexClicked(self, checked):
        if checked: self.importVertexCoordinates()
        else:
            for axis in 'XYZ': getattr(self, 'mExpressionEdit'+axis).setExpression('')

    def displayCoordinateText(self, crs, value):
        # QgsCoordinateUtils is not SIP-exported in 3.34. Match its project
        # precision rule: explicit decimal places, otherwise degrees=8/other=3.
        project = QgsProject.instance()
        if project.readBoolEntry('PositionPrecision', '/Automatic', False)[0]:
            precision = 8 if crs.mapUnits() == Qgis.DistanceUnit.Degrees else 3
        else: precision = project.readNumEntry('PositionPrecision', '/DecimalPlaces', 6)[0]
        precision = max(0, min(precision, 20))
        return format(value, f'.{precision}f') if math.isfinite(value) else ''

    def importVertexCoordinates(self):
        if not self.mButtonImport.isChecked(): return
        vertices = self.mTool.vertices()
        point = vertices.get(self.mInputVertices[0]) if len(self.mInputVertices) == 1 else None
        self.mUpdating = True
        try:
            for axis in 'XYZ':
                text = self.displayCoordinateText(self.mInputLayer.crs(), getattr(point, axis.lower())()) if point is not None else ''
                getattr(self, 'mExpressionEdit'+axis).setExpression(text)
        finally: self.mUpdating = False
        self.updateButton()

    def dispose(self):
        from qgis.PyQt import sip
        self.mTool.canvas().scene().removeItem(self.mPreview)
        sip.delete(self.mPreview)
