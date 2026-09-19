"""QGIS 3.34 annotation selection, hover and native CAD edit operations."""
from qgis.PyQt.QtCore import Qt, QEvent, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMenu
from qgis.core import (Qgis, QgsAnnotationLayer, QgsGeometry, QgsRectangle,
    QgsCoordinateTransform, QgsAnnotationItemEditOperationTranslateItem,
    QgsAnnotationItemEditOperationMoveNode, QgsAnnotationItemEditOperationDeleteNode,
    QgsAnnotationItemEditOperationAddNode, QgsPoint, QgsPointXY, QgsCsException,
    QgsPointLocator)
from qgis.gui import QgsMapToolAdvancedDigitizing, QgsRubberBand, QgsSnapIndicator


class QgsMapToolModifyAnnotation(QgsMapToolAdvancedDigitizing):
    itemSelected = pyqtSignal(object, str)
    selectionCleared = pyqtSignal()
    NoAction, MoveItem, MoveNode = range(3)

    def __init__(self, canvas, app):
        super().__init__(canvas, app.mAdvancedDigitizingDockWidget)
        self.mApp = app
        self.mSelectedItemId = self.mSelectedItemLayerId = ''
        self.mHoveredItemId = self.mHoveredItemLayerId = ''
        self.mBounds = self.mHoverBounds = None
        self.mTargetNode = self.mSelectedNode = self.mPressPoint = None
        self.mNodes, self.mHoveredNodes = [], []
        self.mCurrentAction = self.NoAction
        self.mLastMapPoint = None
        self.mSkipContextMenu = False
        self.mShutdown = False
        self.mSnapIndicator = QgsSnapIndicator(canvas)
        self.setAutoSnapEnabled(True)
        self.mRubberBand = self.createBand(Qgis.GeometryType.Line, QColor(50, 50, 50, 200))
        self.mHoverRubberBand = self.createBand(Qgis.GeometryType.Line, QColor(100, 100, 100, 155))
        self.mNodeRubberBand = self.createBand(Qgis.GeometryType.Point, QColor(200, 0, 120))
        self.mNodeRubberBand.setIcon(QgsRubberBand.ICON_BOX)
        self.mHoveredNodeRubberBand = self.createBand(Qgis.GeometryType.Point, QColor(200, 0, 120))
        self.mHoveredNodeRubberBand.setIcon(QgsRubberBand.ICON_FULL_BOX)
        self.mTemporaryRubberBand = self.createBand(Qgis.GeometryType.Line, QColor(255, 120, 0, 180))
        self.setCursor(Qt.ArrowCursor)
        canvas.mapCanvasRefreshed.connect(self.onCanvasRefreshed)
        canvas.viewport().installEventFilter(self)
        app.mProject.layersWillBeRemoved.connect(self.layersWillBeRemoved)
        app.mProject.cleared.connect(self.projectCleared)

    def createBand(self, geometryType, color):
        band = QgsRubberBand(self.canvas(), geometryType)
        scale = int(max(1., self.canvas().fontMetrics().xHeight() * .2))
        band.setWidth(scale)
        band.setIconSize(scale * 5)
        band.setColor(color)
        band.setFillColor(QColor(0, 0, 0, 0))
        band.setSecondaryStrokeColor(QColor(255, 255, 255, 100))
        band.hide()
        return band

    def annotationLayerFromId(self, layerId):
        project = self.mApp.mProject
        layer = project.mainAnnotationLayer() if project.mainAnnotationLayer().id() == layerId else project.mapLayer(layerId)
        return layer if isinstance(layer, QgsAnnotationLayer) else None

    def selectedLayer(self): return self.annotationLayerFromId(self.mSelectedItemLayerId)

    def findClosestItemToPoint(self, point, items):
        closest, score = None, None
        for detail in items:
            layer = self.annotationLayerFromId(detail.layerId())
            item = layer.item(detail.itemId()) if layer else None
            if item is None: continue
            bounds = QgsRectangle(detail.boundingBox())
            candidateScore = (0. if bounds.contains(point) else bounds.distance(point), -item.zIndex())
            if score is None or candidateScore < score:
                score = candidateScore
                # Render results are borrowed. Store IDs and a copied rectangle.
                closest = (detail.layerId(), detail.itemId(), bounds)
        return closest

    def itemAtPoint(self, point):
        results = self.canvas().renderedItemResults(False)
        if results is None: return None
        bounds = QgsRectangle(point.x(), point.y(), point.x(), point.y())
        bounds.grow(self.searchRadiusMU(self.canvas()))
        return self.findClosestItemToPoint(point, results.renderedAnnotationItemsInBounds(bounds))

    def nodesForItem(self, layerId, itemId):
        layer = self.annotationLayerFromId(layerId)
        item = layer.item(itemId) if layer else None
        if item is None: return []
        transform = QgsCoordinateTransform(layer.crs(), self.canvas().mapSettings().destinationCrs(), self.mApp.mProject)
        nodes = []
        for node in item.nodes():
            try: nodes.append((node, transform.transform(node.point())))
            except QgsCsException: continue
        return nodes

    def showBounds(self, bounds, band=None):
        band = band or self.mRubberBand
        points = [QgsPointXY(bounds.xMinimum(), bounds.yMinimum()), QgsPointXY(bounds.xMinimum(), bounds.yMaximum()),
                  QgsPointXY(bounds.xMaximum(), bounds.yMaximum()), QgsPointXY(bounds.xMaximum(), bounds.yMinimum()),
                  QgsPointXY(bounds.xMinimum(), bounds.yMinimum())]
        band.setToGeometry(QgsGeometry.fromPolylineXY(points), None)
        band.show()

    def setHoveredItem(self, layerId, itemId, bounds):
        self.mHoveredItemLayerId, self.mHoveredItemId = layerId, itemId
        self.mHoverBounds = QgsRectangle(bounds)
        self.showBounds(bounds, self.mHoverRubberBand)
        self.mHoveredNodes = self.nodesForItem(layerId, itemId)
        self.mNodeRubberBand.reset(Qgis.GeometryType.Point)
        for _, point in self.mHoveredNodes: self.mNodeRubberBand.addPoint(point)
        self.mNodeRubberBand.show()

    def clearHoveredItem(self):
        self.mHoveredItemId = self.mHoveredItemLayerId = ''
        self.mHoverBounds = None
        self.mHoveredNodes.clear()
        for band in (self.mHoverRubberBand, self.mNodeRubberBand, self.mHoveredNodeRubberBand): band.hide()
        if self.mCurrentAction == self.NoAction: self.setCursor(Qt.ArrowCursor)

    def updateHoveredItem(self, point):
        closest = self.itemAtPoint(point)
        if closest is None:
            self.clearHoveredItem()
            return False
        layerId, itemId, bounds = closest
        if (layerId, itemId) != (self.mHoveredItemLayerId, self.mHoveredItemId):
            self.setHoveredItem(layerId, itemId, bounds)
        else: self.showBounds(bounds, self.mHoverRubberBand)
        selected = (layerId, itemId) == (self.mSelectedItemLayerId, self.mSelectedItemId)
        node = self.nearestNode(point) if selected else None
        self.mHoveredNodeRubberBand.hide()
        if node is not None:
            location = next(p for n, p in self.mNodes if n.id() == node.id())
            self.mHoveredNodeRubberBand.reset(Qgis.GeometryType.Point)
            self.mHoveredNodeRubberBand.addPoint(location)
            self.mHoveredNodeRubberBand.show()
        self.setCursor(Qt.OpenHandCursor if selected and node is None else Qt.ArrowCursor)
        return True

    def selectHoveredItem(self):
        if not self.mHoveredItemId: return False
        self.mSelectedItemLayerId, self.mSelectedItemId = self.mHoveredItemLayerId, self.mHoveredItemId
        self.mSelectedNode = None
        self.mBounds = QgsRectangle(self.mHoverBounds)
        self.showBounds(self.mBounds)
        self.updateNodes()
        self.itemSelected.emit(self.selectedLayer(), self.mSelectedItemId)
        return True

    def pick(self, point):
        if not self.updateHoveredItem(point):
            self.clearSelection()
            return False
        return self.selectHoveredItem()

    def updateNodes(self):
        self.mNodes = self.nodesForItem(self.mSelectedItemLayerId, self.mSelectedItemId)
        if self.mSelectedNode is not None:
            self.mSelectedNode = next((n for n, _ in self.mNodes if n.id() == self.mSelectedNode.id()), None)

    def nearestNode(self, point):
        layer = self.selectedLayer()
        if layer is None or layer.item(self.mSelectedItemId) is None or not self.mNodes: return None
        node, location = min(self.mNodes, key=lambda pair: pair[1].sqrDist(point))
        return node if location.sqrDist(point) <= self.searchRadiusMU(self.canvas()) ** 2 else None

    def translationOperation(self, start, end):
        layer = self.selectedLayer()
        if layer is None: return None
        transform = QgsCoordinateTransform(self.canvas().mapSettings().destinationCrs(), layer.crs(), self.mApp.mProject)
        start, end = transform.transform(start), transform.transform(end)
        return QgsAnnotationItemEditOperationTranslateItem(self.mSelectedItemId, end.x() - start.x(), end.y() - start.y())

    def moveNodeOperation(self, point):
        layer = self.selectedLayer()
        if layer is None or self.mTargetNode is None: return None
        return QgsAnnotationItemEditOperationMoveNode(self.mSelectedItemId, self.mTargetNode.id(),
            QgsPoint(self.mTargetNode.point()), QgsPoint(self.toLayerCoordinates(layer, point)))

    def applyOperation(self, operation):
        layer = self.selectedLayer()
        if layer is None or operation is None or layer.item(self.mSelectedItemId) is None: return False
        result = layer.applyEdit(operation)
        if result == Qgis.AnnotationItemEditOperationResult.Invalid:
            self.mApp.mMessageBar.pushWarning('修改注记', '此注记不支持该操作，或操作会产生无效几何')
            return False
        self.mApp.mProject.setDirty(True)
        if result == Qgis.AnnotationItemEditOperationResult.ItemCleared:
            self.clearSelection()
            self.clearHoveredItem()
        else: self.updateNodes()
        layer.triggerRepaint()
        return True

    def previewOperation(self, operation):
        self.mTemporaryRubberBand.hide()
        layer = self.selectedLayer()
        item = layer.item(self.mSelectedItemId) if layer else None
        if item is None or operation is None: return
        preview = item.transientEditResults(operation)
        if preview is not None:
            geometry = preview.representativeGeometry()
            if geometry.isEmpty(): return
            self.mTemporaryRubberBand.reset(geometry.type())
            self.mTemporaryRubberBand.setToGeometry(geometry, layer.crs())
            self.mTemporaryRubberBand.show()

    def refreshSelection(self):
        if self.mShutdown or self.canvas().mapTool() is not self: return
        layer = self.selectedLayer()
        if layer is None or layer.item(self.mSelectedItemId) is None:
            self.clearSelection()
            return
        if self.mCurrentAction != self.NoAction: return
        self.mRubberBand.hide()
        results = self.canvas().renderedItemResults(False)
        if results is None: return
        for detail in results.renderedAnnotationItemsInBounds(self.canvas().extent()):
            if (detail.layerId(), detail.itemId()) == (self.mSelectedItemLayerId, self.mSelectedItemId):
                self.mBounds = QgsRectangle(detail.boundingBox())
                self.showBounds(self.mBounds)
                self.updateNodes()
                return

    def onCanvasRefreshed(self):
        if self.mShutdown or self.canvas().mapTool() is not self: return
        self.refreshSelection()
        if self.mCurrentAction == self.NoAction:
            self.clearHoveredItem()
            if self.mLastMapPoint is not None: self.updateHoveredItem(self.mLastMapPoint)

    def showProperties(self):
        layer = self.selectedLayer()
        if layer is None or layer.item(self.mSelectedItemId) is None: return
        self.mApp.mapStyleDock(True)
        self.mApp.mLayerStylingWidget.setAnnotationItem(layer, self.mSelectedItemId)

    def stopOperation(self):
        self.mCurrentAction = self.NoAction
        self.mPressPoint = self.mTargetNode = None
        self.mTemporaryRubberBand.hide()
        self.mSnapIndicator.setMatch(QgsPointLocator.Match())
        self.cadDockWidget().clearPoints()
        self.setCursor(Qt.ArrowCursor)
        self.refreshSelection()
        self.clearHoveredItem()
        if self.mLastMapPoint is not None: self.updateHoveredItem(self.mLastMapPoint)

    def cadCanvasMoveEvent(self, event):
        event.snapPoint()
        self.mSnapIndicator.setMatch(event.mapPointMatch())
        self.mLastMapPoint = QgsPointXY(event.mapPoint())
        try:
            if self.mCurrentAction == self.MoveNode:
                self.previewOperation(self.moveNodeOperation(event.mapPoint()))
            elif self.mCurrentAction == self.MoveItem:
                self.previewOperation(self.translationOperation(self.mPressPoint, event.mapPoint()))
            else: self.updateHoveredItem(event.mapPoint())
        except QgsCsException as error:
            self.mTemporaryRubberBand.hide()
            self.mApp.statusBar().showMessage('注记坐标转换失败：' + str(error), 3000)

    def cadCanvasPressEvent(self, event):
        if self.mCurrentAction != self.NoAction:
            if event.button() == Qt.RightButton:
                self.mSkipContextMenu = True
                self.stopOperation()
            elif event.button() == Qt.LeftButton:
                event.snapPoint()
                try:
                    operation = self.moveNodeOperation(event.mapPoint()) if self.mCurrentAction == self.MoveNode else self.translationOperation(self.mPressPoint, event.mapPoint())
                    self.applyOperation(operation)
                except QgsCsException as error:
                    self.mApp.mMessageBar.pushWarning('修改注记', '坐标转换失败：' + str(error))
                finally: self.stopOperation()
            return
        if event.button() != Qt.LeftButton: return
        event.snapPoint()
        self.mLastMapPoint = QgsPointXY(event.mapPoint())
        if not self.updateHoveredItem(event.mapPoint()):
            self.clearSelection()
            return
        selected = (self.mSelectedItemLayerId, self.mSelectedItemId) == (self.mHoveredItemLayerId, self.mHoveredItemId)
        if not selected:
            self.selectHoveredItem()
            self.showProperties()
            return
        self.mTargetNode = self.nearestNode(event.mapPoint())
        self.mSelectedNode = self.mTargetNode
        self.mPressPoint = QgsPointXY(event.mapPoint())
        self.mCurrentAction = self.MoveNode if self.mTargetNode is not None else self.MoveItem
        self.mHoverRubberBand.hide()
        self.mRubberBand.hide()
        self.mNodeRubberBand.hide()
        self.mHoveredNodeRubberBand.hide()
        self.setCursor(Qt.CrossCursor if self.mTargetNode is not None else Qt.ClosedHandCursor)

    def cadCanvasReleaseEvent(self, event):
        if event.button() != Qt.RightButton: return
        if self.mSkipContextMenu:
            self.mSkipContextMenu = False
            return
        if self.mCurrentAction != self.NoAction or not self.pick(event.mapPoint()): return
        self.mSelectedNode = self.nearestNode(event.mapPoint())
        menu = QMenu(self.mApp)
        menu.addAction('注记属性', self.showProperties)
        if self.mSelectedNode is not None: menu.addAction('删除节点', self.deleteNode)
        layer = self.selectedLayer()
        item = layer.item(self.mSelectedItemId) if layer else None
        if item and item.type() in ('polygon', 'linestring', 'linetext'):
            point = QgsPointXY(event.mapPoint())
            menu.addAction('添加节点', lambda: self.addNode(point))
        menu.addAction('删除注记', self.deleteSelected)
        menu.exec_(self.canvas().mapToGlobal(event.pos()))
        menu.deleteLater()

    def translateItem(self, start, end):
        return self.applyOperation(self.translationOperation(start, end))

    def addNode(self, point):
        layer = self.selectedLayer()
        if layer is None: return False
        self.mSelectedNode = None
        return self.applyOperation(QgsAnnotationItemEditOperationAddNode(self.mSelectedItemId, QgsPoint(self.toLayerCoordinates(layer, point))))

    def deleteNode(self):
        node = self.mTargetNode or self.mSelectedNode
        if node is None: return
        self.mSelectedNode = None
        self.applyOperation(QgsAnnotationItemEditOperationDeleteNode(self.mSelectedItemId, node.id(), QgsPoint(node.point())))
        self.stopOperation()

    def canvasDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton or self.mCurrentAction == self.MoveNode: return
        self.stopOperation()
        event.snapPoint()
        if not self.updateHoveredItem(event.mapPoint()): return
        if (self.mHoveredItemLayerId, self.mHoveredItemId) == (self.mSelectedItemLayerId, self.mSelectedItemId):
            try: self.addNode(event.mapPoint())
            except QgsCsException as error: self.mApp.mMessageBar.pushWarning('修改注记', str(error))
        else:
            self.selectHoveredItem()
            self.showProperties()

    def deltaForKeyEvent(self, event):
        handle = self.canvas().window().windowHandle()
        dpi = handle.screen().physicalDotsPerInch() if handle and handle.screen() else self.canvas().logicalDpiX()
        pixels = 20. / 25.4 * dpi if event.modifiers() & Qt.ShiftModifier else 1. if event.modifiers() & Qt.AltModifier else 5. / 25.4 * dpi
        dx, dy = {Qt.Key_Left: (-pixels, 0), Qt.Key_Right: (pixels, 0), Qt.Key_Up: (0, -pixels), Qt.Key_Down: (0, pixels)}[event.key()]
        center = self.mBounds.center()
        transform = self.canvas().getCoordinateTransform()
        screen = transform.transform(center)
        return center, transform.toMapCoordinatesF(screen.x() + dx, screen.y() + dy)

    def deleteSelected(self):
        layer = self.selectedLayer()
        if layer is None or layer.item(self.mSelectedItemId) is None: return
        layer.removeItem(self.mSelectedItemId)
        self.mApp.mProject.setDirty(True)
        self.clearSelection()
        self.clearHoveredItem()
        layer.triggerRepaint()

    def clearSelection(self):
        layer = self.selectedLayer()
        hadSelection = bool(self.mSelectedItemId)
        self.mSelectedItemLayerId = self.mSelectedItemId = ''
        self.mCurrentAction = self.NoAction
        self.mPressPoint = self.mTargetNode = self.mSelectedNode = self.mBounds = None
        self.mNodes.clear()
        self.mRubberBand.hide()
        self.mTemporaryRubberBand.hide()
        if hadSelection:
            self.selectionCleared.emit()
            if layer is not None and not self.mShutdown and hasattr(self.mApp, 'mLayerStylingWidget'):
                self.mApp.mLayerStylingWidget.setAnnotationItem(layer, '')

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            if self.mCurrentAction != self.NoAction: self.stopOperation()
            else: self.clearSelection(); self.clearHoveredItem()
            event.ignore()
        elif key in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.mCurrentAction == self.MoveNode: self.deleteNode()
            elif self.mCurrentAction == self.NoAction: self.deleteSelected()
            event.ignore()  # QgsMapCanvas treats ignored map-tool keys as consumed.
        elif key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and self.mSelectedItemId:
            if self.mCurrentAction == self.NoAction and self.mBounds is not None:
                try: self.translateItem(*self.deltaForKeyEvent(event))
                except QgsCsException as error: self.mApp.mMessageBar.pushWarning('修改注记', str(error))
            event.ignore()
        else: super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        # A tool can outlive its canvas (window teardown, canvas-less harness), so
        # the viewport comparison must not assume canvas() is still valid.
        canvas = self.canvas()
        if canvas is not None and watched is canvas.viewport() and event.type() == QEvent.Leave:
            self.mLastMapPoint = None
            if self.mCurrentAction == self.NoAction: self.clearHoveredItem()
            self.mSnapIndicator.setMatch(QgsPointLocator.Match())
        return super().eventFilter(watched, event)

    def layersWillBeRemoved(self, layerIds):
        if self.mSelectedItemLayerId in layerIds: self.clearSelection()
        if self.mHoveredItemLayerId in layerIds: self.clearHoveredItem()

    def projectCleared(self):
        self.clearSelection()
        self.clearHoveredItem()
        self.mLastMapPoint = None
        self.mSnapIndicator.setMatch(QgsPointLocator.Match())

    def deactivate(self):
        self.projectCleared()
        self.cadDockWidget().clearPoints()
        super().deactivate()

    def shutdown(self):
        from qgis.PyQt import sip
        self.mShutdown = True
        # The canvas may already be gone during teardown; native keeps it as a
        # member, here it is resolved through the app, so guard the access.
        canvas = self.canvas()
        if canvas is not None:
            canvas.mapCanvasRefreshed.disconnect(self.onCanvasRefreshed)
            canvas.viewport().removeEventFilter(self)
        self.mApp.mProject.layersWillBeRemoved.disconnect(self.layersWillBeRemoved)
        self.mApp.mProject.cleared.disconnect(self.projectCleared)
        self.mSnapIndicator.setMatch(QgsPointLocator.Match())
        for band in (self.mRubberBand, self.mHoverRubberBand, self.mNodeRubberBand,
                     self.mHoveredNodeRubberBand, self.mTemporaryRubberBand):
            if canvas is not None:
                canvas.scene().removeItem(band)
            sip.delete(band)
