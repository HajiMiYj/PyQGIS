from qgis.PyQt.QtCore import QCoreApplication
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMessageBox
from qgis.core import Qgis
from qgis.gui import QgsGui, QgsHelp


class QgsDecorationGridDialog(QDialog):
    def __init__(self, deco, parent=None):
        super().__init__(parent)
        self.mDeco = deco
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/qgsdecorationgriddialog.ui'), self)
        QgsGui.enableAutoGeometryRestore(self)
        for text, value in [('线', deco.Line), ('标记', deco.Marker)]: self.mGridTypeComboBox.addItem(text, value)
        for text in ('水平', '垂直', '水平和垂直', '沿边界'): self.mAnnotationDirectionComboBox.addItem(text)
        self.grpEnable.setChecked(deco.enabled())
        for key in ('IntervalX', 'IntervalY', 'OffsetX', 'OffsetY'): getattr(self, 'm' + key + 'Edit').setValue(getattr(deco, 'mGrid' + key))
        self.mGridTypeComboBox.setCurrentIndex(self.mGridTypeComboBox.findData(deco.mGridStyle))
        self.mDrawAnnotationCheckBox.setChecked(deco.mShowGridAnnotation)
        self.mAnnotationDirectionComboBox.setCurrentIndex(deco.mGridAnnotationDirection)
        self.mDistanceToMapFrameSpinBox.setValue(deco.mAnnotationFrameDistance)
        self.mCoordinatePrecisionSpinBox.setValue(deco.mGridAnnotationPrecision)
        self.mAnnotationFontButton.setTextFormat(deco.mTextFormat)
        self.mAnnotationFontButton.setMapCanvas(deco.mApp.mMapCanvas)
        for button, symbol, kind in ((self.mLineSymbolButton, deco.mLineSymbol, Qgis.SymbolType.Line),
                                     (self.mMarkerSymbolButton, deco.mMarkerSymbol, Qgis.SymbolType.Marker)):
            button.setSymbolType(kind)
            button.setSymbol(symbol.clone())
            button.setMapCanvas(deco.mApp.mMapCanvas)
            button.setMessageBar(deco.mApp.mMessageBar)
        self.mGridTypeComboBox.currentIndexChanged.connect(self.updateSymbolButtons)
        self.grpEnable.toggled.connect(self.updateSymbolButtons)
        self.mPbtnUpdateFromExtents.clicked.connect(lambda: self.updateInterval(True))
        self.mPbtnUpdateFromLayer.clicked.connect(self.mPbtnUpdateFromLayer_clicked)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        self.buttonBox.helpRequested.connect(lambda: QgsHelp.openHelp('map_views/map_view.html#grid-decoration'))
        self.updateInterval(False)
        self.updateSymbolButtons()

    def updateSymbolButtons(self, *args):
        marker = self.mGridTypeComboBox.currentData() == self.mDeco.Marker
        for widget in (self.mMarkerSymbolFrame, self.mMarkerSymbolButton, self.mMarkerSymbolLabel): widget.setVisible(marker)
        for widget in (self.mLineSymbolButton, self.mLineSymbolLabel): widget.setVisible(not marker)

    def setIntervals(self, values):
        if values is None: return
        for key, value in zip(('IntervalX', 'IntervalY', 'OffsetX', 'OffsetY'), values): getattr(self, 'm' + key + 'Edit').setValue(value)
        self.mCoordinatePrecisionSpinBox.setValue(0 if values[0] >= 1 else 3)

    def updateInterval(self, force=False):
        if force or self.mDeco.isDirty(): self.setIntervals(self.mDeco.getIntervalFromExtent())

    def mPbtnUpdateFromLayer_clicked(self):
        try: self.setIntervals(self.mDeco.getIntervalFromCurrentLayer())
        except ValueError as error: QMessageBox.warning(self, QCoreApplication.translate('QgsDecorationGrid', 'Get Interval from Layer'), str(error))

    def apply(self):
        if self.grpEnable.isChecked() and (self.mIntervalXEdit.value() <= 0 or self.mIntervalYEdit.value() <= 0):
            QMessageBox.warning(self, QCoreApplication.translate('QgsDecorationGrid', 'Grid'), 'X 和 Y 间隔必须大于零。')
            return False
        deco = self.mDeco
        deco.setEnabled(self.grpEnable.isChecked())
        deco.setDirty(False)
        for key in ('IntervalX', 'IntervalY', 'OffsetX', 'OffsetY'): setattr(deco, 'mGrid' + key, getattr(self, 'm' + key + 'Edit').value())
        deco.mGridStyle = self.mGridTypeComboBox.currentData()
        deco.mShowGridAnnotation = self.mDrawAnnotationCheckBox.isChecked()
        deco.mGridAnnotationDirection = self.mAnnotationDirectionComboBox.currentIndex()
        deco.mAnnotationFrameDistance = self.mDistanceToMapFrameSpinBox.value()
        deco.mGridAnnotationPrecision = self.mCoordinatePrecisionSpinBox.value()
        deco.mTextFormat = self.mAnnotationFontButton.textFormat()
        deco.mLineSymbol = self.mLineSymbolButton.symbol().clone()
        deco.mMarkerSymbol = self.mMarkerSymbolButton.symbol().clone()
        deco.update()
        return True

    def accept(self):
        if self.apply(): super().accept()
