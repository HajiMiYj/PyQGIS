"""Mesh frame actions through the bound 3.34 editor and expression scopes.

Native mesh/triangular-mesh pointers are SIP_SKIP. Read current vertex values
through native mesh expressions; never use a provider snapshot of unsaved edits.
Face operations currently target the native expression-selected face IDs.
"""
import json
import math
from pathlib import Path
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAction, QMenu, QMessageBox, QWidgetAction, QWidget,
    QGridLayout, QCheckBox, QComboBox, QLabel, QToolButton, QApplication)
from qgis.core import (Qgis, QgsMesh, QgsMeshLayer, QgsExpression, QgsExpressionContext,
    QgsExpressionContextUtils, QgsPoint, QgsPointXY, QgsGeometry, QgsCoordinateTransform,
    QgsApplication, QgsMeshEditRefineFaces, QgsRectangle, QgsSettings, QgsRenderContext,
    QgsMeshEditForceByPolylines, QgsLineString, QgsCsException, QgsMeshTransformVerticesByExpression)
from qgis.gui import (QgsMapToolAdvancedDigitizing, QgsRubberBand, QgsDoubleSpinBox,
    QgsUnitSelectionWidget, QgsIdentifyMenu)


class QgsMeshEditForceByLineAction(QWidgetAction):
    # This class is also defined in qgsmaptooleditmeshframe.cpp upstream.
    Mesh, Lines = range(2)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('mWidgetActionForceByLine')
        self.setText('线约束设置')
        settings = QgsSettings()
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(3, 2, 3, 2)
        self.mCheckBoxNewVertex = QCheckBox('在相交边上添加新顶点')
        self.mCheckBoxNewVertex.setChecked(settings.value('UI/Mesh/ForceByLineNewVertex', False, type=bool))
        self.mComboInterpolateFrom = QComboBox()
        self.mComboInterpolateFrom.addItem(QCoreApplication.translate('QgsMeshEditForceByLineAction', 'Mesh'), self.Mesh)
        self.mComboInterpolateFrom.addItem('约束线', self.Lines)
        mode = settings.value('UI/Mesh/ForceByLineInterpolateFrom', 'Mesh')
        self.mComboInterpolateFrom.setCurrentIndex(self.Lines if str(mode) in ('Lines', '1') else self.Mesh)
        self.mToleranceSpinBox = QgsDoubleSpinBox()
        self.mToleranceSpinBox.setRange(0, 1e12)
        self.mToleranceSpinBox.setDecimals(8)
        self.mToleranceSpinBox.setValue(settings.value('UI/Mesh/ForceByLineToleranceValue', 1., type=float))
        self.mToleranceSpinBox.setKeyboardTracking(False)
        self.mToleranceSpinBox.setSingleStep(.1)
        self.mToleranceSpinBox.setClearValue(1.)
        self.mUnitSelecionWidget = QgsUnitSelectionWidget()
        self.mUnitSelecionWidget.setUnits([Qgis.RenderUnit.MetersInMapUnits, Qgis.RenderUnit.MapUnits])
        unit = settings.value('UI/Mesh/ForceByLineToleranceUnit', 'MapUnits')
        meters = str(unit) in ('MetersInMapUnits', str(int(Qgis.RenderUnit.MetersInMapUnits)))
        self.mUnitSelecionWidget.setUnit(Qgis.RenderUnit.MetersInMapUnits if meters else Qgis.RenderUnit.MapUnits)
        layout.addWidget(self.mCheckBoxNewVertex, 1, 0, 1, 4)
        layout.addWidget(QLabel('Z 值插值来源'), 2, 0, 1, 3)
        layout.addWidget(self.mComboInterpolateFrom, 2, 3)
        layout.addWidget(QLabel(QCoreApplication.translate('QgsMeshEditForceByLineAction', 'Tolerance')), 3, 0, 1, 2)
        layout.addWidget(self.mToleranceSpinBox, 3, 2)
        layout.addWidget(self.mUnitSelecionWidget, 3, 3)
        self.setDefaultWidget(widget)
        self.mCheckBoxNewVertex.toggled.connect(self.updateSettings)
        self.mComboInterpolateFrom.currentIndexChanged.connect(self.updateSettings)
        self.mToleranceSpinBox.valueChanged.connect(self.updateSettings)
        self.mUnitSelecionWidget.changed.connect(self.updateSettings)

    def setMapCanvas(self, canvas): self.mUnitSelecionWidget.setMapCanvas(canvas)
    def interpolationMode(self): return self.mComboInterpolateFrom.currentData()
    def newVertexOnIntersectingEdge(self): return self.mCheckBoxNewVertex.isChecked()
    def toleranceValue(self): return self.mToleranceSpinBox.value()
    def toleranceUnit(self): return self.mUnitSelecionWidget.unit()

    def updateSettings(self, *args):
        settings = QgsSettings()
        settings.setValue('UI/Mesh/ForceByLineNewVertex', self.newVertexOnIntersectingEdge())
        settings.setValue('UI/Mesh/ForceByLineInterpolateFrom', 'Mesh' if self.interpolationMode() == self.Mesh else 'Lines')
        settings.setValue('UI/Mesh/ForceByLineToleranceValue', self.toleranceValue())
        settings.setValue('UI/Mesh/ForceByLineToleranceUnit', 'MetersInMapUnits' if self.toleranceUnit() == Qgis.RenderUnit.MetersInMapUnits else 'MapUnits')


