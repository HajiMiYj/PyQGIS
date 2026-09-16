from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapTool


class QgsGeorefToolAddPoint(QgsMapTool):
    def __init__(self, canvas, window):
        super().__init__(canvas)
        self.mWindow = window
        self.setCursor(Qt.CrossCursor)

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self.mWindow.mBusy:
            self.mWindow.requestPoint(event.mapPoint())
