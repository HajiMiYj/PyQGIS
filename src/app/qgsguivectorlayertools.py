"""Application editing policy; counterpart of qgsguivectorlayertools.cpp."""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsVectorLayerTools, QgsVectorLayerUtils, QgsGeometry, QgsSettings
from qgis.gui import QgsAttributeDialog, QgsAttributeEditorContext
from qgis.PyQt.QtWidgets import QMessageBox


class QgsGuiVectorLayerTools(QgsVectorLayerTools):
    def __init__(self, app):
        super().__init__()
        self.mApp = app

    def startEditing(self, layer):
        return bool(layer and (layer.isEditable() or layer.startEditing()))

    def saveEdits(self, layer):
        if not layer or not layer.isEditable():
            return True
        if not layer.commitChanges(False):
            self.mApp.mMessageBar.pushCritical('保存编辑失败', '\n'.join(layer.commitErrors()))
            return False
        return True

    def stopEditing(self, layer, allowCancel=True):
        if not layer or not layer.isEditable():
            return True
        if layer.isModified():
            buttons = QMessageBox.Save | QMessageBox.Discard
            if allowCancel:
                buttons |= QMessageBox.Cancel
            answer = QMessageBox.question(self.mApp, QCoreApplication.translate('MainWindow', 'Save Layer Edits'), layer.name(), buttons, QMessageBox.Save)
            if answer == QMessageBox.Cancel:
                return False
            if answer == QMessageBox.Save:
                if not layer.commitChanges():
                    self.mApp.mMessageBar.pushCritical('保存编辑失败', '\n'.join(layer.commitErrors()))
                    return False
                return True
        return layer.rollBack()

    def addFeature(self, layer, defaultValues={}, defaultGeometry=QgsGeometry(), parentWidget=None, showModal=True, hideParent=False, expressionContext=None):
        if not layer or not layer.isEditable():
            return False, None
        feature = QgsVectorLayerUtils.createFeature(layer, defaultGeometry, defaultValues,
            expressionContext if expressionContext is not None else layer.createExpressionContext())
        disableAttributeDialog = QgsSettings().value(
            'qgis/digitizing/disable_enter_attribute_values_dialog', False, type=bool)
        if disableAttributeDialog:
            for index in range(len(layer.fields())):
                if not QgsVectorLayerUtils.validateAttribute(layer, feature, index)[0]:
                    self.mApp.mMessageBar.pushWarning('属性约束', layer.fields().at(index).name())
                    return False, feature
            layer.beginEditCommand('新增要素')
            success = layer.addFeature(feature)
            if success: layer.endEditCommand()
            else: layer.destroyEditCommand()
            return success, feature
        context = QgsAttributeEditorContext()
        context.setVectorLayerTools(self)
        dialog = QgsAttributeDialog(layer, feature, False, parentWidget or self.mApp, True, context)
        dialog.setMode(QgsAttributeEditorContext.AddFeatureMode)
        if not dialog.exec_():
            return False, feature
        # QgsAttributeForm AddFeatureMode commits the new feature to the edit buffer.
        return True, dialog.feature()


