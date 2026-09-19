"""Original Designer form with the application-side slots from QGIS 3.34."""
from qgis.PyQt.QtCore import QCoreApplication
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox
from qgis.core import Qgis, QgsTextFormat
from qgis.gui import QgsExpressionBuilderDialog, QgsHelp, QgsGui

UI_ROOT = Path(__file__).resolve().parents[2] / 'ui'


class QgsDecorationTitleDialog(QDialog):
    uiName = 'qgsdecorationtitledialog.ui'
    helpAnchor = 'titlelabel-decoration'
    textWidgetName = 'txtTitleText'

    def __init__(self, decoration, parent):
        super().__init__(parent)
        self.mDeco = decoration
        uic.loadUi(str(UI_ROOT / self.uiName), self)
        QgsGui.enableAutoGeometryRestore(self)
        self.initPlacement()
        self.mTextEdit = getattr(self, self.textWidgetName)
        self.mTextEdit.setPlainText(decoration.mLabelText or (self.defaultText() if not decoration.enabled() else ''))
        self.mButtonFontStyle.setMapCanvas(parent.mMapCanvas)
        self.mButtonFontStyle.setTextFormat(decoration.mTextFormat)
        self.mButtonFontStyle.setDialogTitle(QCoreApplication.translate('QObject', 'Text Format'))
        self.mInsertExpressionButton.clicked.connect(self.insertExpression)
        if decoration.hasBackground:
            self.pbnBackgroundColor.setAllowOpacity(True)
            self.pbnBackgroundColor.setColor(decoration.mBackgroundColor)
        self.connectButtons()

    def initPlacement(self):
        deco = self.mDeco
        self.grpEnable.setChecked(deco.enabled())
        self.cboPlacement.clear()
        for text, placement in [('左上', deco.TopLeft), ('上中', deco.TopCenter), ('右上', deco.TopRight),
                                ('左下', deco.BottomLeft), ('下中', deco.BottomCenter), ('右下', deco.BottomRight)]:
            self.cboPlacement.addItem(text, placement)
        self.cboPlacement.setCurrentIndex(self.cboPlacement.findData(deco.mPlacement))
        self.mHorizontal = getattr(self, 'spnHorizontal', None) or self.spinHorizontal
        self.mVertical = getattr(self, 'spnVertical', None) or self.spinVertical
        self.cboPlacement.currentIndexChanged.connect(self.placementChanged)
        self.placementChanged()
        self.mHorizontal.setValue(deco.mMarginHorizontal)
        self.mVertical.setValue(deco.mMarginVertical)
        self.mHorizontal.setClearValue(0)
        self.mVertical.setClearValue(0)
        self.wgtUnitSelection.setUnits([Qgis.RenderUnit.Millimeters, Qgis.RenderUnit.Percentage, Qgis.RenderUnit.Pixels])
        self.wgtUnitSelection.setUnit(deco.mMarginUnit)

    def placementChanged(self, *args):
        center = self.cboPlacement.currentData() in (self.mDeco.TopCenter, self.mDeco.BottomCenter)
        self.mHorizontal.setMinimum(-100 if center else 0)

    def connectButtons(self):
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        self.buttonBox.helpRequested.connect(lambda: QgsHelp.openHelp('map_views/map_view.html#' + self.helpAnchor))

    def defaultText(self): return self.mDeco.mApp.mProject.metadata().title()

    def insertExpression(self):
        text = self.mTextEdit.textCursor().selectedText()
        if text.startswith('[%') and text.endswith('%]'): text = text[2:-2].strip()
        dialog = QgsExpressionBuilderDialog(None, text, self, 'generic', self.mDeco.mApp.mMapCanvas.mapSettings().expressionContext())
        if dialog.exec_() and dialog.expressionText():
            self.mTextEdit.insertPlainText('[% ' + dialog.expressionText() + ' %]')
        dialog.deleteLater()

    def applyPlacement(self):
        self.mDeco.setEnabled(self.grpEnable.isChecked())
        self.mDeco.setPlacement(self.cboPlacement.currentData())
        self.mDeco.mMarginUnit = self.wgtUnitSelection.unit()
        self.mDeco.mMarginHorizontal = self.mHorizontal.value()
        self.mDeco.mMarginVertical = self.mVertical.value()

    def apply(self):
        self.applyPlacement()
        self.mDeco.mLabelText = self.mTextEdit.toPlainText()
        self.mDeco.mTextFormat = QgsTextFormat(self.mButtonFontStyle.textFormat())
        if self.mDeco.hasBackground: self.mDeco.mBackgroundColor = self.pbnBackgroundColor.color()
        self.mDeco.update()
        return True

    def accept(self):
        if self.apply(): super().accept()
