"""Original qgsmeasurebase.ui with ellipsoidal measurements and unit conversion."""
import math
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QTreeWidgetItem
from qgis.core import Qgis, QgsDistanceArea, QgsProject, QgsSettings, QgsUnitTypes, QgsApplication


class QgsMeasureDialog(QDialog):
    def __init__(self, tool):
        super().__init__(tool.mApp, Qt.Tool)
        uic.loadUi(str(Path(__file__).resolve().parents[1] / 'ui/qgsmeasurebase.ui'), self)
        self.mTool = tool
        self.mMeasureArea = tool.measureArea()
        self.mDa = QgsDistanceArea()
        self.mLastPoints, self.mMeasurements, self.mTotal = [], [], 0
        self.setObjectName('QgsMeasureDialog')
        titles = {'distance': '测量距离', 'area': '测量面积', 'angle': '测量角度', 'bearing': '测量方位角'}
        self.setWindowTitle(titles[tool.mMeasureMode])
        self.editHorizontalTotal.hide()
        self.totalHorizontalDistanceLabel.hide()
        self.editTotal.setReadOnly(True)
        self.mTable.setHeaderLabels(['分段', '测量值'])
        self.mEllipsoidal.setChecked(True)
        if tool.mMeasureMode in ('angle', 'bearing'):
            choices = [('度', 'degrees'), ('弧度', 'radians'), ('百分度', 'gon')]
        elif self.mMeasureArea:
            choices = [(QgsUnitTypes.toString(unit), unit) for unit in (Qgis.AreaUnit.SquareMeters, Qgis.AreaUnit.SquareKilometers, Qgis.AreaUnit.Hectares, Qgis.AreaUnit.Acres, Qgis.AreaUnit.SquareFeet)]
        else:
            choices = [(QgsUnitTypes.toString(unit), unit) for unit in (Qgis.DistanceUnit.Meters, Qgis.DistanceUnit.Kilometers, Qgis.DistanceUnit.Feet, Qgis.DistanceUnit.Miles, Qgis.DistanceUnit.NauticalMiles)]
        self.mUnitsCombo.clear()
        for label, value in choices: self.mUnitsCombo.addItem(label, value)
        self.buttonBox.addButton(QCoreApplication.translate('QgsAppDirectoryItemGuiProvider', 'New'), QDialogButtonBox.ActionRole).clicked.connect(tool.restart)
        self.buttonBox.addButton(QCoreApplication.translate('QgsMeasureDialog', 'Copy'), QDialogButtonBox.ActionRole).clicked.connect(self.copyMeasurements)
        self.buttonBox.addButton(QCoreApplication.translate('QgsAuthConfigEditor', 'Config'), QDialogButtonBox.ActionRole).clicked.connect(lambda: tool.mApp.options('地图工具'))
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.helpRequested.connect(lambda: tool.mApp.mActionHelpContents.trigger())
        self.mUnitsCombo.currentIndexChanged.connect(lambda: self.updateMeasurements(self.mLastPoints))
        self.mEllipsoidal.toggled.connect(lambda: self.updateMeasurements(self.mLastPoints))
        self.resize(380, 400)

    def updateMeasurements(self, points):
        self.mLastPoints = list(points)
        project = QgsProject.instance()
        self.mDa.setSourceCrs(self.mTool.canvas().mapSettings().destinationCrs(), project.transformContext())
        self.mDa.setEllipsoid(project.ellipsoid() if self.mEllipsoidal.isChecked() else 'NONE')
        decimals = QgsSettings().value('qgis/measure/decimalplaces', 3, type=int)
        self.mTable.clear()
        self.mMeasurements = []
        mode, unit = self.mTool.mMeasureMode, self.mUnitsCombo.currentData()
        if mode in ('angle', 'bearing'):
            value = 0
            if mode == 'angle' and len(points) >= 3:
                a, b, c = points[-3:]
                value = self.mDa.bearing(b, c) - self.mDa.bearing(b, a)
                value = (value + math.pi) % (2 * math.pi) - math.pi
            elif mode == 'bearing' and len(points) >= 2:
                value = self.mDa.bearing(points[0], points[-1]) % (2 * math.pi)
            self.mTotal = value if unit == 'radians' else value * (200 / math.pi if unit == 'gon' else 180 / math.pi)
        elif self.mMeasureArea:
            value = self.mDa.measurePolygon(points) if len(points) >= 3 else 0
            self.mTotal = self.mDa.convertAreaMeasurement(value, unit)
        else:
            for a, b in zip(points, points[1:]):
                self.mMeasurements.append(self.mDa.convertLengthMeasurement(self.mDa.measureLine(a, b), unit))
            self.mTotal = sum(self.mMeasurements)
        for index, value in enumerate(self.mMeasurements, 1): QTreeWidgetItem(self.mTable, [str(index), f'{value:.{decimals}f}'])
        self.editTotal.setText(f'{self.mTotal:.{decimals}f}')
        self.mNotesLabel.setText(f'CRS: {self.mTool.canvas().mapSettings().destinationCrs().authid()}；椭球: {self.mDa.ellipsoid()}\n左键添加点，右键结束并保留结果；Backspace 撤销，Esc 重新开始。')
    def copyMeasurements(self):
        text = '\n'.join(f'{index}\t{value:.8f}' for index, value in enumerate(self.mMeasurements, 1))
        QgsApplication.clipboard().setText(text + f'\n总计\t{self.mTotal:.8f}\t{self.mUnitsCombo.currentText()}')
    def reject(self):
        self.mTool.restart()
        super().reject()
