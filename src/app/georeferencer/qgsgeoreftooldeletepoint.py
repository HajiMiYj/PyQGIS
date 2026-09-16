from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapTool


class QgsGeorefToolDeletePoint(QgsMapTool):
    def __init__(self, canvas, window):
        super().__init__(canvas)
        self.mWindow = window
        self.setCursor(Qt.CrossCursor)

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self.mWindow.mBusy:
            index = self.mWindow.nearestPoint(event.mapPoint())
            if index is not None: self.mWindow.deletePoints([index])
