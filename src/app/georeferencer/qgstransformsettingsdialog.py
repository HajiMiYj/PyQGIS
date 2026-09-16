from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.core import QgsCoordinateReferenceSystem
from qgis.gui import QgsFileWidget
from .qgsgeoreftransform import QgsGeorefTransform


class QgsTransformSettingsDialog(QDialog):
    def __init__(self, settings, raster, parent=None):
        super().__init__(parent)
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/georeferencer/qgstransformsettingsdialogbase.ui'), self)
        self.mSettings = dict(settings)
        self.mRaster = raster
        method = QgsGeorefTransform.Method
        for label, value in [('线性（仅平移与缩放）', method.Linear), ('Helmert', method.Helmert),
                             ('一阶多项式', method.PolynomialOrder1), ('二阶多项式', method.PolynomialOrder2),
                             ('三阶多项式', method.PolynomialOrder3), ('薄板样条 TPS', method.ThinPlateSpline),
                             ('投影变换', method.Projective)]:
            self.cmbTransformType.addItem(label, value)
        if raster:
            self.cmbTransformType.model().item(6).setEnabled(False)
            self.cmbTransformType.setToolTip('栅格投影变换的自定义重采样回调尚未移植；其他列出的栅格变换可用。')
        self.cmbTransformType.setCurrentIndex(max(0, self.cmbTransformType.findData(settings['method'])))
        for label, value in [('最近邻', 'near'), ('双线性', 'bilinear'), ('三次卷积', 'cubic'), ('三次样条', 'cubicspline'), ('Lanczos', 'lanczos')]:
            self.cmbResampling.addItem(label, value)
        self.cmbResampling.setCurrentIndex(max(0, self.cmbResampling.findData(settings['resampling'])))
        self.cmbCompressionComboBox.addItems(['NONE', 'LZW', 'DEFLATE', 'PACKBITS'])
        self.cmbCompressionComboBox.setCurrentText(settings['compression'])
        self.mCrsSelector.setCrs(settings['crs'])
        self.mOutputSettingsStackedWidget.setCurrentIndex(0 if raster else 1)
        for widget, filterText in ((self.mRasterOutputFile, 'GeoTIFF (*.tif)'), (self.mVectorOutputFile, 'GeoPackage (*.gpkg)')):
            widget.setStorageMode(QgsFileWidget.SaveFile)
            widget.setFilter(filterText)
            widget.setConfirmOverwrite(False)
            widget.setFilePath(settings['output'])
        self.cbxLoadInProjectsWhenDone.setChecked(settings['load'])
        self.saveGcpCheckBox.setChecked(settings['saveGcp'])
        self.cbxZeroAsTrans.setChecked(settings['zero'])
        self.cbxUserResolution.setChecked(bool(settings['resolution']))
        if settings['resolution']:
            self.dsbHorizRes.setValue(settings['resolution'][0])
            self.dsbVerticalRes.setValue(-abs(settings['resolution'][1]))
        self.mWorldFileCheckBox.setChecked(settings['worldfile'])
        self.cmbTransformType.currentIndexChanged.connect(self.updateWorldFile)
        self.mWorldFileCheckBox.toggled.connect(self.updateWorldFile)
        self.groupBox_3.setEnabled(False)
        self.groupBox_3.setToolTip('PDF 地图与完整配准报告尚未移植。')
        self.updateWorldFile()

    def updateWorldFile(self, *unused):
        enabled = self.mRaster and self.cmbTransformType.currentData() == QgsGeorefTransform.Method.Linear
        self.mWorldFileCheckBox.setEnabled(enabled)
        if not enabled: self.mWorldFileCheckBox.setChecked(False)
        self.mRasterOutputFile.setEnabled(not self.mWorldFileCheckBox.isChecked())

    def accept(self):
        output = (self.mRasterOutputFile if self.mRaster else self.mVectorOutputFile).filePath()
        if not self.mCrsSelector.crs().isValid():
            QMessageBox.warning(self, '变换设置', '请选择有效的目标 CRS'); return
        if not self.mWorldFileCheckBox.isChecked() and not output:
            QMessageBox.warning(self, '变换设置', '请选择输出文件'); return
        # The native UI uses negative vertical pixel size; GDAL xRes/yRes
        # take positive magnitudes.
        resolution = (self.dsbHorizRes.value(), abs(self.dsbVerticalRes.value())) if self.cbxUserResolution.isChecked() and self.mRaster else None
        if resolution and min(resolution) <= 0:
            QMessageBox.warning(self, '变换设置', '目标分辨率必须为正数'); return
        self.mSettings.update(method=self.cmbTransformType.currentData(), crs=QgsCoordinateReferenceSystem(self.mCrsSelector.crs()),
                              output=output, resampling=self.cmbResampling.currentData(), compression=self.cmbCompressionComboBox.currentText(),
                              load=self.cbxLoadInProjectsWhenDone.isChecked(), saveGcp=self.saveGcpCheckBox.isChecked(),
                              zero=self.cbxZeroAsTrans.isChecked(), resolution=resolution, worldfile=self.mWorldFileCheckBox.isChecked())
        super().accept()
