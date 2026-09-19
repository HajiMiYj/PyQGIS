"""Application project settings controller corresponding to qgsprojectproperties.cpp."""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QLineEdit, QDialogButtonBox, QTableWidget, QTableWidgetItem
from qgis.gui import QgsProjectionSelectionTreeWidget
from qgis.core import QgsExpressionContextUtils


class QgsProjectProperties(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.mApp = app
        self.setObjectName('QgsProjectProperties')
        self.setWindowTitle(QCoreApplication.translate('QgsProjectPropertiesBase', 'Project Properties'))
        self.resize(800, 620)
        layout = QVBoxLayout(self)
        self.mOptionsStackedWidget = QTabWidget()
        layout.addWidget(self.mOptionsStackedWidget)
        general = QWidget()
        form = QFormLayout(general)
        self.titleEdit = QLineEdit(app.mProject.title())
        self.mProjectHomeLineEdit = QLineEdit(app.mProject.presetHomePath())
        self.mEllipsoid = QLineEdit(app.mProject.ellipsoid())
        form.addRow(QCoreApplication.translate('QgsProjectPropertiesBase', 'Project title'), self.titleEdit)
        form.addRow(QCoreApplication.translate('QgsBrowserModel', 'Project Home'), self.mProjectHomeLineEdit)
        form.addRow('椭球体（例如 WGS84、NONE）', self.mEllipsoid)
        self.mOptionsStackedWidget.addTab(general, QCoreApplication.translate('Map3DConfigWidget', 'General'))
        self.mProjectionSelector = QgsProjectionSelectionTreeWidget()
        self.mProjectionSelector.setCrs(app.mProject.crs())
        self.mOptionsStackedWidget.addTab(self.mProjectionSelector, '坐标参考系')
        variables = app.mProject.customVariables()
        self.mVariableTable = QTableWidget(len(variables) + 5, 2)
        self.mVariableTable.setHorizontalHeaderLabels(['变量名', '值（文本）'])
        self._variables = dict(variables)
        for row, (key, value) in enumerate(variables.items()):
            self.mVariableTable.setItem(row, 0, QTableWidgetItem(key))
            self.mVariableTable.setItem(row, 1, QTableWidgetItem(str(value)))
        self.mOptionsStackedWidget.addTab(self.mVariableTable, '工程变量')
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self.apply)
        buttons.rejected.connect(self.reject)

    def apply(self):
        project = self.mApp.mProject
        project.setTitle(self.titleEdit.text())
        project.setPresetHomePath(self.mProjectHomeLineEdit.text())
        project.setCrs(self.mProjectionSelector.crs())
        project.setEllipsoid(self.mEllipsoid.text())
        variables = {}
        for row in range(self.mVariableTable.rowCount()):
            keyItem, valueItem = self.mVariableTable.item(row, 0), self.mVariableTable.item(row, 1)
            if keyItem and keyItem.text().strip():
                key = keyItem.text().strip()
                value = valueItem.text() if valueItem else ''
                # Preserve existing typed values if their text was not edited.
                variables[key] = self._variables[key] if key in self._variables and str(self._variables[key]) == value else value
        QgsExpressionContextUtils.setProjectVariables(project, variables)
        project.setDirty(True)
        self.accept()

