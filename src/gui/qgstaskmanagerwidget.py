"""Unbound status-bar wrapper around native QgsTaskManagerWidget."""
from qgis.PyQt.QtWidgets import QToolButton, QVBoxLayout, QProgressBar, QSizePolicy
from qgis.PyQt.QtCore import QSize, QEvent
from qgis.core import Qgis
from qgis.gui import QgsFloatingWidget, QgsTaskManagerWidget


class QgsTaskManagerStatusBarWidget(QToolButton):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
        self.mProgressBar = QProgressBar(self)
        self.mProgressBar.setMaximumHeight(16)
        self.mProgressBar.setRange(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.mProgressBar)
        self.mFloatingWidget = QgsFloatingWidget(parent.window())
        self.mFloatingWidget.setAnchorWidget(self)
        self.mFloatingWidget.setAnchorPoint(QgsFloatingWidget.BottomMiddle)
        self.mFloatingWidget.setAnchorWidgetPoint(QgsFloatingWidget.TopMiddle)
        floatingLayout = QVBoxLayout(self.mFloatingWidget)
        self.mTaskManagerWidget = QgsTaskManagerWidget(manager, self.mFloatingWidget)
        floatingLayout.addWidget(self.mTaskManagerWidget)
        self.mFloatingWidget.resize(500, 220)
        self.mFloatingWidget.hide()
        self.clicked.connect(self.toggleDisplay)
        manager.taskAdded.connect(lambda *_: self.show())
        manager.allTasksFinished.connect(self.allFinished)
        manager.finalTaskProgressChanged.connect(self.overallProgressChanged)
        manager.countActiveTasksChanged.connect(self.countActiveTasksChanged)
        self.setVisible(manager.countActiveTasks() > 0)
    def sizeHint(self):
        return QSize(round(self.fontMetrics().horizontalAdvance('X')*20*Qgis.UI_SCALE_FACTOR), super().sizeHint().height())
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange and hasattr(self, 'mProgressBar'):
            self.mProgressBar.setFont(self.font())
    def toggleDisplay(self):
        self.mFloatingWidget.setVisible(not self.mFloatingWidget.isVisible())
        if self.mFloatingWidget.isVisible(): self.mFloatingWidget.raise_()
    def allFinished(self):
        self.mFloatingWidget.hide()
        self.hide()
        self.mProgressBar.setRange(0, 0)
    def overallProgressChanged(self, value):
        self.mProgressBar.setRange(0, 100 if value else 0)
        self.mProgressBar.setValue(round(value))
    def countActiveTasksChanged(self, count):
        self.setToolTip(f'{count} 个后台任务正在运行')
        if count > 1: self.mProgressBar.setRange(0, 0)
