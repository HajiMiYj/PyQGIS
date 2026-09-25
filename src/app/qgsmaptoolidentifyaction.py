"""Identify map tool and the five upstream selection shapes."""
import time

from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsRectangle, QgsWkbTypes
from qgis.gui import QgsMapToolIdentify, QgsRubberBand


class QgsMapToolIdentifyAction(QgsMapToolIdentify):
    def __init__(self, canvas, app):
        super().__init__(canvas)
        self.mApp = app
        self.mResults = []
        self.mSelectionMode = 0
        self.mStartPoint = None
        self.mPoints = []
        self.mLastHoverTime = 0
        self.mLastHoverPixel = None
        self.mLastIdentify = None
        self.mRubberBand = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.mRubberBand.setColor(QColor(255, 0, 0, 65))
        self.mRubberBand.setStrokeColor(QColor(255, 0, 0))
        self.mRubberBand.setWidth(2)
        self.mRubberBand.hide()

    def setSelectionMode(self, mode):
        self.mSelectionMode = mode
        self.mStartPoint = None
        self.mPoints.clear()
        self.mRubberBand.hide()

    def deactivate(self):
        self.mStartPoint = None
        self.mPoints.clear()
        self.mRubberBand.hide()
        super().deactivate()

    @staticmethod
    def polygon(points):
        ring = list(points)
        if len(ring) < 3:
            return None
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        return QgsGeometry.fromPolygonXY([ring])

    def dragGeometry(self, current):
        start = self.mStartPoint
        if start is None:
            return None
        if self.mSelectionMode == 3:  # freehand
            return self.polygon(self.mPoints + [current])
        if self.mSelectionMode == 4:  # radius
            radius = start.distance(current)
            return QgsGeometry.fromPointXY(start).buffer(radius, 36) if radius > 0 else None
        rectangle = QgsRectangle(start, current)
        return QgsGeometry.fromRect(rectangle) if rectangle.width() and rectangle.height() else None

    def showRubberBand(self, geometry):
        if geometry is None or geometry.isEmpty():
            return
        self.mRubberBand.setToGeometry(geometry, None)
        self.mRubberBand.show()

    def canvasPressEvent(self, event):
        if event.button() != Qt.LeftButton or self.mSelectionMode in (1, 2):
            return
        self.mStartPoint = self.toMapCoordinates(event.pos())
        self.mPoints = [self.mStartPoint]

    def canvasMoveEvent(self, event):
        if self.mSelectionMode == 1:
            now = time.monotonic()
            pixel = event.pos()
            if now - self.mLastHoverTime >= 0.25 and pixel != self.mLastHoverPixel:
                self.mLastHoverTime = now
                self.mLastHoverPixel = pixel
                self.identifyAtPixel(pixel)
            return
        current = self.toMapCoordinates(event.pos())
        if self.mSelectionMode == 2 and self.mPoints:
            self.showRubberBand(self.polygon(self.mPoints + [current]))
        elif self.mStartPoint is not None:
            if self.mSelectionMode == 3:
                self.mPoints.append(current)
            self.showRubberBand(self.dragGeometry(current))

    def canvasReleaseEvent(self, event):
        if self.mSelectionMode == 1:
            return
        if self.mSelectionMode == 2:
            if event.button() == Qt.RightButton:
                geometry = self.polygon(self.mPoints)
                if geometry is not None:
                    self.identifyAtGeometry(geometry)
                self.mPoints.clear()
                self.mRubberBand.hide()
            elif event.button() == Qt.LeftButton:
                self.mPoints.append(self.toMapCoordinates(event.pos()))
            return
        if event.button() != Qt.LeftButton:
            return
        start = self.mStartPoint
        geometry = self.dragGeometry(self.toMapCoordinates(event.pos())) if start is not None else None
        self.mStartPoint = None
        self.mPoints.clear()
        self.mRubberBand.hide()
        if geometry is not None:
            if self.mSelectionMode != 0 or start.distance(self.toMapCoordinates(event.pos())) > self.canvas().mapUnitsPerPixel() * 3:
                self.identifyAtGeometry(geometry)
                return
        self.identifyAtPixel(event.pos())

    def identifyAtPixel(self, pixel):
        self.mLastIdentify = ('pixel', QPoint(pixel))
        dialog = self.mApp.mIdentifyResultsDialog
        mode = dialog.identifyMode()
        x, y = pixel.x(), pixel.y()
        if mode == self.ActiveLayer:
            layers = self.mApp.mLayerTreeView.selectedLayersRecursive() or [self.mApp.activeLayer()]
            layers = [layer for layer in layers if layer is not None]
            results = self.identify(x, y, mode, layers, self.AllLayers) if layers else []
        else:
            results = self.identify(x, y, mode, self.AllLayers)
        self.showIdentifyResults(results)

    def identifyAtGeometry(self, geometry):
        self.mLastIdentify = ('geometry', QgsGeometry(geometry))
        mode = self.mApp.mIdentifyResultsDialog.identifyMode()
        if mode == self.ActiveLayer:
            layers = self.mApp.mLayerTreeView.selectedLayersRecursive() or [self.mApp.activeLayer()]
            layers = [layer for layer in layers if layer is not None]
            results = self.identify(geometry, mode, layers, self.AllLayers) if layers else []
        else:
            results = self.identify(geometry, mode, self.AllLayers)
        self.showIdentifyResults(results)

    def repeatIdentify(self):
        if self.mLastIdentify is None:
            return
        kind, value = self.mLastIdentify
        if kind == 'pixel':
            self.identifyAtPixel(value)
        else:
            self.identifyAtGeometry(value)

    def showIdentifyResults(self, results):
        self.mResults = list(results)
        self.mApp.mIdentifyResultsDialog.showResults(self.mResults)
