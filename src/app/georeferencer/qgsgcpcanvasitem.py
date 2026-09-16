from qgis.PyQt.QtCore import QRectF
from qgis.PyQt.QtGui import QColor, QPen
from qgis.gui import QgsMapCanvasItem


class QgsGCPCanvasItem(QgsMapCanvasItem):
    def __init__(self, canvas, point, text, enabled=True):
        self.mPoint, self.mText, self.mEnabled = point, text, enabled
        super().__init__(canvas)
        self.setZValue(1000)
        self.updatePosition()

    def updatePosition(self): self.setPos(self.toCanvasCoordinates(self.mPoint))
    def boundingRect(self): return QRectF(-7, -10, max(20, len(self.mText)*10+20), 30)
    def paint(self, painter, option=None, widget=None):
        painter.setPen(QPen(QColor('red' if self.mEnabled else 'gray'), 2))
        painter.drawEllipse(-4, -4, 8, 8)
        painter.drawLine(-6, 0, 6, 0)
        painter.drawLine(0, -6, 0, 6)
        painter.drawText(9, -3, self.mText)
