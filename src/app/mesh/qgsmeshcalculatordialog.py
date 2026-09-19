"""QGIS 3.34 mesh calculator: original UI, native persistent/virtual calculation."""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QProgressDialog
from qgis.core import (Qgis, QgsProject, QgsApplication, QgsSettings, QgsMeshCalculator,
                       QgsMeshDriverMetadata, QgsMeshDatasetGroup, QgsMeshDatasetIndex,
                       QgsMeshDatasetGroupMetadata, QgsProviderRegistry, QgsRectangle,
                       QgsGeometry, QgsCoordinateTransform, QgsFeedback)
from qgis.gui import QgsGui, QgsFileWidget, QgsHelp
from src.gui.mesh.qgsmeshdatasetgrouptreeview import QgsMeshDatasetGroupListModel

# QgsMeshLayer::datasetRelativeTimeInMilliseconds() reports datasets without a
# usable time as native INVALID_MESHLAYER_TIME; MDAL additionally returns its own
# negative sentinel (observed -99999). Native only guards the first form, which
# leaves a duplicate entry in the combos, so skip both.
INVALID_MESHLAYER_TIME = 9223372036854775807


class QgsMeshCalculatorDialog(QDialog):
    def __init__(self, meshLayer, parent=None):
        super().__init__(parent)
        self.mLayer = meshLayer
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/mesh/qgsmeshcalculatordialogbase.ui'), self)
        QgsGui.enableAutoGeometryRestore(self)
        self.mModel = QgsMeshDatasetGroupListModel(self)
        self.mModel.syncToLayer(meshLayer)
        self.mModel.setDisplayProviderName(True)
        self.mDatasetsListWidget.setModel(self.mModel)
        self.mVariableNames = self.mModel.variableNames()
        self.mMeshDrivers = {}
        metadata = QgsProviderRegistry.instance().providerMetadata('mdal')
        if metadata:
            for driver in metadata.meshDriversMetadata():
                if driver.capabilities() & (QgsMeshDriverMetadata.CanWriteFaceDatasets | QgsMeshDriverMetadata.CanWriteVertexDatasets | QgsMeshDriverMetadata.CanWriteEdgeDatasets):
                    self.mMeshDrivers[driver.name()] = driver
                    self.mOutputFormatComboBox.addItem(driver.description(), driver.name())
        self.cboLayerMask.setFilters(Qgis.LayerFilter.PolygonLayer)
        self.cboLayerMask.layerChanged.connect(self.updateInfoMessage)
        self.cboLayerMask.layerChanged.connect(self.updateMaskAvailability)
        self.mOutputDatasetFileWidget.setStorageMode(QgsFileWidget.SaveFile)
        self.mOutputDatasetFileWidget.setDialogTitle('输入网格数据集文件')
        self.mOutputDatasetFileWidget.setDefaultRoot(QgsSettings().value('MeshCalculator/lastOutputDir', str(Path.home())))
        self.mDatasetsListWidget.doubleClicked.connect(self.datasetGroupEntry)
        self.mCurrentLayerExtentButton.clicked.connect(self.useFullLayerExtent)
        self.mAllTimesButton.clicked.connect(self.useAllTimesFromLayer)
        self.mExpressionTextEdit.setCurrentFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.mExpressionTextEdit.textChanged.connect(self.updateInfoMessage)
        self.mOutputGroupNameLineEdit.textChanged.connect(self.updateInfoMessage)
        self.mOutputDatasetFileWidget.fileChanged.connect(self.updateInfoMessage)
        self.mOutputFormatComboBox.currentIndexChanged.connect(self.onOutputFormatChange)
        self.mUseVirtualProviderCheckBox.toggled.connect(self.onVirtualCheckboxChange)
        self.useMaskCb.toggled.connect(self.toggleExtendMask)
        tokens = {'PlusPushButton': '+', 'MinusPushButton': '-', 'MultiplyPushButton': '*', 'DividePushButton': '/',
                  'OpenBracketPushButton': '(', 'CloseBracketPushButton': ')', 'LessButton': '<', 'GreaterButton': '>',
                  'EqualButton': '=', 'LesserEqualButton': '<=', 'GreaterEqualButton': '>=', 'NotEqualButton': '!=',
                  'MinButton': 'min( A , B )', 'MaxButton': 'max( A , B )', 'AbsButton': 'abs(', 'PowButton': '^',
                  'IfButton': 'if( 1 = 1 , NODATA , NODATA )', 'AndButton': 'and', 'OrButton': 'or', 'NotButton': 'not',
                  'SumAggrButton': 'sum_aggr(', 'MaxAggrButton': 'max_aggr(', 'MinAggrButton': 'min_aggr(',
                  'AverageAggrButton': 'average_aggr(', 'NoDataButton': 'NODATA'}
        for name, token in tokens.items():
            getattr(self, 'm' + name).clicked.connect(lambda checked=False, token=token: self.mExpressionTextEdit.insertPlainText(' ' + token + ' '))
        for widget in (self.mXMinSpinBox, self.mYMinSpinBox, self.mXMaxSpinBox, self.mYMaxSpinBox):
            widget.setShowClearButton(False)
            widget.valueChanged.connect(self.updateInfoMessage)
        self.useFullLayerExtent()
        self.repopulateTimeCombos()
        self.mStartTimeComboBox.currentIndexChanged.connect(self.updateInfoMessage)
        self.mEndTimeComboBox.currentIndexChanged.connect(self.updateInfoMessage)
        self.mButtonBox.helpRequested.connect(lambda: QgsHelp.openHelp('working_with_mesh/mesh_properties.html#mesh-calculator'))
        self.onOutputFormatChange()
        self.onVirtualCheckboxChange()
        self.toggleExtendMask()
        # Native leaves the mask page hidden and the mask switch unavailable
        # until a polygon layer exists, and keeps OK disabled before any input.
        self.maskBox.setVisible(False)
        self.useMaskCb.setEnabled(bool(self.cboLayerMask.count()))
        self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(False)

    def updateMaskAvailability(self, *args):
        self.useMaskCb.setEnabled(bool(self.cboLayerMask.count()))

    def formulaString(self): return self.mExpressionTextEdit.toPlainText()
    def meshLayer(self): return self.mLayer
    def driver(self): return self.mOutputFormatComboBox.currentData()
    def groupName(self): return self.mOutputGroupNameLineEdit.text()
    def startTime(self):
        index = self.mStartTimeComboBox.currentIndex()
        return float(self.mStartTimeComboBox.itemData(index)) if index > -1 else 0.0
    def endTime(self):
        index = self.mEndTimeComboBox.currentIndex()
        return float(self.mEndTimeComboBox.itemData(index)) if index > -1 else 0.0
    def outputExtent(self): return QgsRectangle(self.mXMinSpinBox.value(), self.mYMinSpinBox.value(), self.mXMaxSpinBox.value(), self.mYMaxSpinBox.value())
    def datasetGroupName(self, index):
        return index.data(Qt.DisplayRole) if index.isValid() else ''
    def currentDatasetGroup(self):
        return self.datasetGroupName(self.mDatasetsListWidget.currentIndex())
    def currentOutputSuffix(self):
        driver = self.mMeshDrivers.get(self.driver())
        return driver.writeDatasetOnFileSuffix() if driver else ''
    def controlSuffix(self, fileName):
        """Native controlSuffix(): only replace a suffix that is wrong.

        Native assumes the path already carries a suffix; for an extension-less
        path it truncates the name away entirely, so keep that degenerate case
        by appending instead of replacing.
        """
        if not fileName:
            return fileName
        appropriate, existing = self.currentOutputSuffix(), Path(fileName).suffix.lstrip('.')
        if (existing or appropriate) and existing != appropriate:
            prefix = fileName[:fileName.rfind('.') + 1] if existing else fileName + '.'
            return prefix + appropriate
        return fileName
    def outputFile(self):
        return self.controlSuffix(self.mOutputDatasetFileWidget.filePath())

    def datasetGroupEntry(self, index):
        self.mExpressionTextEdit.insertPlainText(' "' + index.data().replace('"', '\\"') + '" ')

    def useFullLayerExtent(self):
        # Native guards a null layer: the dialog opens from the menu even when the
        # project has no mesh layer at all.
        if self.mLayer is None:
            return
        extent = self.mLayer.extent()
        for widget, value in [(self.mXMinSpinBox, extent.xMinimum()), (self.mYMinSpinBox, extent.yMinimum()),
                              (self.mXMaxSpinBox, extent.xMaximum()), (self.mYMaxSpinBox, extent.yMaximum())]: widget.setValue(value)

    def repopulateTimeCombos(self):
        """Native repopulateTimeCombos(): key on relative milliseconds, skip invalid."""
        layer = self.mLayer
        if layer is None:
            return
        times = {}
        for group in layer.datasetGroupsIndexes():
            for dataset in range(layer.datasetCount(QgsMeshDatasetIndex(group, 0))):
                index = QgsMeshDatasetIndex(group, dataset)
                milliseconds = layer.datasetRelativeTimeInMilliseconds(index)
                if milliseconds == INVALID_MESHLAYER_TIME or milliseconds < 0: continue
                times[milliseconds] = layer.datasetMetadata(index).time()
        for combo in (self.mStartTimeComboBox, self.mEndTimeComboBox):
            combo.blockSignals(True)
            combo.clear()
        for milliseconds in sorted(times):
            for combo in (self.mStartTimeComboBox, self.mEndTimeComboBox):
                combo.addItem(self.mLayer.formatTime(times[milliseconds]), times[milliseconds])
        for combo in (self.mStartTimeComboBox, self.mEndTimeComboBox):
            combo.blockSignals(False)
        if times:
            self.mStartTimeComboBox.setCurrentIndex(0)
            self.mEndTimeComboBox.setCurrentIndex(len(times) - 1)

    def useAllTimesFromLayer(self):
        self.setTimesByDatasetGroupName(self.currentDatasetGroup())

    def setTimesByDatasetGroupName(self, group):
        """Native setTimesByDatasetGroupName(), resolved through the dataset group index."""
        if self.mLayer is None: return
        index = self.mDatasetsListWidget.currentIndex()
        groupIndex = index.data(Qt.UserRole) if index.isValid() else None
        if groupIndex is None and group:
            for candidate in self.mLayer.datasetGroupsIndexes():
                if self.mLayer.datasetGroupMetadata(QgsMeshDatasetIndex(candidate, 0)).name() == group:
                    groupIndex = candidate
                    break
        if groupIndex is None: return
        count = self.mLayer.datasetCount(QgsMeshDatasetIndex(groupIndex, 0))
        if count < 1: return
        start = self.mStartTimeComboBox.findData(self.mLayer.datasetMetadata(QgsMeshDatasetIndex(groupIndex, 0)).time())
        if start >= 0: self.mStartTimeComboBox.setCurrentIndex(start)
        end = self.mEndTimeComboBox.findData(self.mLayer.datasetMetadata(QgsMeshDatasetIndex(groupIndex, count - 1)).time())
        if end >= 0: self.mEndTimeComboBox.setCurrentIndex(end)

    def toggleExtendMask(self, *args):
        self.maskBox.setVisible(self.useMaskCb.isChecked())
        self.extendBox.setVisible(not self.useMaskCb.isChecked())
        self.updateInfoMessage()

    def onVirtualCheckboxChange(self, *args):
        for widget in (self.mOutputDatasetFileWidget, self.mOutputDatasetFileLabel, self.mOutputFormatComboBox, self.mOutputFormatLabel):
            widget.setVisible(not self.mUseVirtualProviderCheckBox.isChecked())
        self.updateInfoMessage()

    def onOutputFormatChange(self, *args):
        suffix = self.currentOutputSuffix()
        if suffix:
            self.mOutputDatasetFileWidget.setFilter(self.mOutputFormatComboBox.currentText() + ' (*.' + suffix + ')')
            path = self.mOutputDatasetFileWidget.filePath()
            if path: self.mOutputDatasetFileWidget.setFilePath(self.controlSuffix(path))
        else:
            self.mOutputDatasetFileWidget.setFilter('所有文件 (*)')
        self.updateInfoMessage()

    def expressionState(self):
        # PyQGIS returns the C++ reference output as the second tuple member.
        try:
            return QgsMeshCalculator.expressionIsValid(self.formulaString(), self.mLayer)
        except RuntimeError:
            # The dialog can outlive its layer (project closed, layer removed);
            # treat that as an unusable input instead of raising from a signal.
            return QgsMeshCalculator.InputLayerError, QgsMeshDriverMetadata.CanWriteVertexDatasets

    def updateInfoMessage(self, *args):
        """Native updateInfoMessage(): same checks and same precedence."""
        result, capability = self.expressionState()
        expressionValid = result == QgsMeshCalculator.Success
        notInFile = self.mUseVirtualProviderCheckBox.isChecked()

        driverValid = False
        if expressionValid:
            driver = self.mMeshDrivers.get(self.driver())
            driverValid = bool(driver) and bool(driver.capabilities() & capability)
        else:
            # Cannot judge the driver while the expression does not parse.
            driverValid = True

        output = self.outputFile()
        filePathValid = bool(output) and Path(output).absolute().parent.is_dir()
        groupNameValid = bool(self.groupName()) and self.groupName() not in self.mVariableNames

        if expressionValid and (notInFile or (driverValid and filePathValid)) and groupNameValid:
            self.mExpressionValidLabel.setText(QCoreApplication.translate('QgsMeshCalculatorDialog', 'Expression valid'))
            self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(True)
        else:
            self.mButtonBox.button(QDialogButtonBox.Ok).setEnabled(False)
            if not expressionValid:
                self.mExpressionValidLabel.setText(QCoreApplication.translate('QgsMeshCalculatorDialog', 'Expression invalid'))
            elif not filePathValid and not notInFile:
                self.mExpressionValidLabel.setText('输出路径无效')
            elif not driverValid and not notInFile:
                self.mExpressionValidLabel.setText('所选格式不能保存定义在' +
                                                   ('面上的' if capability == QgsMeshDriverMetadata.CanWriteFaceDatasets else '顶点上的') + '数据')
            elif not groupNameValid:
                self.mExpressionValidLabel.setText('结果组名称为空或已存在')
            else:
                self.mExpressionValidLabel.setText('输入无效')

    def maskGeometry(self):
        layer = self.cboLayerMask.currentLayer()
        if not layer or self.mLayer is None: raise ValueError('请选择掩膜图层')
        transform = QgsCoordinateTransform(layer.crs(), self.mLayer.crs(), QgsProject.instance())
        geometries = []
        for feature in layer.getFeatures():
            geometry = feature.geometry()
            if geometry.isEmpty(): continue
            geometry.transform(transform)
            geometries.append(geometry)
        mask = QgsGeometry.unaryUnion(geometries)
        if mask.isEmpty() or mask.isNull(): raise ValueError('掩膜没有可用的多边形')
        return mask

    def calculator(self):
        mask = self.maskGeometry() if self.useMaskCb.isChecked() else self.outputExtent()
        if self.mUseVirtualProviderCheckBox.isChecked():
            return QgsMeshCalculator(self.formulaString(), self.groupName(), mask, QgsMeshDatasetGroup.Virtual, self.mLayer, self.startTime(), self.endTime())
        return QgsMeshCalculator(self.formulaString(), self.driver(), self.groupName(), self.outputFile(), mask, self.startTime(), self.endTime(), self.mLayer)

    def calculate(self, feedback=None):
        self.updateInfoMessage()
        if not self.mButtonBox.button(QDialogButtonBox.Ok).isEnabled(): raise ValueError(self.mExpressionValidLabel.text())
        # Native spatial filtering dereferences the triangular mesh. A freshly
        # loaded/hidden layer may never have been rendered; build it explicitly.
        self.mLayer.updateTriangularMesh()
        result = self.calculator().processCalculation(feedback)
        if result == QgsMeshCalculator.Success:
            QgsProject.instance().setDirty(True)
            self.mLayer.triggerRepaint()
            self.mModel.syncToLayer(self.mLayer)
            self.mVariableNames = self.mModel.variableNames()
            if not self.mUseVirtualProviderCheckBox.isChecked(): QgsSettings().setValue('MeshCalculator/lastOutputDir', str(Path(self.outputFile()).parent))
        return result

    def accept(self):
        self.updateInfoMessage()
        if not self.mButtonBox.button(QDialogButtonBox.Ok).isEnabled(): return
        if not self.mUseVirtualProviderCheckBox.isChecked() and Path(self.outputFile()).exists():
            QMessageBox.warning(self, '输出文件已存在', '请选择新文件名，以免覆盖网格已经引用的数据集。')
            return
        progress = QProgressDialog('正在计算网格表达式…', QCoreApplication.translate('DbManagerDlgSqlWindow', 'Cancel'), 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        feedback = QgsFeedback()
        progress.canceled.connect(feedback.cancel)
        feedback.progressChanged.connect(lambda value: (progress.setValue(int(value)), QgsApplication.processEvents()))
        progress.show()
        try:
            result = self.calculate(feedback)
            if result == QgsMeshCalculator.Canceled: return
            if result != QgsMeshCalculator.Success:
                errors = {QgsMeshCalculator.CreateOutputError: '无法创建输出', QgsMeshCalculator.InputLayerError: '输入图层无效',
                          QgsMeshCalculator.InvalidDatasets: '数据集无效或不兼容', QgsMeshCalculator.ParserError: '表达式解析失败',
                          QgsMeshCalculator.EvaluateError: '表达式计算失败', QgsMeshCalculator.MemoryError: '内存不足'}
                raise RuntimeError(errors.get(result, str(result)))
        except Exception as error:
            QMessageBox.warning(self, '网格计算失败', str(error))
            return
        finally:
            progress.close()
        super().accept()
