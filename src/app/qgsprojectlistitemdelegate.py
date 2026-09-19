"""Python port of the upstream QGIS C++ file 'src/app/qgsprojectlistitemdelegate.cpp'
(header 'src/app/qgsprojectlistitemdelegate.h', QGIS 3.34).

Contains the three classes declared in that header:

* QgsProjectPreviewImage - helper which loads a preview image and returns it as a
  pixmap with rounded corners.
* QgsProjectListItemDelegate - item delegate used by the recent projects list.
* QgsNewsItemListItemDelegate - item delegate used by the QGIS news feed list.
"""
from qgis.PyQt.QtCore import Qt, QSize, QRect, QRectF, QPoint, QUrl
from pathlib import Path
from qgis.PyQt.QtGui import (
    QPainter,
    QPixmap,
    QImage,
    QColor,
    QBrush,
    QPalette,
    QIcon,
    QTextDocument,
    QAbstractTextDocumentLayout,
)
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QStyle, QWidget
from qgis.core import QgsApplication, Qgis


def _pinImageTag():
    """The pin marker used for pinned entries.

    Upstream embeds the compiled-in Qt resource :/images/themes/default/pin.svg.
    That resource namespace belongs to the QGIS binaries and is not registered in
    a PyQt process, so the identical file shipped with this port is referenced
    through a file:// URL instead.
    """
    pinPath = Path(__file__).resolve().parents[2] / 'images' / 'themes' / 'default' / 'pin.svg'
    if not pinPath.exists():
        return ''
    return f'<img src="{QUrl.fromLocalFile(str(pinPath)).toString()}">'


def _drawRoundedRect(painter, x, y, w, h, xRadius, yRadius):
    """QPainter::drawRoundedRect( int x, int y, int w, int h, qreal, qreal ).

    C++ implicitly converts the (double) geometry arguments to int when selecting
    that overload; Python does not, so the conversion is made explicit here.
    """
    painter.drawRoundedRect(int(x), int(y), int(w), int(h), xRadius, yRadius)


def _drawPixmap(painter, x, y, w, h, pixmap):
    """QPainter::drawPixmap( int x, int y, int w, int h, const QPixmap & ).

    C++ implicitly converts the (double) position arguments to int when selecting
    that overload; Python does not, so the conversion is made explicit here.
    """
    painter.drawPixmap(int(x), int(y), int(w), int(h), pixmap)


class QgsProjectPreviewImage:
    """Helper class to manage a project preview image.

    Mirrors the upstream C++ class of the same name. A project preview image is
    stored as a QImage and handed out as a pixmap with rounded corners.
    """

    def __init__(self, pathOrImage=None):
        self.mImage = QImage()
        if pathOrImage is None:
            return
        if isinstance(pathOrImage, QImage):
            self.setImage(pathOrImage)
        else:
            self.loadImageFromFile(pathOrImage)

    def loadImageFromFile(self, path):
        """Loads an image from a file, replacing any existing image."""
        self.mImage = QImage(path)

    def setImage(self, image):
        """Sets the image to be displayed."""
        self.mImage = image

    def pixmap(self):
        """Returns the preview image as a pixmap with rounded corners."""
        # nicely round corners so users don't get paper cuts
        previewImage = QImage(self.mImage.size(), QImage.Format_ARGB32)
        previewImage.fill(Qt.transparent)
        previewPainter = QPainter(previewImage)
        previewPainter.setRenderHint(QPainter.Antialiasing, True)
        previewPainter.setPen(Qt.NoPen)
        previewPainter.setBrush(Qt.black)
        _drawRoundedRect(previewPainter, 0, 0, previewImage.width(), previewImage.height(), 8, 8)
        previewPainter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        previewPainter.drawImage(0, 0, self.mImage)
        previewPainter.end()
        return QPixmap.fromImage(previewImage)

    def isNull(self):
        """Returns True if the preview image is null."""
        return self.mImage.isNull()


