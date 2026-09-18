"""Port of src/plugins/offline_editing/offline_editing_progress_dialog.cpp."""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog

ROOT = Path(__file__).resolve().parents[3]


class QgsOfflineEditingProgressDialog(QDialog):
    def __init__(self, parent=None, flags=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'src/ui/offline_editing/offline_editing_progress_dialog_base.ui'), self)
        self.mProgressUpdate = 1

    def setTitle(self, title):
        self.setWindowTitle(title)

    def setCurrentLayer(self, layer, numLayers):
        self.label.setText(f'第 {layer} / {numLayers} 个图层…')
        self.progressBar.reset()

    def setupProgressBar(self, format, maximum):
        self.progressBar.setFormat(format)
        self.progressBar.setRange(0, maximum)
        self.progressBar.reset()
        self.mProgressUpdate = max(1, maximum // 100)

    def setProgressValue(self, value):
        # Native updates every nth feature so processing stays fast.
        if value == self.progressBar.maximum() or value % self.mProgressUpdate == 0:
            self.progressBar.setValue(value)
