"""Counterpart of options/qgsuserprofileoptions.cpp, using its original form.

The port already had the profile *selection* dialog; this is the User Profiles
options page: which profile is loaded at startup, the profile selector icon size
and the active profile's icon.
"""
from qgis.PyQt.QtCore import QCoreApplication
from pathlib import Path
import shutil
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.core import Qgis
from qgis.gui import QgsOptionsPageWidget

ROOT = Path(__file__).resolve().parents[2]
ICON_FILTER = '图像 (*.png *.jpg *.jpeg *.gif *.bmp *.svg)'


class QgsUserProfileOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None, app=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgsuserprofileoptionswidgetbase.ui'), self)
        self.setObjectName('mOptionsPageUserProfiles')
        if app is None:
            from ..qgisapp import QgisApp
            app = QgisApp.instance()
        self.mApp = app
        self.mManager = app.userProfileManager() if app is not None else None
        # Tests build the application without a profile folder, so the page has to
        # stay usable (and inert) instead of failing to construct.
        if self.mManager is None:
            for widget in (self.mProfilePolicyGroupBox, self.mProfileSelectorGroupBox):
                widget.setEnabled(False)
                widget.setToolTip('未启用配置档案目录（未指定 --profiles-path），此页不可用。')
            return

        self.mDefaultProfileComboBox.setEnabled(False)
        self.mDefaultProfile.toggled.connect(self.mDefaultProfileComboBox.setEnabled)
        self.mIconSizeLabel.setEnabled(False)
        self.mIconSize.setEnabled(False)
        self.mAskUser.toggled.connect(self.onAskUserChanged)

        self.mIconSize.setCurrentText(str(self.mManager.settings().value('/selector/iconSize', 24, type=int)))
        self.mIconSize.currentTextChanged.connect(self.onIconSizeChanged)
        self.mActiveProfileIconButton.clicked.connect(self.onChangeIconClicked)
        self.mResetIconButton.clicked.connect(self.onResetIconClicked)

        policy = self.mManager.userProfileSelectionPolicy()
        if policy == Qgis.UserProfileSelectionPolicy.LastProfile:
            self.mLastProfile.setChecked(True)
        elif policy == Qgis.UserProfileSelectionPolicy.AskUser:
            self.mAskUser.setChecked(True)
        elif policy == Qgis.UserProfileSelectionPolicy.DefaultProfile:
            self.mDefaultProfile.setChecked(True)
        self.mDefaultProfileComboBox.setEnabled(self.mDefaultProfile.isChecked())
        self.onAskUserChanged()

        self.mDefaultProfileComboBox.clear()
        for name in self.mManager.allProfiles():
            profile = self.mManager.profileForName(name)
            self.mDefaultProfileComboBox.addItem(profile.icon() if profile else QIcon(), name)
        self.mDefaultProfileComboBox.setCurrentText(self.mManager.defaultProfileName())

        active = self.mManager.userProfile()
        # The manager has no active profile until one is loaded; the page still has
        # to build so the dialog can open.
        if active is None:
            self.mProfileSelectorGroupBox.setEnabled(False)
            return
        self.mActiveProfileIconButton.setIcon(active.icon())
        self.mActiveProfileIconLabel.setText(f'当前配置档案（{active.name()}）图标')

    def onIconSizeChanged(self, text):
        self.mManager.settings().setValue('/selector/iconSize', int(text or 0))
        self.mManager.settings().sync()

    def onAskUserChanged(self, *args):
        self.mIconSizeLabel.setEnabled(self.mAskUser.isChecked())
        self.mIconSize.setEnabled(self.mAskUser.isChecked())

    def profileFolder(self):
        active = self.mManager.userProfile()
        if active is None: raise ValueError('没有活动配置档案')
        return Path(active.folder())

    def removeIconFiles(self):
        for path in self.profileFolder().glob('icon.*'):
            if path.is_file(): path.unlink()

    def onChangeIconClicked(self):
        path, _ = QFileDialog.getOpenFileName(self, QCoreApplication.translate('QgsUserProfileOptionsWidget', 'Select Icon'), '', ICON_FILTER)
        if not path: return
        self.removeIconFiles()
        # Native stores the profile icon as icon.<extension> inside the profile.
        shutil.copyfile(path, self.profileFolder() / ('icon.' + Path(path).suffix().lstrip('.')))
        self.mActiveProfileIconButton.setIcon(QIcon(path))
        self.refreshIcon(self.mManager.userProfile().name())

    def onResetIconClicked(self):
        self.removeIconFiles()
        profile = self.mManager.userProfile()
        self.mActiveProfileIconButton.setIcon(profile.icon())
        self.refreshIcon(profile.name())

    def refreshIcon(self, name):
        index = self.mDefaultProfileComboBox.findText(name)
        if index >= 0:
            profile = self.mManager.profileForName(name)
            if profile is not None: self.mDefaultProfileComboBox.setItemIcon(index, profile.icon())

    def apply(self):
        if self.mManager is None: return
        if self.mLastProfile.isChecked():
            self.mManager.setUserProfileSelectionPolicy(Qgis.UserProfileSelectionPolicy.LastProfile)
        elif self.mAskUser.isChecked():
            self.mManager.setUserProfileSelectionPolicy(Qgis.UserProfileSelectionPolicy.AskUser)
        elif self.mDefaultProfile.isChecked():
            self.mManager.setUserProfileSelectionPolicy(Qgis.UserProfileSelectionPolicy.DefaultProfile)
            self.mManager.setDefaultProfileName(self.mDefaultProfileComboBox.currentText())
