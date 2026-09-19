"""QGIS report tree, original section forms and native report persistence."""
from qgis.PyQt import sip, uic
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import (QMainWindow, QVBoxLayout, QMenu, QFileDialog,
                                QMessageBox, QAbstractItemView)
from qgis.core import (QgsLayout, QgsReportSectionLayout, QgsReportSectionFieldGroup,
                       QgsLayoutExporter, QgsApplication)
from .qgsreportsectionmodel import QgsReportSectionModel
from .qgsreportsectionwidget import QgsReportSectionWidget, UI_ROOT
from .qgsreportlayoutsectionwidget import QgsReportLayoutSectionWidget
from .qgsreportfieldgroupsectionwidget import QgsReportSectionFieldGroupWidget


class QgsReportOrganizerWidget(QMainWindow):
    def __init__(self, app, report):
        super().__init__(app, Qt.Window)
        self.mApp, self.mReport = app, report
        self.mConfigWidget = None
        self.setObjectName('QgsReportOrganizerWidget')
        self.setWindowTitle(report.name() + ' — 报表')
        self.resize(560, 720)
        form = uic.loadUi(str(UI_ROOT / 'qgsreportorganizerwidgetbase.ui'))
        self.setCentralWidget(form)
        for name in ('mViewSections', 'mButtonAddSection', 'mButtonRemoveSection', 'mSettingsFrame'):
            setattr(self, name, getattr(form, name))
        self.mSectionModel = QgsReportSectionModel(report, self)
        self.mViewSections.setModel(self.mSectionModel)
        self.mViewSections.header().hide()
        self.mViewSections.setSelectionMode(QAbstractItemView.SingleSelection)
        # Native 3.34 model does not implement drops. Explicit move controls
        # use an ownership-safe deep copy of the section and its descendants.
        self.mViewSections.setDragDropMode(QAbstractItemView.NoDragDrop)
        box = QVBoxLayout(self.mSettingsFrame)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        menu = QMenu(self.mButtonAddSection)
        menu.addAction('静态布局章节', self.addLayoutSection)
        menu.addAction('字段分组章节', self.addFieldGroupSection)
        self.mButtonAddSection.setMenu(menu)
        self.mButtonAddSection.setIcon(QgsApplication.getThemeIcon('/symbologyAdd.svg'))
        self.mButtonRemoveSection.setIcon(QgsApplication.getThemeIcon('/symbologyRemove.svg'))
        self.mButtonRemoveSection.clicked.connect(lambda: self.removeSection(confirm=True))
        self.mViewSections.selectionModel().currentChanged.connect(self.selectionChanged)
        self.mViewSections.doubleClicked.connect(lambda *_: self.editSection())
        self.mViewSections.customContextMenuRequested.connect(self.showSectionMenu)
        toolbar = self.addToolBar('报表')
        toolbar.setObjectName('ReportToolbar')
        self.mActionEditSection = toolbar.addAction('编辑正文', self.editSection)
        self.mActionMoveUp = toolbar.addAction(QCoreApplication.translate('QgsProcessingAggregateMapPanelBase', 'up'), lambda: self.moveSection(-1))
        self.mActionMoveDown = toolbar.addAction(QCoreApplication.translate('QgsProcessingAggregateMapPanelBase', 'down'), lambda: self.moveSection(1))
        self.mActionIndent = toolbar.addAction('降级', self.indentSection)
        self.mActionOutdent = toolbar.addAction(QCoreApplication.translate('QgsPluginDependenciesDialog', 'Upgrade'), self.outdentSection)
        self.mActionDuplicate = toolbar.addAction('复制章节', self.duplicateSection)
        toolbar.addSeparator()
        toolbar.addAction(QCoreApplication.translate('MainWindow', 'Save Project'), app.fileSave)
        toolbar.addAction('导出 PDF', lambda: self.exportPdf())
        report.destroyed.connect(self.reportDestroyed)
        self.selectSection(report)

    def currentSection(self):
        if self.mReport is None: return None
        return self.mSectionModel.sectionForIndex(self.mViewSections.currentIndex()) or self.mReport

    def selectSection(self, section):
        index = self.mSectionModel.indexForSection(section)
        self.mViewSections.setCurrentIndex(index)
        self.mViewSections.expandAll()
        self.mViewSections.scrollTo(index)

    def clearConfigWidget(self):
        if self.mConfigWidget is not None:
            self.mSettingsFrame.layout().removeWidget(self.mConfigWidget)
            sip.delete(self.mConfigWidget)
            self.mConfigWidget = None

    def selectionChanged(self, *_):
        self.clearConfigWidget()
        section = self.currentSection()
        self.updateActions()
        if section is None: return
        widgetClass = (QgsReportSectionFieldGroupWidget if isinstance(section, QgsReportSectionFieldGroup)
                       else QgsReportLayoutSectionWidget if isinstance(section, QgsReportSectionLayout)
                       else QgsReportSectionWidget)
        self.mConfigWidget = widgetClass(self, self.mApp, section)
        self.mSettingsFrame.layout().addWidget(self.mConfigWidget)

    def updateActions(self):
        section = self.currentSection()
        child = section is not None and section is not self.mReport
        parent = section.parentSection() if child else None
        row = section.row() if child else -1
        self.mButtonRemoveSection.setEnabled(child)
        self.mActionEditSection.setEnabled(child and section.bodyEnabled())
        self.mActionMoveUp.setEnabled(child and row > 0)
        self.mActionMoveDown.setEnabled(child and row + 1 < parent.childCount())
        self.mActionIndent.setEnabled(child and row > 0)
        self.mActionOutdent.setEnabled(child and parent is not self.mReport)
        self.mActionDuplicate.setEnabled(child)

    def setEditedSection(self, section): self.mSectionModel.setEditedSection(section)

    def sectionChanged(self, section):
        self.mApp.mProject.setDirty(True)
        self.mSectionModel.sectionChanged(section)
        self.updateActions()

    def addLayoutSection(self):
        section = QgsReportSectionLayout()
        layout = QgsLayout(self.mApp.mProject)
        layout.initializeDefaults()
        section.setBody(layout)
        section.setBodyEnabled(True)
        self.mSectionModel.addSection(self.mViewSections.currentIndex(), section)
        self.selectSection(section)
        self.sectionChanged(section)
        return section

    def addFieldGroupSection(self):
        section = QgsReportSectionFieldGroup()
        self.mSectionModel.addSection(self.mViewSections.currentIndex(), section)
        self.selectSection(section)
        self.sectionChanged(section)
        return section

    def editSectionLayout(self, section, part):
        layout = getattr(section, part.lower())()
        if layout is None:
            layout = QgsLayout(self.mApp.mProject)
            layout.initializeDefaults()
            getattr(section, 'set' + part)(layout)
            self.sectionChanged(section)
        if isinstance(section, QgsReportSectionFieldGroup): layout.reportContext().setLayer(section.layer())
        self.setEditedSection(section)
        title = {'Header': '页眉', 'Footer': '页脚', 'Body': '正文'}[part]
        for window in self.mApp.mLayoutDesigners:
            if not sip.isdeleted(window) and getattr(window, 'mLayout', None) is layout:
                window.show()
                window.raise_()
                window.activateWindow()
                return window
        window = self.mApp.openLayoutDesigner(layout)
        window.setWindowTitle(title + '：' + section.description() + ' — ' + self.mReport.name())
        return window

    def editSection(self):
        section = self.currentSection()
        if section is not None and section is not self.mReport and section.bodyEnabled():
            return self.editSectionLayout(section, 'Body')

    def editHeaderFooter(self, header):
        section = self.currentSection()
        if section is None: return
        getattr(section, 'setHeaderEnabled' if header else 'setFooterEnabled')(True)
        self.sectionChanged(section)
        self.selectionChanged()
        return self.editSectionLayout(section, 'Header' if header else 'Footer')

    def sectionLayouts(self, section):
        layouts = [section.header(), section.footer()]
        if isinstance(section, (QgsReportSectionLayout, QgsReportSectionFieldGroup)): layouts.append(section.body())
        for child in section.childSections(): layouts.extend(self.sectionLayouts(child))
        return [layout for layout in layouts if layout is not None]

    def cleanupSection(self, section):
        # Designers hold native layouts. Release them before removing a subtree.
        layouts = self.sectionLayouts(section)
        for window in list(self.mApp.mLayoutDesigners):
            if sip.isdeleted(window):
                self.mApp.mLayoutDesigners.remove(window)
            elif getattr(window, 'mLayout', None) in layouts:
                window.close()
                self.mApp.mLayoutDesigners.remove(window)
                sip.delete(window)
        self.clearConfigWidget()

    def removeSection(self, confirm=False):
        section = self.currentSection()
        if section is None or section is self.mReport: return False
        if confirm and QMessageBox.question(self, '删除章节', '删除选中的章节及其所有子章节？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes: return False
        parent, row = section.parentSection(), section.row()
        self.cleanupSection(section)
        self.mSectionModel.removeRows(row, 1, self.mSectionModel.indexForSection(parent))
        self.selectSection(parent)
        self.sectionChanged(parent)
        return True

    def moveTo(self, section, parent, row):
        self.cleanupSection(section)
        replacement = self.mSectionModel.moveSection(section, parent, row)
        if replacement is not None:
            self.selectSection(replacement)
            self.sectionChanged(replacement)
        else: self.selectionChanged()
        return replacement

    def moveSection(self, offset):
        section = self.currentSection()
        if section is None or section is self.mReport: return
        parent, row = section.parentSection(), section.row()
        target = row + offset
        if target < 0 or target >= parent.childCount(): return
        return self.moveTo(section, parent, target if offset < 0 else target + 1)

    def indentSection(self):
        section = self.currentSection()
        if section is None or section is self.mReport or section.row() == 0: return
        parent = section.parentSection().childSection(section.row() - 1)
        return self.moveTo(section, parent, parent.childCount())

    def outdentSection(self):
        section = self.currentSection()
        if section is None or section is self.mReport: return
        parent = section.parentSection()
        if parent is self.mReport: return
        return self.moveTo(section, parent.parentSection(), parent.row() + 1)

    def duplicateSection(self):
        section = self.currentSection()
        if section is None or section is self.mReport: return
        clone = self.mSectionModel.cloneSection(section)
        self.mSectionModel.addSection(self.mSectionModel.indexForSection(section.parentSection()), clone)
        self.selectSection(clone)
        self.sectionChanged(clone)
        return clone

    def showSectionMenu(self, position):
        index = self.mViewSections.indexAt(position)
        if index.isValid(): self.mViewSections.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction('添加静态布局子章节', self.addLayoutSection)
        menu.addAction('添加字段分组子章节', self.addFieldGroupSection)
        menu.addSeparator()
        for action in (self.mActionEditSection, self.mActionMoveUp, self.mActionMoveDown,
                       self.mActionIndent, self.mActionOutdent, self.mActionDuplicate): menu.addAction(action)
        action = menu.addAction('删除章节', lambda: self.removeSection(confirm=True))
        action.setEnabled(self.currentSection() is not self.mReport)
        menu.exec_(self.mViewSections.viewport().mapToGlobal(position))
        menu.deleteLater()

    def exportPdf(self, path=None):
        if self.mReport is None: return
        def invalidGroup(section):
            if isinstance(section, QgsReportSectionFieldGroup):
                layer = section.layer()
                if layer is None or not layer.isValid(): return '字段分组缺少有效的矢量图层'
                if section.field() and layer.fields().lookupField(section.field()) < 0: return '字段分组所用的字段已不存在'
            for child in section.childSections():
                error = invalidGroup(child)
                if error: return error
            return ''
        error = invalidGroup(self.mReport)
        if error:
            self.mApp.mMessageBar.pushWarning('报表导出', error)
            return QgsLayoutExporter.IteratorError
        if not path: path, _ = QFileDialog.getSaveFileName(self, '导出报表', '', 'PDF (*.pdf)')
        if not path: return
        if not str(path).lower().endswith('.pdf'): path = str(path) + '.pdf'
        result, error = QgsLayoutExporter.exportToPdf(self.mReport, str(path), QgsLayoutExporter.PdfExportSettings())
        if result != QgsLayoutExporter.Success: self.mApp.mMessageBar.pushWarning('报表导出失败', error or str(result))
        return result

    def reportDestroyed(self, *_):
        self.clearConfigWidget()
        self.mReport = None
        self.mSectionModel.clearReport()
        self.setEnabled(False)
        self.close()