class QgsProjectListItemDelegate(QStyledItemDelegate):
    """Item delegate for the recent projects list.

    Mirrors the upstream C++ class of the same name.
    """

    # Custom model roles
    TitleRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    NativePathRole = Qt.UserRole + 3
    CrsRole = Qt.UserRole + 4
    PinRole = Qt.UserRole + 5
    AnonymisedNativePathRole = Qt.UserRole + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mRoundedRectSizePixels = 5
        self.mShowPath = True
        self.mColor = QColor(Qt.white)
        fontMetrics = QgsApplication.fontMetrics()
        self.mRoundedRectSizePixels = int(Qgis.UI_SCALE_FACTOR * fontMetrics.height() * 0.5)

    def paint(self, painter, option, index):
        # QgsScopedQPainterState painterState( painter );
        painter.save()
        try:
            doc = QTextDocument()
            icon = index.data(Qt.DecorationRole)
            if not isinstance(icon, QPixmap):
                icon = QPixmap()

            ctx = QAbstractTextDocumentLayout.PaintContext()
            optionV4 = option

            color = QColor(optionV4.palette.color(QPalette.Active, QPalette.Window))
            if option.state & QStyle.State_Selected and option.state & QStyle.State_HasFocus:
                color.setAlpha(40)
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Active, QPalette.HighlightedText))

                style = option.widget.style() if option.widget is not None else QgsApplication.style()
                style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, None)
            elif option.state & QStyle.State_Enabled:
                if option.state & QStyle.State_Selected:
                    color.setAlpha(40)
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Active, QPalette.Text))

                style = option.widget.style() if option.widget is not None else QgsApplication.style()
                style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, None)
            else:
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Disabled, QPalette.Text))

            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setPen(QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(color))
            _drawRoundedRect(painter, option.rect.left() + 0.625 * self.mRoundedRectSizePixels, option.rect.top() + 0.625 * self.mRoundedRectSizePixels,
                             option.rect.width() - 2 * 0.625 * self.mRoundedRectSizePixels, option.rect.height() - 2 * 0.625 * self.mRoundedRectSizePixels, self.mRoundedRectSizePixels, self.mRoundedRectSizePixels)

            titleSize = int(QgsApplication.fontMetrics().height() * 1.1)
            textSize = int(titleSize * 0.85)
            iconSize = QSize(icon.size())
            w = option.styleObject
            if isinstance(w, QWidget):
                iconSize = QSize(int(iconSize.width() / w.devicePixelRatioF()), int(iconSize.height() / w.devicePixelRatioF()))

            pinImage = _pinImageTag() if index.data(QgsProjectListItemDelegate.PinRole) else ''
            pathText = index.data(QgsProjectListItemDelegate.AnonymisedNativePathRole) if self.mShowPath else ''
            doc.setHtml("<div style='font-size:{textSize}px'><span style='font-size:{titleSize}px;font-weight:bold;'>{title}{pin}</span><br>{path}<br>{crs}</div>".format(
                textSize=textSize, titleSize=float(titleSize),
                title=index.data(QgsProjectListItemDelegate.TitleRole) or '',
                pin=pinImage,
                path=pathText or '',
                crs=index.data(QgsProjectListItemDelegate.CrsRole) or ''))
            doc.setTextWidth(option.rect.width() - (iconSize.width() + 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 4.375 * self.mRoundedRectSizePixels))

            if not icon.isNull():
                _drawPixmap(painter, option.rect.left() + 1.25 * self.mRoundedRectSizePixels, option.rect.top() + 1.25 * self.mRoundedRectSizePixels,
                            iconSize.width(), iconSize.height(), icon)

            painter.translate(option.rect.left() + (iconSize.width() + 3.125 * self.mRoundedRectSizePixels if not icon.isNull() else 1.875 * self.mRoundedRectSizePixels),
                              option.rect.top() + 1.875 * self.mRoundedRectSizePixels)
            ctx.clip = QRectF(0, 0, option.rect.width() - (iconSize.width() - 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 3.125 * self.mRoundedRectSizePixels),
                              option.rect.height() - 3.125 * self.mRoundedRectSizePixels)
            doc.documentLayout().draw(painter, ctx)
        finally:
            # ~QgsScopedQPainterState()
            painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        icon = index.data(Qt.DecorationRole)
        if not isinstance(icon, QPixmap):
            icon = QPixmap()
        iconSize = QSize(icon.size())
        w = option.styleObject
        if isinstance(w, QWidget):
            iconSize = QSize(int(iconSize.width() / w.devicePixelRatioF()), int(iconSize.height() / w.devicePixelRatioF()))

        if option.rect.width() < 450:
            width = 450
        else:
            width = option.rect.width()

        titleSize = int(QgsApplication.fontMetrics().height() * 1.1)
        textSize = int(titleSize * 0.85)

        pinImage = '<img src=":/images/themes/default/pin.svg">' if index.data(QgsProjectListItemDelegate.PinRole) else ''
        doc.setHtml("<div style='font-size:{textSize}px;'><span style='font-size:{titleSize}px;font-weight:bold;'>{title}{pin}</span><br>{path}<br>{crs}</div>".format(
            textSize=textSize, titleSize=float(titleSize),
            title=index.data(QgsProjectListItemDelegate.TitleRole) or '',
            pin=pinImage,
            path=index.data(QgsProjectListItemDelegate.NativePathRole) or '',
            crs=index.data(QgsProjectListItemDelegate.CrsRole) or ''))
        doc.setTextWidth(width - (iconSize.width() + 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 4.375 * self.mRoundedRectSizePixels))

        return QSize(width, int(max(doc.size().height() + 1.25 * self.mRoundedRectSizePixels, float(iconSize.height())) + 2.5 * self.mRoundedRectSizePixels))

    def showPath(self):
        return self.mShowPath

    def setShowPath(self, value):
        self.mShowPath = value


