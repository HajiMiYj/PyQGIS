"""Port of src/gui/qgsproxystyle.cpp QgsAppStyle.

QgsAppStyle sits behind ``#ifndef SIP_RUN`` upstream, so it is absent from the
PyQGIS bindings even though it is GUI_EXPORT. The application style is
rebuilt here so the desktop entry can install the same proxy style (and get the
same disabled-icon rendering) as native QGIS.

The upstream ``polish()`` override only acts on Unix, so it is not reproduced.
"""
from qgis.PyQt.QtGui import QIcon, QImage, QPixmap
from qgis.PyQt.QtWidgets import QProxyStyle, QStyleFactory
from qgis.core import QgsImageOperation


class QgsAppStyle(QProxyStyle):
    def __init__(self, base):
        super().__init__()
        self.mBaseStyle = base or ''
        if self.mBaseStyle:
            style = QStyleFactory.create(self.mBaseStyle)
            if style is not None:
                self.setBaseStyle(style)
        self.setObjectName('QgsAppStyle')

    def baseStyle(self):
        return self.mBaseStyle

    def generatedIconPixmap(self, iconMode, pixmap, opt):
        if iconMode == QIcon.Disabled:
            if not pixmap.isNull():
                # Upstream replaces the default disabled icon treatment, which
                # only reads well on light themes, with a hue/opacity adjustment.
                image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
                QgsImageOperation.adjustHueSaturation(image, 0.2)
                QgsImageOperation.multiplyOpacity(image, 0.3)
                return QPixmap.fromImage(image)
            return pixmap
        return super().generatedIconPixmap(iconMode, pixmap, opt)

    def clone(self):
        return QgsAppStyle(self.mBaseStyle)
