from qgis.PyQt.QtCore import QCoreApplication
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QAction
from qgis.core import Qgis, QgsMesh, QgsExpressionContext, QgsExpressionContextUtils, QgsApplication, QgsSettings
from qgis.gui import QgsExpressionBuilderWidget, QgsHelp


class QgsMeshSelectByExpressionDialog(QDialog):
    def __init__(self, tool, parent=None):
        super().__init__(parent)
        self.mTool = tool
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/mesh/qgsmeshselectbyexpressiondialogbase.ui'), self)
        self.setWindowTitle('按表达式选择网孔元素')
        for name, title, icon, behavior in (
            ('mActionSelect', '选择', '/mIconExpressionSelect.svg', Qgis.SelectBehavior.SetSelection),
            ('mActionAddToSelection', '添加到选择', '/mIconSelectAdd.svg', Qgis.SelectBehavior.AddToSelection),
            ('mActionRemoveFromSelection', '从选择中移除', '/mIconSelectRemove.svg', Qgis.SelectBehavior.RemoveFromSelection)):
            action = QAction(QgsApplication.getThemeIcon(icon), title, self)
            action.triggered.connect(lambda checked=False, b=behavior: self.select(b))
            setattr(self, name, action)
            self.mButtonSelect.addAction(action)
        self.mButtonSelect.setDefaultAction(self.mActionSelect)
        self.mComboBoxElementType.addItem(QCoreApplication.translate('Line3DSymbolWidget', 'Vertex'), QgsMesh.Vertex)
        self.mComboBoxElementType.addItem('面', QgsMesh.Face)
        index = self.mComboBoxElementType.findData(QgsSettings().value('/meshSelection/elementType', int(QgsMesh.Vertex), type=int))
        self.mComboBoxElementType.setCurrentIndex(max(index, 0))
        self.mComboBoxElementType.currentIndexChanged.connect(self.onElementTypeChanged)
        self.mButtonClose.clicked.connect(self.close)
        self.mButtonZoomToSelected.clicked.connect(tool.zoomToSelected)
        self.buttonBox.helpRequested.connect(lambda: QgsHelp.openHelp('working_with_mesh/mesh_properties.html#select-mesh-elements'))
        self.mExpressionBuilder.setExpressionPreviewVisible(False)
        self.onElementTypeChanged()

    def onElementTypeChanged(self):
        element = self.mComboBoxElementType.currentData()
        QgsSettings().setValue('/meshSelection/elementType', element)
        context = QgsExpressionContext([QgsExpressionContextUtils.meshExpressionScope(element)])
        self.mExpressionBuilder.init(context, 'mesh_vertex_selection', QgsExpressionBuilderWidget.LoadAll)

    def select(self, behavior):
        text = self.mExpressionBuilder.expressionText()
        if self.mTool.selectByExpression(text, behavior, self.mComboBoxElementType.currentData()):
            self.mExpressionBuilder.expressionTree().saveToRecent(text, 'mesh_vertex_selection')
