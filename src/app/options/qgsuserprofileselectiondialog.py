"""Port of src/app/options/qgsuserprofileselectiondialog.cpp.

Upstream class lives in src/app, so it is absent from the PyQGIS bindings even
though everything it drives (QgsUserProfileManager, QgsNewNameDialog) is bound.
"""
from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, QSize, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QDialog, QListWidgetItem, QMessageBox
from qgis.core import QgsApplication

ROOT = Path(__file__).resolve().parents[3]


class QgsUserProfileSelectionDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'src/ui/qgsuserprofileselectiondialog.ui'), self)
        self.mManager = manager
        self.setWindowIcon(QIcon(QgsApplication.appIconPath()))

        # Select the user profile on double-click.
        self.mProfileListWidget.itemDoubleClicked.connect(self.accept)
        self.mAddProfileButton.clicked.connect(self.onAddProfile)

        iconSize = int(self.mManager.settings().value('/selector/iconSize', 24))
        self.mProfileListWidget.setIconSize(QSize(iconSize, iconSize))

        # Clear the placeholder entries shipped in the .ui form.
        self.mProfileListWidget.clear()
        for profile in self.mManager.allProfiles():
            item = QListWidgetItem(self.mManager.profileForName(profile).icon(), profile)
            self.mProfileListWidget.addItem(item)
            if profile == self.mManager.lastProfileName():
                self.mProfileListWidget.setCurrentItem(item)
                item.setSelected(True)

    def selectedProfileName(self):
        item = self.mProfileListWidget.currentItem()
        return item.text() if item is not None else ''

    def accept(self):
        item = self.mProfileListWidget.currentItem()
        if item is not None and item.isSelected():
            super().accept()

    def onAddProfile(self):
        from qgis.gui import QgsNewNameDialog
        dialog = QgsNewNameDialog('', '', [], self.mManager.allProfiles(), Qt.CaseInsensitive, self)
        dialog.setConflictingNameWarning(QCoreApplication.translate('QgsUserProfileSelectionDialog', 'A profile with this name already exists'))
        dialog.setOverwriteEnabled(False)
        dialog.setHintString(QCoreApplication.translate('QgsUserProfileSelectionDialog', 'New profile name'))
        dialog.setWindowTitle('新建配置名称')
        # Prevent slashes and backslashes in the profile folder name.
        dialog.setRegularExpression('[^/\\\\]+')
        if dialog.exec_() != QDialog.Accepted:
            return
        profileName = dialog.name()
        error = self.mManager.createUserProfile(profileName)
        if error.isEmpty():
            item = QListWidgetItem(QgsApplication.getThemeIcon('user.svg'), profileName)
            self.mProfileListWidget.addItem(item)
            self.mProfileListWidget.setCurrentItem(item)
            item.setSelected(True)
            self.accept()
            return
        QMessageBox.warning(self, QCoreApplication.translate('QgsUserProfileSelectionDialog', 'New Profile'), f"无法创建文件夹 '{profileName}'")
