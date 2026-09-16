from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTreeView, QAbstractItemView, QMenu
from .qgsgcplistmodel import QgsGCPListModel


class QgsGCPListWidget(QTreeView):
    def __init__(self, window):
        super().__init__(window)
        self.mWindow = window
        self.mModel = QgsGCPListModel(window)
        self.setModel(self.mModel)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        self.doubleClicked.connect(lambda index: window.centerPoint(index.row()) if index.column() == 1 else None)

    def showContextMenu(self, position):
        rows = sorted({index.row() for index in self.selectionModel().selectedRows()})
        if not rows or self.mWindow.mBusy: return
        menu = QMenu(self)
        menu.addAction('缩放至控制点', lambda: self.mWindow.centerPoint(rows[0]))
        menu.addAction('删除所选控制点', lambda: self.mWindow.deletePoints(rows))
        menu.exec_(self.viewport().mapToGlobal(position))
