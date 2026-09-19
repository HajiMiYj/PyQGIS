"""Layout designer controller port using native QgsLayoutView and layout items.

Currently provides item selection/movement, common items, undo and exports.
This is not yet a port of every upstream designer property panel.
"""
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar, QFileDialog, QInputDialog, QDockWidget, QFormLayout, QWidget, QDoubleSpinBox, QLineEdit, QPushButton
from qgis.core import QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemScaleBar, QgsLayoutItemPicture, QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize, QgsLayoutExporter
from qgis.gui import QgsLayoutView, QgsLayoutViewToolSelect, QgsLayoutViewToolPan, QgsLayoutViewToolZoom


class QgsLayoutDesignerDialog(QMainWindow):
    def __init__(self, app, layout):
        super().__init__(app, Qt.Window)
        self.mApp, self.mLayout = app, layout
        self.setObjectName('QgsLayoutDesignerDialog')
        self.setWindowTitle((layout.name() if hasattr(layout, 'name') else '报表章节') + ' — 布局设计器')
        self.resize(1200, 800)
        self.mView = QgsLayoutView(self)
        self.mView.setCurrentLayout(layout)
        self.setCentralWidget(self.mView)
        self.mTools = [QgsLayoutViewToolSelect(self.mView), QgsLayoutViewToolPan(self.mView), QgsLayoutViewToolZoom(self.mView)]
        self.mView.setTool(self.mTools[0])
        self.mLayoutToolbar = self.addToolBar(QCoreApplication.translate('QgsLayoutDesignerDialog', 'Layout'))
        self.mLayoutToolbar.setObjectName('mLayoutToolbar')
        self.mLayoutToolbar.addAction(QCoreApplication.translate('MainWindow', 'Save Project'), app.fileSave)
        self.mLayoutToolbar.addAction('PDF', self.exportToPdf)
        self.mLayoutToolbar.addAction(QCoreApplication.translate('MainWindow', 'Image'), self.exportToImage)
        self.mLayoutToolbar.addAction('SVG', self.exportToSvg)
        self.mLayoutToolbar.addAction(QCoreApplication.translate('MainWindow', 'Undo'), layout.undoStack().stack().undo)
        self.mLayoutToolbar.addAction(QCoreApplication.translate('MainWindow', 'Redo'), layout.undoStack().stack().redo)
        self.mLayoutToolbar.addAction('全页', self.mView.zoomFull)
        self.mToolsToolbar = self.addToolBar(QCoreApplication.translate('AddModelFromFileAction', 'Tools'))
        self.mToolsToolbar.setObjectName('mToolsToolbar')
        for name, tool in zip(['选择/移动', '平移', '缩放'], self.mTools):
            self.mToolsToolbar.addAction(name, lambda checked=False, t=tool: self.mView.setTool(t))
        for name, kind in [('地图', 'map'), ('标签', 'label'), ('图例', 'legend'), ('比例尺', 'scale'), ('图片/指北针', 'picture'), ('矩形', 'shape')]:
            self.mToolsToolbar.addAction('添加' + name, lambda checked=False, k=kind: self.addItem(k))
        self.mToolsToolbar.addAction('删除选中项', self.deleteItems)
        self.mItemPropertiesDock = QDockWidget('项目属性', self)
        self.mItemPropertiesDock.setObjectName('ItemProperties')
        widget = QWidget()
        form = QFormLayout(widget)
        self.mItemId = QLineEdit()
        form.addRow('项目 ID', self.mItemId)
        self.mItemLabel = QLineEdit()
        form.addRow('标签文字', self.mItemLabel)
        self.mPosition = []
        for name in ['X（毫米）', 'Y（毫米）', '宽度（毫米）', '高度（毫米）', '旋转角度']:
            spin = QDoubleSpinBox()
            spin.setRange(-10000, 10000)
            spin.setDecimals(2)
            form.addRow(name, spin)
            self.mPosition.append(spin)
        button = QPushButton('应用到选中项目')
        button.clicked.connect(self.applyItemProperties)
        form.addRow(button)
        self.mItemPropertiesDock.setWidget(widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.mItemPropertiesDock)
        layout.selectedItemChanged.connect(self.showItemOptions)
        layout.destroyed.connect(self.close)
        self.mCurrentItem = None
        self.mView.zoomFull()

    def addItem(self, kind):
        classes = {'map': QgsLayoutItemMap, 'label': QgsLayoutItemLabel, 'legend': QgsLayoutItemLegend,
                   'scale': QgsLayoutItemScaleBar, 'picture': QgsLayoutItemPicture, 'shape': QgsLayoutItemShape}
        item = classes[kind](self.mLayout)
        self.mLayout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(20, 20))
        item.attemptResize(QgsLayoutSize(60, 30))
        if kind == 'map':
            item.setLayers(self.mApp.mMapCanvas.layers())
            item.setCrs(self.mApp.mMapCanvas.mapSettings().destinationCrs())
            item.zoomToExtent(self.mApp.mMapCanvas.extent())
        elif kind == 'label': item.setText('标签')
        elif kind in ('legend', 'scale'):
            maps = [i for i in self.mLayout.items() if isinstance(i, QgsLayoutItemMap)]
            if maps: item.setLinkedMap(maps[0])
            if kind == 'scale': item.applyDefaultSize()
        elif kind == 'picture':
            path, _ = QFileDialog.getOpenFileName(self, QCoreApplication.translate('QObject', 'Picture'), '', '图片 (*.svg *.png *.jpg)')
            if path: item.setPicturePath(path)
        self.mLayout.setSelectedItem(item)

    def showItemOptions(self, item):
        self.mCurrentItem = item
        if item is None: return
        self.mItemId.setText(item.id())
        self.mItemLabel.setText(item.text() if isinstance(item, QgsLayoutItemLabel) else '')
        for spin, value in zip(self.mPosition, [item.positionWithUnits().x(), item.positionWithUnits().y(), item.sizeWithUnits().width(), item.sizeWithUnits().height(), item.itemRotation()]):
            spin.setValue(value)

    def applyItemProperties(self):
        item = self.mCurrentItem
        if item is None: return
        x, y, w, h, angle = [spin.value() for spin in self.mPosition]
        item.beginCommand('修改项目属性')
        item.setId(self.mItemId.text())
        item.attemptMove(QgsLayoutPoint(x, y))
        item.attemptResize(QgsLayoutSize(max(0.1, w), max(0.1, h)))
        item.setItemRotation(angle)
        if isinstance(item, QgsLayoutItemLabel): item.setText(self.mItemLabel.text())
        item.endCommand()
        item.refresh()

    def deleteItems(self):
        self.mCurrentItem = None
        for item in self.mLayout.selectedLayoutItems(): self.mLayout.removeLayoutItem(item)

    def export(self, kind):
        path, _ = QFileDialog.getSaveFileName(self, QCoreApplication.translate('QgsLayoutDesignerDialog', 'Export layout'), '', {'pdf': 'PDF (*.pdf)', 'image': 'PNG (*.png)', 'svg': 'SVG (*.svg)'}[kind])
        if not path: return
        exporter = QgsLayoutExporter(self.mLayout)
        if kind == 'pdf': result = exporter.exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
        elif kind == 'svg': result = exporter.exportToSvg(path, QgsLayoutExporter.SvgExportSettings())
        else: result = exporter.exportToImage(path, QgsLayoutExporter.ImageExportSettings())
        if result != QgsLayoutExporter.Success: self.mApp.mMessageBar.pushCritical('布局导出失败', str(result))
    def exportToPdf(self): self.export('pdf')
    def exportToImage(self): self.export('image')
    def exportToSvg(self): self.export('svg')
