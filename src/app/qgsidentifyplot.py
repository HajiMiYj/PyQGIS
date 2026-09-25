"""Qt implementation of the QGIS 3.34 identify result plot.

The desktop dialog uses QwtPlot for this one widget.  The Python application
keeps the same numeric-series behaviour with QWidget/QPainter, both supplied
by the OSGeo4W Qt runtime.
"""

import math

from qgis.PyQt.QtCore import Qt, QPointF, QRectF
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QWidget


class QgsIdentifyPlot(QWidget):
    COLORS = ('#2677af', '#db6b37', '#59a14f', '#9c6db4', '#be9b31', '#de5a79')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mCurves = []
        self.setMinimumSize(220, 160)
        self.setAutoFillBackground(True)

    def clear(self):
        self.mCurves.clear()
        self.update()

    def addCurve(self, attributes, title):
        # QgsIdentifyPlotCurve in the C++ dialog uses numeric values in key
        # order and numbers the usable samples consecutively from one.
        samples = []
        for key, value in sorted(attributes.items()):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                samples.append((key, number))
        if samples:
            self.mCurves.append((title, samples))
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        if not self.mCurves:
            painter.end()
            return

        metrics = painter.fontMetrics()
        legendWidth = max(metrics.horizontalAdvance(title) + 28 for title, _ in self.mCurves)
        legendColumns = max(1, min(3, self.width() // max(110, legendWidth)))
        legendRows = math.ceil(len(self.mCurves) / legendColumns)
        chart = QRectF(54, 20 + legendRows * (metrics.height() + 6),
                       max(1, self.width() - 76),
                       max(1, self.height() - 78 - legendRows * (metrics.height() + 6)))
        values = [number for _, samples in self.mCurves for _, number in samples]
        low, high = min(values), max(values)
        if low == high:
            padding = abs(low) * 0.1 or 1
        else:
            padding = (high - low) * 0.05
        low -= padding
        high += padding
        maxSamples = max(len(samples) for _, samples in self.mCurves)
        axisPen = QPen(self.palette().text().color())
        axisPen.setWidth(1)
        painter.setPen(axisPen)
        painter.drawLine(chart.bottomLeft(), chart.topLeft())
        painter.drawLine(chart.bottomLeft(), chart.bottomRight())
        for tick in range(5):
            y = chart.bottom() - chart.height() * tick / 4
            value = low + (high - low) * tick / 4
            painter.drawText(QRectF(0, y - 9, 48, 18), Qt.AlignRight | Qt.AlignVCenter, f'{value:.4g}')
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.DotLine))
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
            painter.setPen(axisPen)
        for index in range(maxSamples):
            x = chart.left() + chart.width() * (index + 1) / (maxSamples + 1)
            painter.drawText(QRectF(x - 14, chart.bottom() + 3, 28, 18), Qt.AlignCenter, str(index + 1))

        for curveIndex, (title, samples) in enumerate(self.mCurves):
            color = QColor(self.COLORS[curveIndex % len(self.COLORS)])
            column = curveIndex % legendColumns
            row = curveIndex // legendColumns
            legendX = 12 + column * max(110, legendWidth)
            legendY = 17 + row * (metrics.height() + 6)
            painter.setPen(QPen(color, 2))
            painter.drawLine(legendX, legendY, legendX + 18, legendY)
            painter.setPen(self.palette().text().color())
            painter.drawText(legendX + 23, legendY + metrics.ascent() // 2, title)
            points = [QPointF(chart.left() + chart.width() * (i + 1) / (maxSamples + 1),
                              chart.bottom() - chart.height() * (value - low) / (high - low))
                      for i, (_, value) in enumerate(samples)]
            if len(points) > 1:
                path = QPainterPath(points[0])
                for point in points[1:]:
                    path.lineTo(point)
                painter.setPen(QPen(color, 2))
                painter.drawPath(path)
            painter.setBrush(self.palette().base())
            painter.setPen(QPen(color, 2))
            for point in points:
                painter.drawEllipse(point, 4, 4)
        painter.end()