class QgsMapToolEditMeshFrame(QgsMapToolAdvancedDigitizing):
    def __init__(self, canvas, cadDock, app):
        super().__init__(canvas, cadDock)
        self.mApp = app
        self.mCurrentLayer = None
        self.mSelectedVertices, self.mSelectedFaces = set(), set()
        self.mFaceVertices, self.mSelectionPoints = [], []
        self.mForcingPoints = []
        self.mCurrentState = 'Digitizing'
        self.mActions = {}
        self.mDialogs = []
        self.mTransformDockWidget = None
        self.mZValueWidget = None
        self.mShutdown = False
        self.mFailedSaves = set()
        self.mVertexCache = None
        self.mStartMovingPoint = None
        self.mMovingLayer = None
        self.mMovingVertices = []
        self.mMovingVerticesRubberBand = QgsRubberBand(canvas, Qgis.GeometryType.Point)
        self.mMovingVerticesRubberBand.setIconSize(9)
        self.mMovingVerticesRubberBand.hide()
        self.mSelectionRubberBand = QgsRubberBand(canvas, Qgis.GeometryType.Point)
        self.mSelectionRubberBand.setColor(QColor('yellow'))
        self.mSelectionRubberBand.setIconSize(7)
        self.mRubberBand = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.mRubberBand.setColor(QColor('orange'))
        self.mRubberBand.setWidth(2)
        self.mNewFaceBand = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self.mNewFaceBand.hide()
        self.mEdgeBand = QgsRubberBand(canvas, Qgis.GeometryType.Line)
        self.mEdgeBand.setColor(QColor(0, 180, 220, 160))
        self.mEdgeBand.setWidth(5)
        self.mEdgeBand.hide()
        self.setCursor(Qt.CrossCursor)
        self.setAutoSnapEnabled(True)

    def setupActions(self):
        callbacks = {
            'mActionDigitizing': lambda: self.activateWithState('Digitizing'),
            'mActionSelectByPolygon': lambda: self.activateWithState('Selecting'),
            'mActionSelectByExpression': self.showSelectByExpressionDialog,
            'mActionTransformCoordinates': self.triggerTransformCoordinatesDockWidget,
            'mActionReindexMesh': self.reindexMesh,
            'mActionRemoveVerticesFillingHole': lambda: self.removeSelectedVerticesFromMesh(True),
            'mActionRemoveVerticesWithoutFillingHole': lambda: self.removeSelectedVerticesFromMesh(False),
            'mActionRemoveFaces': self.removeFacesFromMesh,
            'mActionSplitFaces': self.splitSelectedFaces,
            'mActionFacesRefinement': self.refineSelectedFaces,
            'mActionDelaunayTriangulation': self.delaunayTriangulation,
            'mActionForceByLines': lambda: self.activateWithState('ForceByLines'),
        }
        catalog = Path(__file__).resolve().parents[3] / 'docs/upstream-toolbar-actions.json'
        for row in json.loads(catalog.read_text(encoding='utf-8'))['actions']:
            key = row['sourceKey'].removeprefix('mesh:')
            if key not in callbacks: continue
            action = QAction(QgsApplication.getThemeIcon(row.get('icon', '')), self.tr(row['text']), self)
            if row['objectName']: action.setObjectName(row['objectName'])
            if key in ('mActionDigitizing', 'mActionSelectByPolygon', 'mActionForceByLines'): action.setCheckable(True)
            action.triggered.connect(lambda checked=False, callback=callbacks[key]: callback())
            self.mActions[key] = action
            setattr(self, key, action)
            if row['location'] == 'toolbar': self.mApp.mMeshToolBar.addAction(action)
            elif row['location'] == 'mesh menu': self.mApp.mMeshMenu.addAction(action)
            note = '原生 QgsMeshEditor 操作，接入编辑状态与撤销；面操作使用表达式选中 ID，地图直接拾取面尚未移植。'
            if key == 'mActionReindexMesh': note = '原生图层 reindex；确认后重新编号顶点/面、清空选择并更新画布，撤销历史按原版清除。'
            if key in ('mActionRemoveVerticesFillingHole', 'mActionRemoveVerticesWithoutFillingHole'):
                note = '对选中顶点调用原生删除接口，反馈拓扑错误/未删除顶点并更新选择、画布和撤销状态。'
            if key == 'mActionDigitizing': note = '顶点添加/选择/移动；已有顶点构面及原生有效性预览；选择两个公共边端点后翻转边/合并面；所选顶点平均 Z 显示、回车统一高程、原版删除快捷键与撤销。边/面直接拾取与完整拖动仍待补齐。'
            if key == 'mActionSelectByPolygon': note = '多边形选择顶点，Shift 添加/Ctrl 移除；面触碰/完全包含选择未移植。'
            if key == 'mActionTransformCoordinates': note = '原版停靠 UI；原生 XYZ 表达式计算/拓扑与数值校验、顶点预览、缓存结果应用及撤销。先预览后应用；修改表达式/选区或编辑网孔使旧结果失效；坐标导入开关随单顶点选择更新，并遵循工程小数位数。上述交互检查通过；完整面边预览待补。'
            if key == 'mActionForceByLines': note = '左键绘制约束折线/右键完成，空闲时右键拾取线或面边界；捕捉 Z、CRS 转换、交点顶点、Z 插值、容差、原生网孔约束与撤销。'
            if key == 'mActionDelaunayTriangulation': note = '使用 analysis 中原生 QgsMeshEditingDelaunayTriangulation；选中至少三个顶点后在右键菜单执行，保留 Z、过滤内部顶点和不兼容面，提示原生结果并支持撤销/重做。'
            self.mApp.mDynamicActions[row['sourceKey']] = {'action': action, 'handler': key, 'toolbar': row['toolbar'], 'note': note, 'inInterface': True}
        self.mWidgetActionForceByLine = QgsMeshEditForceByLineAction(self)
        self.mWidgetActionForceByLine.setMapCanvas(self.canvas())
        self.mActions['mWidgetActionForceByLine'] = self.mWidgetActionForceByLine
        self.mForceByLineButton = QToolButton(self.mApp.mMeshToolBar)
        self.mForceByLineButton.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(self.mForceByLineButton)
        menu.addAction(self.mActionForceByLines)
        menu.addSeparator()
        menu.addAction(self.mWidgetActionForceByLine)
        self.mForceByLineButton.setMenu(menu)
        self.mForceByLineButton.setDefaultAction(self.mActionForceByLines)
        self.mApp.mMeshToolBar.insertWidget(self.mActionForceByLines, self.mForceByLineButton)
        self.mApp.mMeshToolBar.removeAction(self.mActionForceByLines)
        self.mApp.mDynamicActions['mesh:mWidgetActionForceByLine'] = {
            'action': self.mWidgetActionForceByLine, 'handler': 'updateSettings', 'toolbar': 'mMeshToolBar',
            'inInterface': True, 'note': '原版 QWidgetAction 四项设置、原版设置键持久化；直接用于线约束操作。'}
        self.mApp.mMeshToolBar.insertAction(self.mApp.mMeshToolBar.actions()[0] if self.mApp.mMeshToolBar.actions() else None, self.mApp.mActionToggleEditing)
        self.mApp.mMeshToolBar.addAction(self.mApp.mActionSaveLayerEdits)

    def layer(self):
        layer = self.mApp.activeLayer()
        return layer if isinstance(layer, QgsMeshLayer) and not sip.isdeleted(layer) else None

    def editor(self):
        layer = self.layer()
        return layer.meshEditor() if layer is not None and layer.isEditable() else None

    def warning(self, text): self.mApp.mMessageBar.pushWarning(QCoreApplication.translate('QgsMapToolEditMeshFrame', 'Mesh editing'), text)

    def transform(self, layer):
        return QgsCoordinateTransform(layer.crs(), self.canvas().mapSettings().destinationCrs(), self.mApp.mProject)

    def startEditing(self, layer, ask=True):
        if layer.isEditable(): return True
        if ask and layer.datasetGroupCount() > 0:
            answer = QMessageBox.warning(self.mApp, '编辑网孔框架', '进入框架编辑会移除当前数据集组。请先保存工程；结束编辑后可重新加载原数据集。是否继续？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes: return False
        success, error = layer.startFrameEditing(self.transform(layer), False)
        if not success:
            self.warning(f'无法开始编辑：{error.errorType}，元素 {error.elementIndex}')
            return False
        settings = layer.rendererSettings()
        native = settings.nativeMeshSettings()
        native.setEnabled(True)
        settings.setNativeMeshSettings(native)
        layer.setRendererSettings(settings)
        self.mApp.mUndoWidget.setStack(layer.undoStack())
        self.mApp.updateActionState()
        self.activateWithState('Digitizing')
        return True

    def saveEdits(self, layer, continueEditing=True):
        if not layer.isEditable(): return False
        # 3.34's stop-editing commit branch unconditionally returns true after
        # saveMeshFrame. Commit while editing so the provider result is retained.
        success = layer.commitFrameEditing(self.transform(layer), True)
        if not success:
            self.mFailedSaves.add(layer.id())
            self.warning('网孔保存失败；保留当前编辑供重试，请检查驱动和文件权限。原生提交可能已清空撤销历史。')
        else:
            self.mFailedSaves.discard(layer.id())
            if not continueEditing:
                success = layer.rollBackFrameEditing(self.transform(layer), False)
        self.onEdit()
        self.mApp.updateActionState()
        return success

    def stopEditing(self, layer):
        if not layer.isEditable(): return True
        if layer.isModified() or layer.id() in self.mFailedSaves:
            answer = QMessageBox.question(self.mApp, '保存网孔编辑', f'保存 {layer.name()} 的网孔框架修改？', QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if answer == QMessageBox.Cancel: return False
            if answer == QMessageBox.Save: return self.saveEdits(layer, False)
        result = layer.rollBackFrameEditing(self.transform(layer), False)
        if result: self.mFailedSaves.discard(layer.id())
        self.onEdit()
        self.mApp.updateActionState()
        return result

    def activateWithState(self, state):
        if not self.editor(): return
        self.cancelMovingSelection()
        self.mCurrentState = state
        self.mSelectionPoints.clear()
        self.mFaceVertices.clear()
        self.mNewFaceBand.hide()
        self.mForcingPoints.clear()
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        self.canvas().setMapTool(self)
        self.updateActions()

    def activate(self):
        super().activate()
        self.mZValueWidget = QgsDoubleSpinBox()
        self.mZValueWidget.setRange(-1e12, 1e12)
        self.mZValueWidget.setDecimals(6)
        self.mZValueWidget.setPrefix('Z：')
        self.mZValueWidget.setValue(QgsSettings().value('qgis/digitizing/default_z_value', 0., type=float))
        self.mZValueWidget.lineEdit().returnPressed.connect(self.applyZValueOnSelectedVertices)
        self.mApp.addUserInputWidget(self.mZValueWidget)
        message = ('左键确定约束折线各点，右键执行；未绘线时右键拾取已有线/面。下拉设置交点、Z 来源及容差。'
                   if self.mCurrentState == 'ForceByLines' else '双击添加顶点；单击选顶点，Shift 加选；再次点击已选顶点开始移动，再点击确认，右键/Esc 取消。Ctrl 左键依次选顶点，右键构面。')
        self.mApp.mMessageBar.pushInfo('网孔数字化', message)
        self.updateSelection()

    def deactivate(self):
        self.cancelMovingSelection()
        self.mForcingPoints.clear()
        self.mSelectionPoints.clear()
        self.mFaceVertices.clear()
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        self.mSelectionRubberBand.hide()
        self.mNewFaceBand.hide()
        self.mEdgeBand.hide()
        if self.mZValueWidget is not None: self.mZValueWidget.deleteLater()
        self.mZValueWidget = None
        super().deactivate()

    def vertices(self):
        layer = self.layer()
        if not self.editor(): return {}
        if self.mVertexCache is not None: return self.mVertexCache
        scope = QgsExpressionContextUtils.meshExpressionScope(QgsMesh.Vertex)
        scope.setVariable('_mesh_layer', layer)
        context = QgsExpressionContext([scope])
        expressions = [QgsExpression('$vertex_'+axis) for axis in 'xyz']
        for expression in expressions: expression.prepare(context)
        ids = layer.selectVerticesByExpression(QgsExpression('$vertex_x IS NOT NULL'))
        result = {}
        for index in ids:
            scope.setVariable('_mesh_vertex_index', index)
            values = [expression.evaluate(context) for expression in expressions]
            if all(isinstance(value, (int, float)) for value in values): result[index] = QgsPoint(*values)
        self.mVertexCache = result
        return result

    def nearestVertex(self, point):
        vertices = self.vertices()
        tolerance = self.canvas().mapUnitsPerPixel()*12
        distances = [(self.toMapCoordinates(self.layer(), QgsPointXY(v)).sqrDist(point), i) for i, v in vertices.items()]
        if not distances: return None
        distance, index = min(distances)
        return index if distance <= tolerance*tolerance else None

    def updateSelection(self):
        if self.mShutdown: return
        vertices = self.vertices()
        self.mSelectedVertices.intersection_update(vertices)
        self.mSelectionRubberBand.reset(Qgis.GeometryType.Point)
        for index in sorted(self.mSelectedVertices):
            self.mSelectionRubberBand.addPoint(self.toMapCoordinates(self.layer(), QgsPointXY(vertices[index])))
        if self.mZValueWidget is not None and self.mSelectedVertices and self.mStartMovingPoint is None:
            values = [vertices[index].z() for index in self.mSelectedVertices if math.isfinite(vertices[index].z())]
            if values: self.mZValueWidget.setValue(sum(values) / len(values))
        self.updateSelectedEdge()
        if self.canvas().mapTool() is self: self.mSelectionRubberBand.show()
        if self.mTransformDockWidget: self.mTransformDockWidget.updateSelection()
        self.mApp.statusBar().showMessage(f'网孔已选：{len(self.mSelectedVertices)} 个顶点，{len(self.mSelectedFaces)} 个面', 5000)
        self.updateActions()

    def updateActions(self):
        if self.mShutdown: return
        layer = self.layer()
        if self.mCurrentLayer is not layer:
            self.cancelMovingSelection()
            self.mCurrentLayer = layer
            self.mVertexCache = None
            self.mSelectedVertices.clear()
            self.mSelectedFaces.clear()
            self.mFaceVertices.clear()
            self.mForcingPoints.clear()
            self.mSelectionPoints.clear()
            self.mSelectionRubberBand.reset(Qgis.GeometryType.Point)
            if self.mTransformDockWidget: self.mTransformDockWidget.hide()
        editable = self.editor() is not None
        # Qt deletes the owned actions during teardown while this refresh can still
        # be queued from QgisApp.updateActionState(); skip the dead wrappers.
        from qgis.PyQt import sip as _sip
        for key, action in self.mActions.items():
            if _sip.isdeleted(action):
                continue
            enabled = editable
            if 'RemoveVertices' in key or key == 'mActionTransformCoordinates': enabled = enabled and bool(self.mSelectedVertices)
            if key == 'mActionDelaunayTriangulation': enabled = enabled and len(self.mSelectedVertices) >= 3
            if key in ('mActionRemoveFaces', 'mActionSplitFaces', 'mActionFacesRefinement'): enabled = enabled and bool(self.mSelectedFaces)
            action.setEnabled(enabled)
        canvas = self.canvas()
        if self.mActions and canvas is not None and not any(_sip.isdeleted(a) for a in self.mActions.values()):
            active = canvas.mapTool() is self
            self.mActionDigitizing.setChecked(active and self.mCurrentState == 'Digitizing')
            self.mActionSelectByPolygon.setChecked(active and self.mCurrentState == 'Selecting')
            self.mActionForceByLines.setChecked(active and self.mCurrentState == 'ForceByLines')
            if active and not editable: canvas.setMapTool(self.mApp.mMapTools['pan'])
        if layer is not None:
            self.mApp.mActionToggleEditing.setEnabled(layer.isValid() and layer.supportsEditing())
            self.mApp.mActionToggleEditing.setChecked(editable)
            self.mApp.mActionSaveLayerEdits.setEnabled(editable and (layer.isModified() or layer.id() in self.mFailedSaves))
            self.mApp.mActionUndo.setEnabled(editable and layer.undoStack().canUndo())
            self.mApp.mActionRedo.setEnabled(editable and layer.undoStack().canRedo())

    def onEdit(self):
        if self.mShutdown: return
        self.cancelMovingSelection()
        self.mVertexCache = None
        self.mFaceVertices.clear()
        self.mNewFaceBand.hide()
        self.mEdgeBand.hide()
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        layer = self.layer()
        if layer is not None:
            layer.triggerRepaint()
            if self.editor():
                self.mSelectedFaces.intersection_update(layer.selectFacesByExpression(QgsExpression('$face_area > 0')))
        self.updateSelection()

    def canvasDoubleClickEvent(self, event):
        if self.mCurrentState != 'Digitizing' or not self.editor() or event.button() != Qt.LeftButton: return
        self.cancelMovingSelection()
        z = self.mZValueWidget.value() if self.mZValueWidget else 0
        self.editor().addPointsAsVertices([QgsPoint(event.mapPoint().x(), event.mapPoint().y(), z)], self.canvas().mapUnitsPerPixel()*2)
        self.onEdit()

    def cadCanvasMoveEvent(self, event):
        if self.mStartMovingPoint is not None:
            self.moveSelection(event.mapPoint())
            return
        if self.mCurrentState == 'ForceByLines':
            self.updateForcingLinePreview(event.mapPoint())
            return
        points = self.mSelectionPoints[:]
        if self.mFaceVertices:
            vertices = self.vertices()
            points = [self.toMapCoordinates(self.layer(), QgsPointXY(vertices[i])) for i in self.mFaceVertices if i in vertices]
            self.updateNewFacePreview(event.mapPoint())
        if points:
            self.mRubberBand.setToGeometry(QgsGeometry.fromPolylineXY(points+[event.mapPoint()]), None)
            self.mRubberBand.show()

    def cadCanvasReleaseEvent(self, event):
        if not self.editor(): return
        if self.mStartMovingPoint is not None:
            if event.button() == Qt.RightButton: self.cancelMovingSelection()
            elif event.button() == Qt.LeftButton: self.applyMovingSelection(event.mapPoint())
            return
        if self.mCurrentState == 'ForceByLines':
            self.forceByLineReleaseEvent(event)
            return
        if self.mCurrentState == 'Selecting':
            if event.button() == Qt.LeftButton: self.mSelectionPoints.append(event.mapPoint())
            elif event.button() == Qt.RightButton:
                if len(self.mSelectionPoints) >= 3:
                    geometry = QgsGeometry.fromPolygonXY([self.mSelectionPoints+[self.mSelectionPoints[0]]])
                    ids = [i for i, v in self.vertices().items() if geometry.intersects(QgsGeometry.fromPointXY(self.toMapCoordinates(self.layer(), QgsPointXY(v))))]
                    self.setSelectedVertices(ids, self.behavior(event.modifiers()))
                self.mSelectionPoints.clear()
                self.mRubberBand.reset(Qgis.GeometryType.Line)
            return
        if event.button() == Qt.LeftButton:
            index = self.nearestVertex(event.mapPoint())
            if index is not None and event.modifiers() & Qt.ControlModifier:
                if index not in self.mFaceVertices: self.mFaceVertices.append(index)
                self.setSelectedVertices(self.mFaceVertices)
                self.updateNewFacePreview()
            elif index in self.mSelectedVertices and not event.modifiers() & Qt.ShiftModifier and not self.mFaceVertices:
                self.startMovingSelection(event.mapPoint())
            else: self.setSelectedVertices([] if index is None else [index], self.behavior(event.modifiers()))
        elif event.button() == Qt.RightButton:
            if self.mFaceVertices:
                face = self.mFaceVertices[:]
                if len(face) < 3: self.warning('至少需要三个已有顶点')
                elif self.editor().faceCanBeAdded(face): self.checkError(self.editor().addFace(face))
                elif self.editor().faceCanBeAdded(list(reversed(face))): self.checkError(self.editor().addFace(list(reversed(face))))
                else: self.warning('不能构面：检查顶点顺序、凸性、包含关系与相邻拓扑')
                self.onEdit()
            else:
                menu = QMenu(self.mApp)
                self.populateSelectedEdgeActions(menu)
                for key in ('mActionRemoveVerticesFillingHole', 'mActionRemoveVerticesWithoutFillingHole', 'mActionDelaunayTriangulation', 'mActionRemoveFaces', 'mActionSplitFaces', 'mActionFacesRefinement'):
                    menu.addAction(self.mActions[key])
                menu.exec_(self.canvas().mapToGlobal(event.pos()))
                menu.deleteLater()

    def selectedEdge(self):
        if not self.editor() or len(self.mSelectedVertices) != 2: return None
        ids = sorted(self.mSelectedVertices.intersection(self.vertices()))
        return ids if len(ids) == 2 else None

    def updateSelectedEdge(self):
        self.mEdgeBand.hide()
        edge = self.selectedEdge()
        if edge is None or self.canvas().mapTool() is not self or self.mStartMovingPoint is not None: return
        if not (self.editor().edgeCanBeFlipped(*edge) or self.editor().canBeMerged(*edge)): return
        vertices = self.vertices()
        points = [self.toMapCoordinates(self.layer(), QgsPointXY(vertices[index])) for index in edge]
        self.mEdgeBand.setToGeometry(QgsGeometry.fromPolylineXY(points), None)
        self.mEdgeBand.show()

    def populateSelectedEdgeActions(self, menu):
        edge = self.selectedEdge()
        if edge is None: return
        # In C++ these operations are exposed by on-canvas markers. The bound
        # editor can validate the selected endpoint pair without reading faces.
        flip = menu.addAction('翻转所选公共边', self.flipSelectedEdge)
        flip.setEnabled(self.editor().edgeCanBeFlipped(*edge))
        merge = menu.addAction('合并公共边两侧的面', self.mergeSelectedFaces)
        merge.setEnabled(self.editor().canBeMerged(*edge))
        menu.addSeparator()

    def flipSelectedEdge(self):
        edge = self.selectedEdge()
        if edge is None or not self.editor().edgeCanBeFlipped(*edge): return False
        self.editor().flipEdge(*edge)
        self.onEdit()
        return True

    def mergeSelectedFaces(self):
        edge = self.selectedEdge()
        if edge is None or not self.editor().canBeMerged(*edge): return False
        self.editor().merge(*edge)
        self.onEdit()
        return True

    def updateNewFacePreview(self, mapPoint=None):
        self.mNewFaceBand.hide()
        if not self.editor() or not self.mFaceVertices: return False
        ids = self.mFaceVertices[:]
        points = self.vertices()
        if mapPoint is not None:
            index = self.nearestVertex(mapPoint)
            if index is not None and index not in ids: ids.append(index)
        valid = len(ids) >= 3 and (self.editor().faceCanBeAdded(ids) or self.editor().faceCanBeAdded(list(reversed(ids))))
        polygon = [self.toMapCoordinates(self.layer(), QgsPointXY(points[index])) for index in ids if index in points]
        if mapPoint is not None and self.nearestVertex(mapPoint) is None:
            polygon.append(mapPoint)
            valid = False
        if len(polygon) >= 3:
            self.mNewFaceBand.setToGeometry(QgsGeometry.fromPolygonXY([polygon + [polygon[0]]]), None)
            self.mNewFaceBand.setFillColor(QColor(0, 210, 0, 65) if valid else QColor(230, 0, 0, 65))
            self.mNewFaceBand.setStrokeColor(QColor('green' if valid else 'red'))
            self.mNewFaceBand.show()
        return bool(valid)

    def applyZValueOnSelectedVertices(self):
        if not self.editor() or self.mZValueWidget is None or self.mStartMovingPoint is not None: return False
        ids = sorted(self.mSelectedVertices.intersection(self.vertices()))
        if not ids: return False
        self.mZValueWidget.interpretText()
        value = self.mZValueWidget.value()
        if not math.isfinite(value): return False
        if all(self.vertices()[index].z() == value for index in ids): return False
        self.editor().changeZValues(ids, [value] * len(ids))
        self.onEdit()
        return True

    def startMovingSelection(self, mapPoint):
        if not self.editor() or not self.mSelectedVertices: return False
        self.mMovingLayer = self.layer()
        self.mMovingVertices = sorted(self.mSelectedVertices.intersection(self.vertices()))
        if not self.mMovingVertices: return False
        self.mStartMovingPoint = QgsPointXY(mapPoint)
        self.mEdgeBand.hide()
        if self.mZValueWidget is not None: self.mZValueWidget.setEnabled(False)
        self.cadDockWidget().setPoints([self.mStartMovingPoint, self.mStartMovingPoint])
        self.moveSelection(mapPoint)
        return True

    def movingSelectionTransform(self, destination):
        if self.mStartMovingPoint is None or self.layer() is not self.mMovingLayer or not self.editor(): return None
        try:
            start = self.toLayerCoordinates(self.mMovingLayer, self.mStartMovingPoint)
            end = self.toLayerCoordinates(self.mMovingLayer, destination)
        except QgsCsException: return None
        dx, dy = end.x() - start.x(), end.y() - start.y()
        if not math.isfinite(dx) or not math.isfinite(dy): return None
        transform = QgsMeshTransformVerticesByExpression()
        transform.setInputVertices(self.mMovingVertices)
        transform.setExpressions(f'$vertex_x + ({dx!r})', f'$vertex_y + ({dy!r})', '')
        # calculate validates face orientation, overlaps and neighboring elements
        # against the current edit mesh, including unsaved edits.
        return transform if transform.calculate(self.mMovingLayer) else None

    def moveSelection(self, destination):
        transform = self.movingSelectionTransform(destination)
        points = []
        if self.layer() is not self.mMovingLayer:
            self.cancelMovingSelection()
            return False
        try:
            start = self.toLayerCoordinates(self.mMovingLayer, self.mStartMovingPoint)
            end = self.toLayerCoordinates(self.mMovingLayer, destination)
            for index in self.mMovingVertices:
                vertex = self.vertices().get(index)
                if vertex is not None:
                    shifted = QgsPointXY(vertex.x() + end.x() - start.x(), vertex.y() + end.y() - start.y())
                    points.append(self.toMapCoordinates(self.mMovingLayer, shifted))
        except QgsCsException:
            self.mMovingVerticesRubberBand.hide()
            return False
        self.mMovingVerticesRubberBand.setColor(QColor('limegreen' if transform is not None else 'red'))
        self.mMovingVerticesRubberBand.setToGeometry(QgsGeometry.fromMultiPointXY(points), None)
        self.mMovingVerticesRubberBand.show()
        return transform is not None

    def applyMovingSelection(self, destination):
        transform = self.movingSelectionTransform(destination)
        if transform is None:
            self.warning('无法移动：位置会破坏网孔拓扑，或目标图层/坐标转换已不可用。可调整位置或按 Esc 取消。')
            return False
        self.cancelMovingSelection()
        self.editor().advancedEdit(transform)
        self.onEdit()
        return True

    def cancelMovingSelection(self):
        wasMoving = self.mStartMovingPoint is not None
        self.mStartMovingPoint = None
        self.mMovingLayer = None
        self.mMovingVertices = []
        if not sip.isdeleted(self.mMovingVerticesRubberBand):
            self.mMovingVerticesRubberBand.reset(Qgis.GeometryType.Point)
            self.mMovingVerticesRubberBand.hide()
        if self.mZValueWidget is not None: self.mZValueWidget.setEnabled(True)
        if wasMoving and self.canvas().mapTool() is self: self.cadDockWidget().clearPoints()

    @staticmethod
    def behavior(modifiers):
        if modifiers & Qt.ControlModifier: return Qgis.SelectBehavior.RemoveFromSelection
        if modifiers & Qt.ShiftModifier: return Qgis.SelectBehavior.AddToSelection
        return Qgis.SelectBehavior.SetSelection

    def currentZValue(self):
        if self.mZValueWidget is not None:
            value = self.mZValueWidget.value()
        elif self.cadDockWidget().cadEnabled():
            value = self.cadDockWidget().constraintZ().value()
        else:
            value = QgsSettings().value('qgis/digitizing/default_z_value', 0., type=float)
        return value if math.isfinite(value) else QgsSettings().value('qgis/digitizing/default_z_value', 0., type=float)

    def updateForcingLinePreview(self, lastPoint=None):
        points = [QgsPointXY(point) for point in self.mForcingPoints]
        if points and lastPoint is not None: points.append(lastPoint)
        self.mRubberBand.reset(Qgis.GeometryType.Line)
        if len(points) > 1:
            self.mRubberBand.setToGeometry(QgsGeometry.fromPolylineXY(points), None)
            self.mRubberBand.show()

    def forceByLineReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            point, z = event.mapPoint(), self.currentZValue()
            vertex = self.nearestVertex(point)
            if vertex is not None:
                native = self.vertices()[vertex]
                point = self.toMapCoordinates(self.layer(), QgsPointXY(native))
                z = native.z()
            elif event.mapPointMatch().isValid():
                matched = event.mapPointMatch().interpolatedPoint(self.canvas().mapSettings().destinationCrs())
                if math.isfinite(matched.z()): z = matched.z()
            self.mForcingPoints.append(QgsPoint(point.x(), point.y(), z))
            self.updateForcingLinePreview()
        elif event.button() == Qt.RightButton:
            if not self.mForcingPoints:
                self.forceByLineBySelectedFeature(event)
            elif len(self.mForcingPoints) >= 2:
                self.forceByLine(QgsGeometry(QgsLineString(self.mForcingPoints)))
                self.mForcingPoints.clear()
                self.updateForcingLinePreview()
            else: self.warning('请至少确定两个约束点；Esc 取消，退格删除末点')

    def forceByLineBySelectedFeature(self, event):
        results = QgsIdentifyMenu.findFeaturesOnCanvas(event, self.canvas(), [Qgis.GeometryType.Line, Qgis.GeometryType.Polygon])
        if not results:
            self.warning('此处没有可用的线或面要素')
            return
        menu = QgsIdentifyMenu(self.canvas())
        menu.setExecWithSingleResult(True)
        menu.setAllowMultipleReturn(False)
        try: selected = menu.exec(results, self.canvas().mapToGlobal(event.pos()))
        finally: menu.deleteLater()
        if not selected or not selected[0].mFeature.hasGeometry(): return
        result = selected[0]
        geometry = QgsGeometry(result.mFeature.geometry())
        try: geometry.transform(self.canvas().mapSettings().layerTransform(result.mLayer))
        except QgsCsException as error:
            self.warning('约束几何坐标转换失败：' + str(error))
            return
        self.forceByLine(geometry)

    def forceByLine(self, geometry):
        editor = self.editor()
        if editor is None or geometry.isEmpty(): return False
        if geometry.type() not in (Qgis.GeometryType.Line, Qgis.GeometryType.Polygon):
            self.warning('约束需要线或面边界几何')
            return False
        settings = self.mWidgetActionForceByLine
        edit = QgsMeshEditForceByPolylines()
        edit.setDefaultZValue(self.currentZValue())
        edit.addLineFromGeometry(geometry)
        edit.setAddVertexOnIntersection(settings.newVertexOnIntersectingEdge())
        edit.setInterpolateZValueOnMesh(settings.interpolationMode() == settings.Mesh)
        context = QgsRenderContext.fromMapSettings(self.canvas().mapSettings())
        tolerance = context.convertToMapUnits(settings.toleranceValue(), settings.toleranceUnit())
        edit.setTolerance(tolerance)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try: editor.advancedEdit(edit)
        finally: QApplication.restoreOverrideCursor()
        if edit.message(): self.warning(edit.message())
        self.onEdit()
        return True

    def setSelectedVertices(self, ids, behavior=Qgis.SelectBehavior.SetSelection):
        self.applySelection(self.mSelectedVertices, ids, behavior)
        self.updateSelection()

    @staticmethod
    def applySelection(selected, ids, behavior):
        if behavior == Qgis.SelectBehavior.SetSelection: selected.clear(); selected.update(ids)
        elif behavior == Qgis.SelectBehavior.AddToSelection: selected.update(ids)
        elif behavior == Qgis.SelectBehavior.RemoveFromSelection: selected.difference_update(ids)
        else: selected.intersection_update(ids)

    def selectByExpression(self, text, behavior, elementType):
        if not self.editor(): return False
        context = QgsExpressionContext([QgsExpressionContextUtils.meshExpressionScope(elementType)])
        expression = QgsExpression(text)
        if not expression.prepare(context):
            self.warning(expression.parserErrorString() or expression.evalErrorString() or '表达式无法解析')
            return False
        if elementType == QgsMesh.Vertex:
            ids = set(self.layer().selectVerticesByExpression(expression)) & set(self.vertices())
            self.applySelection(self.mSelectedVertices, ids, behavior)
        else:
            ids = set(self.layer().selectFacesByExpression(expression)) & set(self.layer().selectFacesByExpression(QgsExpression('$face_area > 0')))
            self.applySelection(self.mSelectedFaces, ids, behavior)
        self.updateSelection()
        return True

    def checkError(self, error):
        if error.errorType != Qgis.MeshEditingErrorType.NoError:
            self.warning(f'操作未完成：{error.errorType}，元素 {error.elementIndex}')
            return False
        return True

    def removeSelectedVerticesFromMesh(self, fillHole):
        if not self.editor() or not self.mSelectedVertices: return
        ids = sorted(self.mSelectedVertices)
        if fillHole:
            remaining = self.editor().removeVerticesFillHoles(ids)
            if remaining: self.warning('以下顶点无法在保持拓扑时移除：' + ', '.join(map(str, remaining)))
        else: self.checkError(self.editor().removeVerticesWithoutFillHoles(ids))
        self.onEdit()

    def removeFacesFromMesh(self):
        if self.editor() and self.mSelectedFaces:
            self.checkError(self.editor().removeFaces(sorted(self.mSelectedFaces)))
            self.onEdit()

    def splitSelectedFaces(self):
        if self.editor() and self.mSelectedFaces:
            count = self.editor().splitFaces(sorted(self.mSelectedFaces))
            if not count: self.warning('所选面不可分割；原生分割要求可分割的四边形')
            self.onEdit()

    def refineSelectedFaces(self):
        if self.editor() and self.mSelectedFaces:
            edit = QgsMeshEditRefineFaces()
            edit.setInputFaces(sorted(self.mSelectedFaces))
            self.editor().advancedEdit(edit)
            if edit.message(): self.warning(edit.message())
            self.onEdit()

    def delaunayTriangulation(self):
        editor = self.editor()
        if editor is None: return False
        ids = sorted(self.mSelectedVertices.intersection(self.vertices()))
        if len(ids) < 3:
            self.warning('请至少选中三个有效顶点。')
            return False
        vertices = self.vertices()
        eligible = [index for index in ids if editor.isVertexFree(index) or editor.isVertexOnBoundary(index)]
        hull = QgsGeometry.fromMultiPointXY([QgsPointXY(vertices[index]) for index in eligible]).convexHull()
        if len(eligible) < 3 or hull.isEmpty() or hull.area() <= 0:
            self.warning('请至少选择三个不共线的边界或自由顶点。')
            return False
        from qgis.analysis import QgsMeshEditingDelaunayTriangulation
        edit = QgsMeshEditingDelaunayTriangulation()
        edit.setInputVertices(ids)
        before = editor.validFacesCount()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try: editor.advancedEdit(edit)
        finally: QApplication.restoreOverrideCursor()
        if edit.message(): self.mApp.mMessageBar.pushInfo('Delaunay 三角剖分', edit.message())
        changed = editor.validFacesCount() > before
        if not changed and not edit.message(): self.warning('没有生成新面：检查顶点是否共线、已有面是否覆盖选区或拓扑是否允许构面。')
        self.onEdit()
        return changed

    def reindexMesh(self):
        if not self.editor(): return
        if QMessageBox.question(self.mApp, '重建网孔索引', '重新编号顶点和面会清空撤销历史。继续？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return
        if not self.layer().reindex(self.transform(self.layer()), True): self.warning('重新编号失败')
        self.mSelectedVertices.clear()
        self.mSelectedFaces.clear()
        self.onEdit()

    def showSelectByExpressionDialog(self):
        if not self.editor(): return
        self.activateWithState('Digitizing')
        from .qgsmeshselectbyexpressiondialog import QgsMeshSelectByExpressionDialog
        dialog = QgsMeshSelectByExpressionDialog(self, self.mApp)
        self.mDialogs.append(dialog)
        dialog.show()

    def triggerTransformCoordinatesDockWidget(self):
        if not self.editor(): return
        from .qgsmeshtransformcoordinatesdockwidget import QgsMeshTransformCoordinatesDockWidget
        if self.mTransformDockWidget is None:
            self.mTransformDockWidget = QgsMeshTransformCoordinatesDockWidget(self, self.mApp)
            self.mApp.addDockWidget(Qt.RightDockWidgetArea, self.mTransformDockWidget)
        self.mTransformDockWidget.updateSelection()
        self.mTransformDockWidget.show()
        self.mTransformDockWidget.raise_()

    def zoomToSelected(self):
        vertices = self.vertices()
        points = [self.toMapCoordinates(self.layer(), QgsPointXY(vertices[i])) for i in self.mSelectedVertices if i in vertices]
        if points:
            extent = QgsGeometry.fromMultiPointXY(points).boundingBox()
            if extent.isEmpty(): extent.grow(self.canvas().mapUnitsPerPixel()*30)
            extent.scale(1.2)
            self.canvas().setExtent(extent)
            self.canvas().refresh()
        elif self.mSelectedFaces: self.warning('当前仅能缩放已选顶点；面的直接几何访问未绑定')

    def keyPressEvent(self, event):
        if event.isAutoRepeat() and event.key() in (Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter):
            event.ignore()
            return
        if self.mStartMovingPoint is not None:
            if event.key() == Qt.Key_Escape: self.cancelMovingSelection()
            # Do not delete selected vertices while a movement is pending.
            if event.key() in (Qt.Key_Escape, Qt.Key_Delete, Qt.Key_Backspace):
                event.ignore()
                return
        if self.mCurrentState == 'ForceByLines' and event.key() in (Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Delete):
            if event.key() == Qt.Key_Escape: self.mForcingPoints.clear()
            elif self.mForcingPoints: self.mForcingPoints.pop()
            self.updateForcingLinePreview()
            event.ignore()
            return
        if event.key() == Qt.Key_Escape:
            self.mFaceVertices.clear()
            self.mNewFaceBand.hide()
            self.mSelectionPoints.clear()
            self.mSelectedVertices.clear()
            self.mSelectedFaces.clear()
            self.mRubberBand.reset(Qgis.GeometryType.Line)
            self.updateSelection()
            event.ignore()
        elif event.key() == Qt.Key_Backspace:
            points = self.mSelectionPoints if self.mCurrentState == 'Selecting' else self.mFaceVertices
            if points: points.pop()
            self.mRubberBand.reset(Qgis.GeometryType.Line)
            if self.mCurrentState == 'Digitizing':
                self.setSelectedVertices(self.mFaceVertices)
                self.updateNewFacePreview()
            event.ignore()
        elif event.key() == Qt.Key_Delete:
            if event.modifiers() & Qt.ControlModifier:
                self.removeSelectedVerticesFromMesh(not bool(event.modifiers() & Qt.ShiftModifier))
            elif event.modifiers() & Qt.ShiftModifier: self.removeFacesFromMesh()
            event.ignore()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.mCurrentState == 'Digitizing':
            self.applyZValueOnSelectedVertices()
            event.ignore()
        else: super().keyPressEvent(event)

    def shutdown(self):
        self.mShutdown = True
        for dialog in self.mDialogs:
            if not sip.isdeleted(dialog): dialog.close()
        if self.mTransformDockWidget: self.mTransformDockWidget.dispose()
        self.cancelMovingSelection()
        for rubber in (self.mRubberBand, self.mSelectionRubberBand, self.mMovingVerticesRubberBand, self.mNewFaceBand, self.mEdgeBand):
            self.canvas().scene().removeItem(rubber)
            sip.delete(rubber)
