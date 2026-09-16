from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsMapTool


class QgsGeorefToolMovePoint(QgsMapTool):
    def __init__(self, canvas, window, destination=False):
        super().__init__(canvas)
        self.mWindow, self.mDestination, self.mIndex = window, destination, None
        self.setCursor(Qt.CrossCursor)

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.mWindow.mBusy:
            self.mIndex = self.mWindow.nearestPoint(event.mapPoint(), self.mDestination)

    def canvasMoveEvent(self, event):
        if self.mIndex is not None:
            self.mWindow.previewMove(self.mIndex, event.mapPoint(), self.mDestination)

    def canvasReleaseEvent(self, event):
        index, self.mIndex = self.mIndex, None
        if index is not None and event.button() == Qt.LeftButton and not self.mWindow.mBusy:
            self.mWindow.movePoint(index, event.mapPoint(), self.mDestination)
        else: self.mWindow.updateMarkers()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.mIndex = None
            self.mWindow.updateMarkers()
            event.ignore()

    def deactivate(self):
        self.mIndex = None
        if not self.mWindow.mShutdown: self.mWindow.updateMarkers()
        super().deactivate()
