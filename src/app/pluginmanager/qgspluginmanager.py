"""Local Python plugin management using the upstream qgis.utils lifecycle."""
from pathlib import Path
import sys
import zipfile
import configparser
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QFileDialog, QMessageBox
from qgis.core import QgsApplication
import qgis.utils


class QgsPluginManager(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.mApp = app
        self.mLoaded = set()
        self.setObjectName('QgsPluginManager')
        self.setWindowTitle('Python 插件管理器')
        self.resize(720, 520)
        self.mPluginPath = Path(QgsApplication.qgisSettingsDirPath()) / 'python/plugins'
        self.mPluginPath.mkdir(parents=True, exist_ok=True)
        if str(self.mPluginPath) not in qgis.utils.plugin_paths: qgis.utils.plugin_paths.insert(0, str(self.mPluginPath))
        if str(self.mPluginPath) not in sys.path: sys.path.insert(0, str(self.mPluginPath))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('本地 Python 插件：加载 / 卸载 / 从 ZIP 安装。在线仓库管理尚未移植。'))
        self.mPluginsList = QListWidget()
        layout.addWidget(self.mPluginsList)
        buttons = QHBoxLayout()
        for text, callback in [('刷新', self.refresh), ('加载', self.loadPlugin), ('卸载', self.unloadPlugin), ('从 ZIP 安装', self.installFromZip)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def refresh(self):
        qgis.utils.updateAvailablePlugins()
        self.mPluginsList.clear()
        for name in qgis.utils.available_plugins:
            if name == 'processing' or 'gps' in name.lower() or 'gpx' in name.lower(): continue
            self.mPluginsList.addItem(name + (' [已加载]' if name in self.mLoaded else ''))

    def selectedPlugin(self):
        item = self.mPluginsList.currentItem()
        return item.text().split(' [')[0] if item else None

    def loadPlugin(self):
        name = self.selectedPlugin()
        if not name or name in self.mLoaded: return
        if qgis.utils.loadPlugin(name) and qgis.utils.startPlugin(name):
            self.mLoaded.add(name)
            self.refresh()
        else:
            self.mApp.mMessageBar.pushWarning('插件加载失败', '请查看日志；插件可能依赖尚未移植的桌面接口。')

    def unloadPlugin(self):
        name = self.selectedPlugin()
        if name in self.mLoaded and qgis.utils.unloadPlugin(name):
            self.mLoaded.remove(name)
            self.refresh()

    def unloadAll(self):
        for name in list(self.mLoaded):
            qgis.utils.unloadPlugin(name)
        self.mLoaded.clear()

    def installFromZip(self):
        path, _ = QFileDialog.getOpenFileName(self, QCoreApplication.translate('QgsPluginManager', 'Install Plugin'), '', 'ZIP (*.zip)')
        if not path: return
        try:
            with zipfile.ZipFile(path) as archive:
                files = archive.namelist()
                roots = {name.replace('\\', '/').split('/')[0] for name in files}
                if len(roots) != 1: raise ValueError('ZIP 必须包含一个插件根目录')
                root = next(iter(roots))
                if not root.isidentifier() or 'gps' in root.lower() or 'gpx' in root.lower():
                    raise ValueError('插件目录名称无效或属于 GPS 插件')
                if f'{root}/metadata.txt' not in files or f'{root}/__init__.py' not in files:
                    raise ValueError('缺少 metadata.txt 或 __init__.py')
                target = (self.mPluginPath / root).resolve()
                if target.exists(): raise ValueError('插件已存在，请手动备份并移除旧目录后再安装')
                for name in files:
                    destination = (self.mPluginPath / name).resolve()
                    if not destination.is_relative_to(target): raise ValueError('ZIP 含越界路径')
                archive.extractall(self.mPluginPath)
            self.refresh()
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            QMessageBox.warning(self, '安装失败', str(error))
