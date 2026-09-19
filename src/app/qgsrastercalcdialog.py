"""QgsRasterCalcDialog: original Designer form plus Python controller."""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QProgressDialog
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.core import QgsProject, QgsRectangle, QgsRasterLayer, QgsCoordinateTransform, QgsFeedback, QgsApplication
from qgis.analysis import QgsRasterCalculatorEntry, QgsRasterCalculator, QgsRasterCalcNode
from qgis.gui import QgsFileWidget


class QgsRasterCalcDialog(QDialog):
    def __init__(self, rasterLayer=None, parent=None):
        super().__init__(parent)
        try:
            from src.ui.ui_qgsrastercalcdialogbase import Ui_QgsRasterCalcDialogBase
        except ImportError:
            uic.loadUi(str(Path(__file__).resolve().parents[1] / 'ui/qgsrastercalcdialogbase.ui'), self)
        else:
            ui = Ui_QgsRasterCalcDialogBase()
            ui.setupUi(self)
            self.__dict__.update(vars(ui))
        self.mApp = parent
        self.setObjectName('QgsRasterCalcDialog')
        self.mAvailableRasterBands = QgsRasterCalculatorEntry.rasterEntries()
        self.mOutputLayer.setStorageMode(QgsFileWidget.SaveFile)
        self.mOutputLayer.setFilter('GeoTIFF (*.tif *.tiff)')
        self.mOutputFormatComboBox.addItem('GeoTIFF', 'GTiff')
        self.mUseVirtualProviderCheckBox.setChecked(False)
        self.mUseVirtualProviderCheckBox.setEnabled(False)
        self.mUseVirtualProviderCheckBox.setToolTip('虚拟栅格计算输出尚未移植；当前输出为 GeoTIFF')
        self.mVirtualLayerName.hide()
        self.mVirtualLayerLabel.hide()
        self.mCrsSelector.setCrs(rasterLayer.crs() if isinstance(rasterLayer, QgsRasterLayer) else QgsProject.instance().crs())
        self.mCurrentLayer = rasterLayer
        for entry in self.mAvailableRasterBands: self.mRasterBandsListWidget.addItem(entry.ref)
        self.mRasterBandsListWidget.itemDoubleClicked.connect(lambda item: self.mExpressionTextEdit.insertPlainText('"' + item.text().replace('"', '\\"') + '"'))
        tokens = {'PlusPushButton': '+', 'MinusPushButton': '-', 'MultiplyPushButton': '*', 'DividePushButton': '/',
                  'OpenBracketPushButton': '(', 'CloseBracketPushButton': ')', 'LessButton': '<', 'GreaterButton': '>',
                  'EqualButton': '=', 'LesserEqualButton': '<=', 'GreaterEqualButton': '>=', 'NotEqualButton': '!=',
                  'AndButton': 'AND', 'OrButton': 'OR', 'ConditionalStatButton': 'if('}
        for name in ['Sqrt', 'Cos', 'Sin', 'ASin', 'Exp', 'Ln', 'Log', 'Tan', 'ACos', 'ATan', 'Abs', 'Min', 'Max']:
            tokens[name + 'Button'] = name.lower() + '('
        for name, token in tokens.items(): getattr(self, 'm' + name).clicked.connect(lambda checked=False, value=token: self.mExpressionTextEdit.insertPlainText(' ' + value + ' '))
        self.mCurrentLayerExtentButton.clicked.connect(self.setCurrentLayerExtent)
        self.mExpressionTextEdit.textChanged.connect(self.setAcceptButtonState)
        self.mOutputLayer.fileChanged.connect(self.setAcceptButtonState)
        if isinstance(rasterLayer, QgsRasterLayer): self.setCurrentLayerExtent()
        self.mButtonBox.helpRequested.connect(lambda: self.mApp.mActionHelpContents.trigger())
        self.setAcceptButtonState()

    def formulaString(self): return self.mExpressionTextEdit.toPlainText()
    def outputFile(self):
        path = self.mOutputLayer.filePath()
        return path if Path(path).suffix else path + '.tif'
    def outputFormat(self): return self.mOutputFormatComboBox.currentData()
    def outputCrs(self): return self.mCrsSelector.crs()
    def addLayerToProject(self): return self.mAddResultToProjectCheckBox.isChecked()
    def outputRectangle(self): return QgsRectangle(self.mXMinSpinBox.value(), self.mYMinSpinBox.value(), self.mXMaxSpinBox.value(), self.mYMaxSpinBox.value())
    def numberOfColumns(self): return self.mNColumnsSpinBox.value()
    def numberOfRows(self): return self.mNRowsSpinBox.value()
    def setCurrentLayerExtent(self):
        layer = self.mCurrentLayer
        if not isinstance(layer, QgsRasterLayer): return
        extent = QgsCoordinateTransform(layer.crs(), self.outputCrs(), QgsProject.instance()).transformBoundingBox(layer.extent())
        self.mXMinSpinBox.setValue(extent.xMinimum())
        self.mYMinSpinBox.setValue(extent.yMinimum())
        self.mXMaxSpinBox.setValue(extent.xMaximum())
        self.mYMaxSpinBox.setValue(extent.yMaximum())
        self.mNColumnsSpinBox.setValue(layer.width())
        self.mNRowsSpinBox.setValue(layer.height())
    def expressionValid(self):
        node = QgsRasterCalcNode.parseRasterCalcString(self.formulaString(), '')
        if isinstance(node, tuple): node = node[0]
        return node is not None
    def setAcceptButtonState(self, *args):
        valid = self.expressionValid()
        self.mExpressionValidLabel.setText(QCoreApplication.translate('QgsRasterCalcDialog', 'Expression valid') if valid else QCoreApplication.translate('QgsRasterCalcDialog', 'Expression invalid'))
        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(valid and bool(self.mOutputLayer.filePath()))
    def accept(self):
        if not self.expressionValid() or self.outputRectangle().isEmpty() or min(self.numberOfColumns(), self.numberOfRows()) <= 0:
            QMessageBox.warning(self, QCoreApplication.translate('QgsRasterCalcDialogBase', 'Raster Calculator'), '请检查表达式、输出范围和行列数')
            return
        if Path(self.outputFile()).exists() and QMessageBox.question(self, '覆盖文件', self.outputFile(), QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        progress = QProgressDialog('正在计算…', QCoreApplication.translate('DbManagerDlgSqlWindow', 'Cancel'), 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        feedback = QgsFeedback()
        progress.canceled.connect(feedback.cancel)
        feedback.progressChanged.connect(lambda value: (progress.setValue(int(value)), QgsApplication.processEvents()))
        progress.show()
        result, error = self.calculate(feedback)
        progress.close()
        if result != QgsRasterCalculator.Success:
            QMessageBox.warning(self, '栅格计算失败', error or str(result))
            return
        if self.addLayerToProject(): self.mApp.addRasterLayer(self.outputFile())
        super().accept()
    def calculate(self, feedback=None):
        calculator = QgsRasterCalculator(self.formulaString(), self.outputFile(), self.outputFormat(), self.outputRectangle(), self.outputCrs(), self.numberOfColumns(), self.numberOfRows(), self.mAvailableRasterBands, QgsProject.instance().transformContext())
        result = calculator.processCalculation(feedback)
        return result, calculator.lastError()
