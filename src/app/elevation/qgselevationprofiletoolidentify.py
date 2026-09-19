"""Click/rectangle identification using native generated profile results."""
from qgis.PyQt.QtCore import QCoreApplication, Qt, QPointF, QRectF
from qgis.PyQt.QtWidgets import QRubberBand
from qgis.gui import QgsPlotTool, QgsMapToolIdentify
from qgis.core import QgsVectorLayer


class QgsElevationProfileToolIdentify(QgsPlotTool):
    def __init__(self, canvas, app):
        super().__init__(canvas, '识别高程剖面')
        self.mApp, self.mStart = app, None
        self.mRubberBand = QRubberBand(QRubberBand.Rectangle, canvas.viewport())
        self.setCursor(Qt.CrossCursor)

    def constrainedPoint(self, event):
        point = event.snappedPoint().toQPointF()
        area = self.canvas().plotArea()
        return QPointF(max(area.left(), min(area.right(), point.x())), max(area.top(), min(area.bottom(), point.y())))

    def plotPressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        self.mStart = self.constrainedPoint(event)

    def plotMoveEvent(self, event):
        if self.mStart is None: return
        self.mRubberBand.setGeometry(QRectF(self.mStart, self.constrainedPoint(event)).normalized().toRect())
        self.mRubberBand.show()

    def plotReleaseEvent(self, event):
        if self.mStart is None or event.button() != Qt.LeftButton: return
        end = self.constrainedPoint(event)
        rectangle = QRectF(self.mStart, end).normalized()
        query = rectangle if rectangle.width() + rectangle.height() > 5 else self.mStart
        self.mStart = None
        self.mRubberBand.hide()
        self.showResults(self.canvas().identify(query))

    def showResults(self, results):
        converted = []
        for result in results:
            layer = result.layer()
            if layer is None: continue
            for attributes in result.results():
                feature = None
                if isinstance(layer, QgsVectorLayer) and attributes.get('id') is not None:
                    feature = layer.getFeature(int(attributes['id']))
                if feature is not None and feature.isValid():
                    entry = QgsMapToolIdentify.IdentifyResult(layer, feature, {str(k): str(v) for k, v in attributes.items()})
                else:
                    entry = QgsMapToolIdentify.IdentifyResult(layer, QCoreApplication.translate('MainWindow', 'Elevation Profile'), {str(k): str(v) for k, v in attributes.items()}, {})
                converted.append(entry)
        self.mApp.mMapTools['identify'].showIdentifyResults(converted)

    def deactivate(self):
        self.mStart = None
        self.mRubberBand.hide()
        super().deactivate()
