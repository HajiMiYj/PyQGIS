"""QgsAnnotationWidget: original common annotation UI and native symbol buttons."""
from pathlib import Path
from qgis.PyQt import uic, sip
from qgis.PyQt.QtCore import QCoreApplication, pyqtSignal, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QWidget, QDialog, QDialogButtonBox
from qgis.core import Qgis, QgsMargins, QgsProject, QgsSettings
from qgis.gui import QgsGui

UI_ROOT = Path(__file__).resolve().parents[1] / 'ui'


class QgsAnnotationWidget(QWidget):
    changed = pyqtSignal()
    backgroundColorChanged = pyqtSignal(object)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        uic.loadUi(str(UI_ROOT / 'qgsannotationwidgetbase.ui'), self)
        self.mItem = item
        annotation = item.annotation()
        self.mLayerComboBox.setAllowEmptyLayer(True)
        self.mLayerComboBox.setLayer(annotation.mapLayer())
        self.mMapPositionFixedCheckBox.setChecked(annotation.hasFixedMapPosition())
        for name, value in [('Top', annotation.contentsMargin().top()), ('Left', annotation.contentsMargin().left()),
                            ('Right', annotation.contentsMargin().right()), ('Bottom', annotation.contentsMargin().bottom())]:
            widget = getattr(self, 'mSpin'+name+'Margin')
            widget.setValue(value)
            widget.valueChanged.connect(lambda *_: self.changed.emit())
        from .qgisapp import QgisApp
        for button, symbol, kind in [(self.mMapMarkerButton, annotation.markerSymbol(), Qgis.SymbolType.Marker),
                                     (self.mFrameStyleButton, annotation.fillSymbol(), Qgis.SymbolType.Fill)]:
            button.setSymbolType(kind)
            if symbol: button.setSymbol(symbol.clone())
            button.setMapCanvas(QgisApp.instance().mMapCanvas)
            button.setMessageBar(QgisApp.instance().mMessageBar)
            button.changed.connect(self.changed)
        self.mFrameStyleButton.changed.connect(lambda: self.backgroundColorChanged.emit(self.backgroundColor()))
        self.mLayerComboBox.layerChanged.connect(lambda *_: self.changed.emit())
        self.mMapPositionFixedCheckBox.toggled.connect(lambda *_: self.changed.emit())

    def backgroundColor(self): return self.mFrameStyleButton.symbol().color()

    def apply(self):
        if not self.mItem or sip.isdeleted(self.mItem): return
        annotation = self.mItem.annotation()
        if not annotation: return
        annotation.setHasFixedMapPosition(self.mMapPositionFixedCheckBox.isChecked())
        annotation.setMapLayer(self.mLayerComboBox.currentLayer())
        annotation.setMarkerSymbol(self.mMapMarkerButton.symbol().clone())
        annotation.setFillSymbol(self.mFrameStyleButton.symbol().clone())
        annotation.setContentsMargin(QgsMargins(self.mSpinLeftMargin.value(), self.mSpinTopMargin.value(),
                                                self.mSpinRightMargin.value(), self.mSpinBottomMargin.value()))
        self.mItem.update()
        QgsProject.instance().setDirty(True)


class _QgsAnnotationDialog(QDialog):
    """Shared Python wiring for the identical C++ dialog slots."""
    def setupAnnotationWidget(self, item):
        self.mItem = item
        self.mEmbeddedWidget = QgsAnnotationWidget(item, self)
        self.mStackedWidget.addWidget(self.mEmbeddedWidget)
        self.mStackedWidget.setCurrentWidget(self.mEmbeddedWidget)
        QgsGui.enableAutoGeometryRestore(self)
        self.mButtonBox.button(QDialogButtonBox.Apply).clicked.connect(self.applySettingsToItem)
        self.mButtonBox.helpRequested.connect(lambda: QDesktopServices.openUrl(QUrl('https://docs.qgis.org/3.34/en/docs/user_manual/map_views/map_view.html#sec-annotations')))
        self.mDeleteButton = self.mButtonBox.addButton(QCoreApplication.translate('DbManagerDlgSqlLayerWindow', 'Delete'), QDialogButtonBox.ActionRole)
        self.mDeleteButton.clicked.connect(self.deleteItem)
        self.mEmbeddedWidget.changed.connect(self.onSettingsChanged)

    def setupLiveUpdate(self):
        self.mLiveCheckBox.setChecked(QgsSettings().value('annotations/live-update', False, type=bool))
        self.mLiveCheckBox.toggled.connect(self.onLiveUpdateToggled)
        self.onLiveUpdateToggled(self.mLiveCheckBox.isChecked(), apply=False)

    def onSettingsChanged(self, *args):
        if self.mLiveCheckBox.isChecked(): self.applySettingsToItem()

    def onLiveUpdateToggled(self, checked, apply=True):
        self.mButtonBox.button(QDialogButtonBox.Apply).setHidden(checked)
        self.mButtonBox.button(QDialogButtonBox.Cancel).setHidden(checked)
        QgsSettings().setValue('annotations/live-update', checked)
        if checked and apply: self.applySettingsToItem()

    def accept(self):
        self.applySettingsToItem()
        super().accept()

    def deleteItem(self):
        if self.mItem and not sip.isdeleted(self.mItem):
            QgsProject.instance().annotationManager().removeAnnotation(self.mItem.annotation())
        self.mItem = None
        self.reject()

    def annotation(self):
        return self.mItem.annotation() if self.mItem and not sip.isdeleted(self.mItem) else None