class QgsNewsItemListItemDelegate(QStyledItemDelegate):
    """Item delegate for the QGIS news feed list.

    Mirrors the upstream C++ class of the same name.
    """

    # Custom model roles of QgsNewsFeedModel (src/core/network/qgsnewsfeedmodel.h):
    # Key = Qt::UserRole + 1, then Title, Content, ImageUrl, Image, Link, Sticky.
    TitleRole = Qt.UserRole + 2
    ContentRole = Qt.UserRole + 3
    StickyRole = Qt.UserRole + 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mRoundedRectSizePixels = 5
        self.mColor = QColor(Qt.white)
        self.mDismissRect = QRect()
        self.mDismissRectSize = QSize()
        fontMetrics = QgsApplication.fontMetrics()
        self.mRoundedRectSizePixels = int(Qgis.UI_SCALE_FACTOR * fontMetrics.height() * 0.5)
        self.mDismissRectSize = QSize(20, 20)  # TODO - hidpi friendly

    def paint(self, painter, option, index):
        # QgsScopedQPainterState painterState( painter );
        painter.save()
        try:
            doc = QTextDocument()
            icon = index.data(Qt.DecorationRole)
            if not isinstance(icon, QPixmap):
                icon = QPixmap()

            ctx = QAbstractTextDocumentLayout.PaintContext()
            optionV4 = option

            color = QColor(optionV4.palette.color(QPalette.Active, QPalette.Window))
            if option.state & QStyle.State_Selected and option.state & QStyle.State_HasFocus:
                color.setAlpha(40)
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Active, QPalette.HighlightedText))

                style = option.widget.style() if option.widget is not None else QgsApplication.style()
                style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, None)
            elif option.state & QStyle.State_Enabled:
                if option.state & QStyle.State_Selected:
                    color.setAlpha(40)
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Active, QPalette.Text))

                style = option.widget.style() if option.widget is not None else QgsApplication.style()
                style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, None)
            else:
                ctx.palette.setColor(QPalette.Text, optionV4.palette.color(QPalette.Disabled, QPalette.Text))

            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setPen(QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(color))
            _drawRoundedRect(painter, option.rect.left() + 0.625 * self.mRoundedRectSizePixels, option.rect.top() + 0.625 * self.mRoundedRectSizePixels,
                             option.rect.width() - 2 * 0.625 * self.mRoundedRectSizePixels, option.rect.height() - 2 * 0.625 * self.mRoundedRectSizePixels, self.mRoundedRectSizePixels, self.mRoundedRectSizePixels)

            titleSize = int(QgsApplication.fontMetrics().height() * 1.1)
            textSize = int(titleSize * 0.85)
            iconSize = QSize(icon.size())
            w = option.styleObject
            if isinstance(w, QWidget):
                iconSize = QSize(int(iconSize.width() / w.devicePixelRatioF()), int(iconSize.height() / w.devicePixelRatioF()))

            pinImage = _pinImageTag() if index.data(QgsNewsItemListItemDelegate.StickyRole) else ''
            doc.setHtml("<div style='font-size:{textSize}px'><span style='font-size:{titleSize}px;font-weight:bold;'>{title}{pin}</span>{content}</div>".format(
                textSize=textSize, titleSize=float(titleSize),
                title=index.data(QgsNewsItemListItemDelegate.TitleRole) or '',
                pin=pinImage,
                content=index.data(QgsNewsItemListItemDelegate.ContentRole) or ''))

            doc.setTextWidth(option.rect.width() - (iconSize.width() + 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 4.375 * self.mRoundedRectSizePixels))

            if not icon.isNull():
                _drawPixmap(painter, option.rect.left() + 1.25 * self.mRoundedRectSizePixels, option.rect.top() + 1.25 * self.mRoundedRectSizePixels,
                            iconSize.width(), iconSize.height(), icon)

            # Gross, but not well supported in Qt
            self.mDismissRect = QRect(option.rect.width() - 32, option.rect.top() + 10, self.mDismissRectSize.width(), self.mDismissRectSize.height())
            pixmap = QgsApplication.getThemeIcon('/mIconClearItem.svg').pixmap(self.mDismissRectSize, QIcon.Normal)
            painter.drawPixmap(self.mDismissRect.topLeft(), pixmap)
            self.mDismissRect.setTop(10)

            painter.translate(option.rect.left() + (iconSize.width() + 3.125 * self.mRoundedRectSizePixels if not icon.isNull() else 1.875 * self.mRoundedRectSizePixels),
                              option.rect.top() + 1.875 * self.mRoundedRectSizePixels)
            ctx.clip = QRectF(0, 0, option.rect.width() - (iconSize.width() - 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 3.125 * self.mRoundedRectSizePixels),
                              option.rect.height() - 3.125 * self.mRoundedRectSizePixels)
            doc.documentLayout().draw(painter, ctx)
        finally:
            # ~QgsScopedQPainterState()
            painter.restore()

    def sizeHint(self, option, index):
        doc = QTextDocument()
        icon = index.data(Qt.DecorationRole)
        if not isinstance(icon, QPixmap):
            icon = QPixmap()
        iconSize = QSize(icon.size())
        w = option.styleObject
        if isinstance(w, QWidget):
            iconSize = QSize(int(iconSize.width() / w.devicePixelRatioF()), int(iconSize.height() / w.devicePixelRatioF()))

        if option.rect.width() < 450:
            width = 450
        else:
            width = option.rect.width()

        titleSize = int(QgsApplication.fontMetrics().height() * 1.1)
        textSize = int(titleSize * 0.85)
        pinImage = '<img src=":/images/themes/default/pin.svg">' if index.data(QgsNewsItemListItemDelegate.StickyRole) else ''
        doc.setHtml("<div style='font-size:{textSize}px'><span style='font-size:{titleSize}px;font-weight:bold;'>{title}{pin}</span>{content}</div>".format(
            textSize=textSize, titleSize=float(titleSize),
            title=index.data(QgsNewsItemListItemDelegate.TitleRole) or '',
            pin=pinImage,
            content=index.data(QgsNewsItemListItemDelegate.ContentRole) or ''))
        doc.setTextWidth(width - (iconSize.width() + 4.375 * self.mRoundedRectSizePixels if not icon.isNull() else 4.375 * self.mRoundedRectSizePixels))

        return QSize(width, int(max(doc.size().height() + 1.25 * self.mRoundedRectSizePixels, float(iconSize.height())) + 2.5 * self.mRoundedRectSizePixels))

    def dismissRect(self):
        """Returns the area corresponding to the dismiss rectangle."""
        return self.mDismissRect

    def dismissRectSize(self):
        return self.mDismissRectSize
