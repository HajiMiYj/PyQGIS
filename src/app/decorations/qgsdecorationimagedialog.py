import re
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt, QRectF
from qgis.PyQt.QtGui import QPixmap, QPainter
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import QDialog, QMessageBox
from qgis.core import QgsApplication
from qgis.gui import QgsGui
from .qgsdecorationtitledialog import QgsDecorationTitleDialog, UI_ROOT


class QgsDecorationImageDialog(QgsDecorationTitleDialog):
    uiName = 'qgsdecorationimagedialog.ui'
    helpAnchor = 'image-decoration'

    def __init__(self, decoration, parent):
        QDialog.__init__(self, parent)
        self.mDeco = decoration
        # Preview uses a separate item so Cancel never alters the map/project.
        self.mPreview = type(decoration)(parent)
        uic.loadUi(str(UI_ROOT / self.uiName), self)
        QgsGui.enableAutoGeometryRestore(self)
        self.initPlacement()
        self.spinSize.setValue(decoration.mSize)
        self.pbnChangeColor.setColor(decoration.mColor)
        self.pbnChangeOutlineColor.setColor(decoration.mOutlineColor)
        self.pbnChangeColor.setAllowOpacity(True)
        self.pbnChangeOutlineColor.setAllowOpacity(True)
        self.initPath()
        self.spinSize.valueChanged.connect(self.drawImage)
        self.pbnChangeColor.colorChanged.connect(self.drawImage)
        self.pbnChangeOutlineColor.colorChanged.connect(self.drawImage)
        self.pixmapLabel.setScaledContents(False)
        self.drawImage()
        self.connectButtons()
        self.mPreview.imageChanged.connect(self.drawImage)
        self.finished.connect(self.closePreview)

    def closePreview(self, *args):
        self.mPreview.shutdown()
        self.mPreview.deleteLater()

    def initPath(self):
        self.wgtImagePath.setFilePath(self.mDeco.mImagePath)
        self.wgtImagePath.setFilter('图片 (*.svg *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff);;所有文件 (*)')
        self.wgtImagePath.fileChanged.connect(self.drawImage)
        self.wgtImagePath.lineEdit().setPlaceholderText('本地图片、HTTP(S) 地址或 base64: 图片数据')
        self.wgtImagePath.lineEdit().setContextMenuPolicy(Qt.CustomContextMenu)
        self.wgtImagePath.lineEdit().customContextMenuRequested.connect(self.pathContextMenu)

    def pathContextMenu(self, position):
        edit = self.wgtImagePath.lineEdit()
        menu = edit.createStandardContextMenu()
        menu.addSeparator()
        embed = menu.addAction('将当前图片嵌入工程')
        embed.setEnabled(self.mValidImage)
        embed.triggered.connect(self.embedImage)
        if self.wgtImagePath.filePath().lower().startswith(('http://', 'https://')):
            menu.addAction('重新下载图片', self.reloadImage)
        menu.exec_(edit.mapToGlobal(position))
        menu.deleteLater()

    def embedImage(self):
        path = self.mPreview.embeddedImagePath()
        if path: self.wgtImagePath.setFilePath(path)

    def reloadImage(self):
        self.mPreview.setImagePath(self.wgtImagePath.filePath(), force=True)
        self.drawImage()

    def copyGraphicSettings(self, target):
        target.mSize = self.spinSize.value()
        target.mColor = self.pbnChangeColor.color()
        target.mOutlineColor = self.pbnChangeOutlineColor.color()
        target.setImagePath(self.wgtImagePath.filePath())

    def previewPath(self): return self.mPreview.renderPath()

    def drawImage(self, *args):
        self.copyGraphicSettings(self.mPreview)
        size = 160
        graphic, dimensions = self.mPreview.graphic(size)
        self.mValidImage = dimensions is not None and not dimensions.isEmpty()
        svg = isinstance(graphic, QSvgRenderer)
        content = bytes(QgsApplication.svgCache().getImageData(self.previewPath())) if svg else b''
        self.pbnChangeColor.setEnabled(bool(re.search(rb'param\(\s*fill\s*\)', content)))
        self.pbnChangeOutlineColor.setEnabled(bool(re.search(rb'param\(\s*outline\s*\)', content)))
        if not self.mValidImage:
            self.pixmapLabel.setText('正在下载图片…' if self.mPreview.mLoading else self.mPreview.mImageError or '请选择有效图片')
            return
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            scale = 0.7 * size / max(dimensions.width(), dimensions.height())
            width, height = dimensions.width() * scale, dimensions.height() * scale
            painter.translate(size / 2, size / 2)
            if hasattr(self.mPreview, 'rotation'):
                painter.rotate(self.mPreview.rotation(self.mDeco.mApp.mMapCanvas.mapSettings()))
            rect = QRectF(-width / 2, -height / 2, width, height)
            if svg: graphic.render(painter, rect)
            else: painter.drawImage(rect, graphic)
        finally: painter.end()
        self.pixmapLabel.setPixmap(pixmap)

    def apply(self):
        if self.grpEnable.isChecked() and not self.mValidImage:
            QMessageBox.warning(self, QCoreApplication.translate('QgsDecorationImageDialog', 'Image Decoration'), '请等待图片下载完成或选择有效图片，也可以取消启用装饰。')
            return False
        self.applyPlacement()
        self.copyGraphicSettings(self.mDeco)
        if self.mPreview.mImageData and self.mPreview.mImagePath == self.mDeco.mImagePath:
            # Reuse the preview download on Apply; do not launch a second fetch.
            self.mDeco.shutdown()
            self.mDeco.setImageData(self.mPreview.mImageData)
        self.mDeco.update()
        return True
