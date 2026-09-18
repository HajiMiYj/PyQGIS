"""Port of src/app/georeferencer/qgsresidualplotitem.cpp.

Native stores the plot residuals inside ``QgsGeorefDataPoint``; this port keeps
residuals in a parallel list on the georeferencer window (``mResiduals``), so
``setGCPList()`` takes both the point list and that residual list. Everything
else follows the native drawing maths: positions are millimetres inside the
layout item, residuals are in source pixels, and the arrow length is scaled by
the smallest ratio that still keeps every arrow inside the frame.
"""
import math
from qgis.PyQt.QtCore import QPointF, QRectF, QLineF, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from qgis.core import QgsLayoutItem, QgsLayoutUtils


class QgsResidualPlotItem(QgsLayoutItem):
    def __init__(self, layout):
        super().__init__(layout)
        self.mPoints = []
        self.mResiduals = []
        self.mExtent = None
        self.mConvertScaleToMapUnits = False
        self.setBackgroundEnabled(False)

    def itemFlags(self):
        return QgsLayoutItem.FlagOverridesPaint

    def setGCPList(self, points, residuals=()):
        self.mPoints = list(points)
        self.mResiduals = list(residuals)
        self.update()

    def residual(self, index):
        if index < len(self.mResiduals):
            x, y = self.mResiduals[index]
            if math.isfinite(x + y):
                return QPointF(x, y)
        return QPointF(0, 0)

    def setExtent(self, rect):
        self.mExtent = rect

    def extent(self):
        return self.mExtent

    def setConvertScaleToMapUnits(self, convert):
        self.mConvertScaleToMapUnits = bool(convert)

    def convertScaleToMapUnits(self):
        return self.mConvertScaleToMapUnits

    def draw(self, context):
        """Native keeps the painting in paint(); draw() stays empty."""

    def paint(self, painter, itemStyle=None, widget=None):
        if not self.mPoints or painter is None or self.mExtent is None:
            return
        widthMM = self.rect().width()
        heightMM = self.rect().height()

        enabledPen = QPen(QColor(255, 0, 0, 255), 0.3, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin)
        disabledPen = QPen(QColor(255, 0, 0, 85), 0.2, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin)
        enabledBrush = QBrush(QColor(255, 255, 255, 255))
        disabledBrush = QBrush(QColor(255, 255, 255, 127))

        minMMPixelRatio = float('inf')
        painter.setRenderHint(QPainter.Antialiasing, True)

        for index, point in enumerate(self.mPoints):
            gcp = point.sourcePoint()
            mmX = (gcp.x() - self.mExtent.xMinimum()) / self.mExtent.width() * widthMM
            mmY = (1 - (gcp.y() - self.mExtent.yMinimum()) / self.mExtent.height()) * heightMM
            if point.isEnabled():
                painter.setPen(enabledPen)
                painter.setBrush(enabledBrush)
            else:
                painter.setPen(disabledPen)
                painter.setBrush(disabledBrush)
            painter.drawRect(QRectF(mmX - 0.5, mmY - 0.5, 1, 1))
            QgsLayoutUtils.drawText(painter, QPointF(mmX + 2, mmY + 2), str(index), QFont())
            minMMPixelRatio = min(minMMPixelRatio, self.maxMMToPixelRatioForGCP(index, mmX, mmY))

        for index, point in enumerate(self.mPoints):
            gcp = point.sourcePoint()
            mmX = (gcp.x() - self.mExtent.xMinimum()) / self.mExtent.width() * widthMM
            mmY = (1 - (gcp.y() - self.mExtent.yMinimum()) / self.mExtent.height()) * heightMM
            painter.setPen(enabledPen if point.isEnabled() else disabledPen)
            residual = self.residual(index)
            start = QPointF(mmX, mmY)
            end = QPointF(mmX + residual.x() * minMMPixelRatio, mmY + residual.y() * minMMPixelRatio)
            painter.drawLine(start, end)
            painter.setBrush(QBrush(painter.pen().color()))
            self.drawArrowHead(painter, end.x(), end.y(), self.angle(start, end), 1)

        # scale bar, rounded down to the next nice number
        if minMMPixelRatio in (0, float('inf')):
            scaleBarWidthUnits = 0
            initialScaleBarWidth = self.rect().width() / 5
        else:
            scaleBarWidthUnits = self.rect().width() / 5 / minMMPixelRatio
            if scaleBarWidthUnits < 1:
                decimals = -math.floor(math.log10(scaleBarWidthUnits))
                scaleBarWidthUnits *= math.pow(10.0, decimals)
                scaleBarWidthUnits = int(scaleBarWidthUnits + 0.5) / math.pow(10.0, decimals)
            else:
                decimals = int(math.log10(scaleBarWidthUnits))
                scaleBarWidthUnits /= math.pow(10.0, decimals)
                scaleBarWidthUnits = int(scaleBarWidthUnits + 0.5) * math.pow(10.0, decimals)
            initialScaleBarWidth = scaleBarWidthUnits * minMMPixelRatio

        painter.setPen(QColor(0, 0, 0))
        painter.drawLine(QPointF(5, self.rect().height() - 5), QPointF(5 + initialScaleBarWidth, self.rect().height() - 5))
        painter.drawLine(QPointF(5, self.rect().height() - 5), QPointF(5, self.rect().height() - 7))
        painter.drawLine(QPointF(5 + initialScaleBarWidth, self.rect().height() - 5), QPointF(5 + initialScaleBarWidth, self.rect().height() - 7))
        scaleBarFont = QFont()
        scaleBarFont.setPointSize(9)
        unit = 'map units' if self.mConvertScaleToMapUnits else 'pixels'
        QgsLayoutUtils.drawText(painter, QPointF(5, self.rect().height() - 4 + QgsLayoutUtils.fontAscentMM(scaleBarFont)),
                                f'{scaleBarWidthUnits} {unit}', QFont())

        if self.frameEnabled():
            painter.save()
            painter.setPen(self.pen())
            painter.setBrush(Qt.NoBrush)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.drawRect(QRectF(0, 0, self.rect().width(), self.rect().height()))
            painter.restore()

    def maxMMToPixelRatioForGCP(self, index, pixelXMM, pixelYMM):
        """Largest mm-per-pixel ratio that keeps this arrow inside the frame."""
        upDownDist = float('inf')
        leftRightDist = float('inf')
        residual = self.residual(index)
        residualLine = QLineF(pixelXMM, pixelYMM, pixelXMM + residual.x(), pixelYMM + residual.y())

        if residual.y() > 0:
            intersection, ok = self.intersection(residualLine, QLineF(0, self.rect().height(), self.rect().width(), self.rect().height()))
            if ok:
                upDownDist = self.dist(QPointF(pixelXMM, pixelYMM), intersection)
        elif residual.y() < 0:
            intersection, ok = self.intersection(residualLine, QLineF(0, 0, self.mExtent.xMaximum(), 0))
            if ok:
                upDownDist = self.dist(QPointF(pixelXMM, pixelYMM), intersection)

        if residual.x() > 0:
            intersection, ok = self.intersection(residualLine, QLineF(self.rect().width(), 0, self.rect().width(), self.rect().height()))
            if ok:
                leftRightDist = self.dist(QPointF(pixelXMM, pixelYMM), intersection)
        elif residual.x() < 0:
            intersection, ok = self.intersection(residualLine, QLineF(0, 0, 0, self.rect().height()))
            if ok:
                leftRightDist = self.dist(QPointF(pixelXMM, pixelYMM), intersection)

        total = math.hypot(residual.x(), residual.y())
        if total <= 0:
            return float('inf')
        return (leftRightDist if leftRightDist <= upDownDist else upDownDist) / total

    @staticmethod
    def intersection(line, frame):
        """QLineF.intersects() exposed as (point, hit) for the port's callers."""
        kind, point = line.intersects(frame)
        return point, kind == QLineF.BoundedIntersection

    @staticmethod
    def dist(p1, p2):
        return math.hypot(p2.x() - p1.x(), p2.y() - p1.y())

    @staticmethod
    def drawArrowHead(painter, x, y, angle, arrowHeadWidth):
        angleRad = math.radians(angle)
        middle = QPointF(x, y)
        p1 = QPointF(-arrowHeadWidth / 2.0, arrowHeadWidth)
        p2 = QPointF(arrowHeadWidth / 2.0, arrowHeadWidth)

        def rotate(point):
            return QPointF(point.x() * math.cos(angleRad) + point.y() * -math.sin(angleRad),
                           point.x() * math.sin(angleRad) + point.y() * math.cos(angleRad))

        p1Rotated, p2Rotated = rotate(p1), rotate(p2)
        polygon = QPolygonF([middle, QPointF(x + p1Rotated.x(), y + p1Rotated.y()),
                             QPointF(x + p2Rotated.x(), y + p2Rotated.y())])
        painter.save()
        arrowPen = painter.pen()
        arrowPen.setJoinStyle(Qt.RoundJoin)
        arrowBrush = painter.brush()
        arrowBrush.setStyle(Qt.SolidPattern)
        painter.setPen(arrowPen)
        painter.setBrush(arrowBrush)
        painter.drawPolygon(polygon)
        painter.restore()

    @staticmethod
    def angle(p1, p2):
        xDiff, yDiff = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(xDiff, yDiff)
        if length <= 0:
            return 0
        value = math.degrees(math.acos((-yDiff * length) / (length * length)))
        return 360 - value if xDiff < 0 else value
