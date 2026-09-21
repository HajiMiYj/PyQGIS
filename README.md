# QGIS Python 3.34.10

本项目用 **PyQGIS + PyQt5** 在 OSGeo4W 上实现 QGIS 3.34.10 的**桌面应用层**：`main.py` 是程序入口，`src/app` 与 `src/gui` 里放的是QGIS源代码中 `src/app/*.cpp`、`src/gui/*.cpp` 在 Python 中的对应实现。
内核直接使用 OSGeo4W 的 `qgis-ltr`：`qgis.core`、`qgis.gui`、`qgis.PyQt` 都是原生二进制与绑定。
移植基准是 QGIS `final-3_34_10` 源码树，写法遵循的原则为：**有 PyQGIS 绑定的类直接调用原生实现；没有绑定的，照 C++ 源码在 Python 里复刻同样的行为与命名。**

> [!NOTE]
>
> 注意，QGIS的3D与GPS功能实在是与作者目前需要做的事或感兴趣的内容毫无关系，所以此项目作者拒绝复刻这两个功能



| 指标 | 现状 |
| --- | --- |
| QGIS源代码 action 覆盖 | 222 条中已接入 216 条 |
| 已接入 | **216 条** |
| 部分实现 | 1 条（`mActionDwgImport`，见 [§9](#9-已知差异与限制)） |
| UI 占位（隐藏插入锚点） | 1 条（`mActionAddLayerSeparator`） |
| 未实现 | **0 条** |
| 范围外（GPS + 3D） | 4 条，按项目范围决定排除 |
| 动态 action（工具栏/插件/接口扩展点） | 88 条已接入，0 条未实现 |
| 选项页面 | 26 页 |
| 代码规模 | `src/app` 186 个模块、`src/gui` 12 个、`src/ui` 50 个 `.ui` |

> `main.py` 是应用入口；`src/app` 与 `src/gui` 里的模块与QGIS源代码 C++ 文件一一对应。

---

## 目录

- [1. 项目定位与覆盖范围](#1-项目定位与覆盖范围)
- [2. 运行](#2-运行)
- [3. 目录结构](#3-目录结构)
- [4. 新手教学：从界面走到代码](#4-新手教学从界面走到代码)
- [5. 移植方法论（硬规则）](#5-移植方法论硬规则)
- [6. 关键子系统指南](#6-关键子系统指南)
- [7. 代码规范与红线](#7-代码规范与红线)
- [8. 故障排查 FAQ](#8-故障排查-faq)
- [9. 已知差异与限制](#9-已知差异与限制)
- [10. 贡献流程](#10-贡献流程)
- [11. 参考](#11-参考)
- [附录 A：功能与入口速查](#附录-a功能与入口速查)

---

## 1. 项目定位与覆盖范围

**做的是什么**：一个可以独立启动的 QGIS 桌面程序。打开 `main.py` 启动后，你会得到菜单栏、工具栏、状态栏、图层面板、地图画布、26 页选项对话框、欢迎页、启动画面、Python 控制台、地理配准窗口、DWG/DXF 导入、网格与注记编辑、高程剖面、报表、界面自定义等完整界面，行为与QGIS源代码 C++ 实现对齐。

**代码怎么分层**：

| 层 | 内容 | 位置 |
| --- | --- | --- |
| 内核 | `qgis.core` / `qgis.gui` / `qgis.PyQt`（OSGeo4W 原生二进制） | OSGeo4W `apps/qgis-ltr` |
| 应用层 | 启动流程、主窗口、动作绑定、选项、各功能窗口与工具 | 本仓库 `main.py` + `src/app` |
| 补缺的界面类 | PyQGIS 未暴露、由本项目按 C++ 复刻的 gui 类 | 本仓库 `src/gui` |
| 界面资源 | QGIS源代码 `.ui` 表单、图标、启动图、自定义目录 XML | `src/ui`、`images`、`resources` |
| 插件 | Processing、DB Manager、MetaSearch、GRASS/OTB provider 等原版插件 | OSGeo4W `apps/qgis-ltr/python/plugins` |

**覆盖范围**：主窗口 `.ui` 声明的全部 action，以及QGIS源代码 C++ 运行时动态创建的工具栏/菜单/接口动作。
**范围外**：3D 地图视图与 GPS/GPX 入口共 4 条 action，该决定记录在 `scripts/sync_upstream.py` 的 `OUT_OF_SCOPE_ACTIONS`，因此重新生成清单时它们始终是"排除"而不会变成待办。
**唯一的部分实现**：DWG 导入（GDAL CAD 后端只支持 R2000 及更早版本），细节见 [§9](#9-已知差异与限制)。

**代码量**：

| 语言       | 文件数   | 空白行   | 注释行   | 代码行     |
| :--------- | :------- | :------- | :------- | :--------- |
| Python     | 207      | 2385     | 1246     | 355115     |
| Qt         | 50       | 7        | 0        | 22355      |
| XML        | 12       | 0        | 0        | 5937       |
| SVG        | 960      | 18       | 5        | 3502       |
| Markdown   | 1        | 159      | 0        | 471        |
| DOS 批处理 | 2        | 0        | 0        | 12         |
| INI        | 2        | 1        | 0        | 7          |
| **合计**   | **1234** | **2570** | **1251** | **387399** |

---

## 2. 运行

### 2.1 前置条件

| 依赖 | 说明 |
| --- | --- |
| OSGeo4W | 默认 `C:\OSGeo4W`，需含 `apps/qgis-ltr`（3.34.10）与 `bin/python-qgis-ltr.bat` |
| 解释器 | 使用 OSGeo4W 的 Python（`python-qgis-ltr.bat` 已配好 QGIS 环境变量）；系统 Python 缺少 QGIS 运行时 |
| PyQt5 / QScintilla | OSGeo4W 自带，无需 pip 安装 |

### 2.2 直接运行 main.py

`main.py` 位于仓库根目录，自己会把仓库根目录与 `apps/qgis-ltr/python/plugins` 加入 `sys.path`，因此**从任意工作目录**都可以启动：

```powershell
# 方式一：用绝对路径调用 OSGeo4W 解释器（最稳妥）
& 'C:\OSGeo4W\bin\python-qgis-ltr.bat' C:\Users\worker306\Documents\ChatGPT\qgis_python\main.py

# 方式二：先进入仓库目录
cd C:\Users\worker306\Documents\ChatGPT\qgis_python
& 'C:\OSGeo4W\bin\python-qgis-ltr.bat' main.py

# 方式三：OSGeo4W 的 python 已在 PATH 上时（例如用 OSGeo4W Shell）
python main.py
```

常用参数：

```powershell
python main.py path\to\project.qgz     # 启动并打开工程
python main.py -n                      # 本次不显示启动画面
python main.py -C                      # 本次跳过界面自定义（入口被自定义隐藏时用）
python main.py -z "C:\path\customization.ini"   # 指定外部自定义 INI
python main.py --profile 名称           # 指定配置档案（也可直接传档案目录）
python main.py -S "D:\profiles"        # 指定 profiles 根目录
python main.py --help                  # 全部参数
```

### 2.3 环境变量

| 变量 | 作用 |
| --- | --- |
| `OSGEO4W_ROOT` | OSGeo4W 根目录，默认 `C:\OSGeo4W` |
| `QGIS_PREFIX_PATH` | QGIS 资源前缀，默认 `C:/OSGeo4W/apps/qgis-ltr` |
| `QGIS_CUSTOM_CONFIG_PATH` | 覆盖配置根目录（做隔离实验、回归验证时最常用） |
| `QGIS_PYTHON_NATIVE_PROFILE` | 置 `1` 时使用原生 `QGIS`/`QGIS3` 组织与应用名，与原生 QGIS 共用同一份配置树；默认使用本项目自己的 `QGIS-Python/QGIS-Python-3.34` 树，两边互不覆盖布局与选项 |
| `QGIS_TRANSLATION_CODE` | 强制指定界面翻译代码（等价原生的语言参数） |
| `QGIS_SOURCE_ROOT` | 供 `scripts/*` 使用：本地 3.34.10 源码树路径（脚本默认 `C:\QGIS_COMPILE\QGIS-final-3_34_10`） |
| `QT_QPA_PLATFORM` | 置 `offscreen` 做无头运行（无显示环境时启动） |

### 2.4 首次运行前生成资源

| 输入 | 产物 | 何时重跑 |
| --- | --- | --- |
| `images/images.qrc` | `images/images_rc.py` | 首次取得代码后**必须**执行；资源变更后同样 |
| `src/ui/qgisapp.ui` | `src/ui/ui_qgisapp.py` | 修改主窗口 UI 后（有产物时优先加载，否则回退 `uic.loadUi`） |
| `src/ui/qgsrastercalcdialogbase.ui` | `src/ui/ui_qgsrastercalcdialogbase.py` | 同上 |
| 其余 48 个 `.ui`（`qgsmeasurebase`、`qgsstatisticalsummarybase`、注记/报表/网格/装饰/CAD/选项等） | 运行时 `uic.loadUi` | 无需编译，改完直接重启；若 `src/ui/` 里存在同名 `ui_*.py` 会被优先加载（该文件不入库） |

```powershell
.\scripts\build-resources.cmd
.\scripts\build-ui.cmd
```

**首次取得代码后必须先跑 `build-resources.cmd`**：`main.py` 启动时会 `from images import images_rc`，缺了它无法启动。
`build-ui.cmd` 重建两个预编译 UI；缺失时 `src/app/qgisapp.py` 会回退到 `uic.loadUi`，所以它不影响能否启动。
`images/images_rc.py` 与 `src/ui/ui_*.py` 都在 `.gitignore` 里。
`src/app/**/*.py` 是手写逻辑，不经过 pyuic/pyrcc；运行时引用的原生控件（浏览器、属性表、渲染器等）也不需要重新编译它们的 `.ui`。

---

## 3. 目录结构

```
qgis_python/
├─ main.py                      唯一入口，对应原生 src/app/main.cpp（启动时序见 §6.1）
├─ LICENSE                      GPL-3.0（与QGIS源代码 QGIS 一致）
├─ src/
│  ├─ app/                      对应原生 src/app/*.cpp：应用层，主要开发区（186 个模块）
│  │  ├─ qgisapp.py             主窗口控制器，对应 qgisapp.cpp/.h（动作绑定见 §4）
│  │  ├─ qgisappinterface.py    对应 qgisappinterface.cpp（iface 契约、选项页工厂、action 工厂）
│  │  ├─ qgsproxystyle.py       对应 qgsproxystyle.cpp（QgsAppStyle 被排除出绑定）
│  │  ├─ ui_defaults.py         由 ui_defaults.h 转写的默认窗口布局
│  │  ├─ qgsnativepluginloader.py  ctypes 驱动无绑定的原生插件（拓扑规则引擎）
│  │  ├─ qgswelcomepage.py / qgsrecentprojectsitemsmodel.py / qgsprojectlistitemdelegate.py
│  │  ├─ qgspythonconsole.py    Python 控制台停靠宿主
│  │  ├─ options/               选项对话框与各页面（对应 qgsoptions.cpp + 各 OptionsWidgetFactory）
│  │  ├─ decorations/  dwg/  elevation/  georeferencer/  labeling/  layout/
│  │  └─ maptools/  mesh/  vertextool/  annotations/  locator/  offline_editing/  pluginmanager/
│  ├─ gui/                      对应原生 src/gui：PyQGIS 未暴露的 gui 类在此复刻（12 个）
│  ├─ ui/                       50 个QGIS源代码 .ui + 5 个预编译 ui_*.py
│  └─ __init__.py
├─ python/                      随包发布的 Python 控制台副本（console/、plugins/）
├─ images/                      QGIS源代码图标与启动图资源
├─ resources/                   customization.xml 等
├─ scripts/                     构建脚本：build-resources.cmd、build-ui.cmd
├─ output/                      运行与检查的产物：状态报告、截图、临时目录（被忽略）
└─ .runtime/                    检查模式使用的隔离配置（被忽略）
```

---

## 4. 新手教学：从界面走到代码

这一章的目标：**你点到的任何一个菜单项、工具栏按钮、选项控件，都能在几分钟内找到它的代码位置。**

### 4.1 三步定位法

界面上每个控件都来自QGIS源代码 `.ui`，对象名以 `mAction` 开头（如 `mActionNewProject`）。定位永远是这三步：

1. **拿到对象名**：在 `src/ui/qgisapp.ui` 里搜中文/英文标题，读出该控件的 `objectName`（形如 `mActionXxx`）；
2. **找绑定**：在 `src/app/qgisapp.py` 搜这个名字，看它绑到哪个 Python 方法；
3. **读实现**：跳到那个方法，方法上方通常有注释指出对应的原生函数。

用命令行一步到位：

```powershell
# 1) 按标题找到对象名（例如“装饰 → 网格”）
Select-String -Path src\ui\qgisapp.ui -Pattern '网格|Grid'

# 2) 看这个对象名绑到了什么
Select-String -Path src\app\qgisapp.py -Pattern 'mActionDecorationGrid'

# 3) 打开对应实现文件
Get-Content src\app\decorations\qgsdecorationgrid.py -TotalCount 40
```

### 4.2 实例一："工程→新建"执行了什么

**第 1 步**：主窗口的 action 绑定集中在 `src/app/qgisapp.py` 的 `createActions()`，那里有一张 `slots` 表（第 800 行起）：

```python
slots = {
    'NewProject': self.fileNew, 'NewBlankProject': self.fileNewBlank,
    'OpenProject': self.fileOpen, 'CloseProject': self.fileClose, 'RevertProject': self.fileRevert,
    'SaveProject': self.fileSave, 'SaveProjectAs': self.fileSaveAs, 'Exit': self.fileExit,
    ...
}
for name, callback in slots.items(): self.bind('mAction' + name, callback)
```

**第 2 步**：`bind()` 做的事（`qgisapp.py`）：

```python
def bind(self, name, callback, requirement=None, note='', signal='triggered'):
    action = getattr(self, name, None)          # .ui 里的对象
    getattr(action, signal).connect(...)        # 连到 Python 处理器
    self.mImplementedActions[name] = {'handler': callback.__name__, 'note': note}   # 登记状态
    if requirement: self.mRequirements[name] = requirement    # 记录可用条件
```

所以 `mActionNewProject` 点击后执行 `QgisApp.fileNew()`，并自动登记进状态台账。

**第 3 步**：`fileNew()` 就在同一个文件里（搜 `def fileNew`），停靠位置与原生一致；打开原生 `qgisapp.cpp` 搜 `QgisApp::fileNew()` 就能逐步对照。

**带可用性条件的例子**：`mActionDwgImport` 需要当前有可编辑图层，绑定写的是：

```python
self.bind('mActionDwgImport', self.dwgImport, requirement='…')
```

`updateActionState()` 会按 `mRequirements` 在选中图层变化时启停这些 action。

### 4.3 实例二：改一个选项项（样式设置）

选项页的取值/写回不走 `bind()`，而走绑定表，这样"读一次、写一次"的语义集中可控。

**第 1 步**：在 `src/app/options/qgsoptionsbindings.py` 找到键与控件：

```python
COMBO_BINDINGS = [
    ...
    ('cmbStyle', 'qgis/style', '', [(name, name) for name in (...)]),
]
```

**第 2 步**：`qgsoptions.py::comboSetting()` 负责建项、按设置选中、登记进 `mBindings`：

```python
def comboSetting(self, name, key, options, default):
    widget = self.enable(name)
    for title, value in options: widget.addItem(title, value)
    widget.setCurrentIndex(widget.findData(self.settingValue(key, default)))
    self.mBindings.append((key, widget, 'currentData'))     # saveOptions() 会统一写回
```

**第 3 步**：点"确定"时 `saveOptions()` 遍历 `mBindings` 写 `QgsSettings`；启动时 `main.py` 读同一个键：

```python
desiredStyle = settings.value('qgis/style', '', type=str)
```

**改一个选项的完整动作**：确认控件已 `self.enable(...)`、在绑定表里登记、`saveOptions()` 能写回、启动路径能读到；然后在真桌面平台启动一次并核对界面（见 [§10](#10-贡献流程) 的验证步骤）。

### 4.4 实例三：新增一个 action（完整闭环）

以"添加一个打开项目文档的动作"为例：

```python
# ① src/app/qgisapp.py::createActions()，在合适的 slots 字典里加一行
slots = {
    ...
    'OpenDocumentation': self.openDocumentation,     # 会绑定到 mActionOpenDocumentation
}

# ② 实现处理器（放在同类方法附近，注释写明对应原生函数）
def openDocumentation(self):
    """打开项目文档（对应原生 QgisApp::openDocumentation()）。"""
    QDesktopServices.openUrl(QUrl('https://docs.qgis.org/3.34/zh_Hans/docs/index.html'))

# ③ 若动作不是 .ui 声明、而是运行时创建的，登记到动态动作表
self.mDynamicActions['qgisapp:actionDocumentation'] = dict(
    action=self.mActionDocumentation, handler='openDocumentation',
    note='打开在线文档。', inInterface=True)
```

**验证顺序**：
1. 启动程序，点击该菜单项，确认行为；
2. 在真桌面平台（不设 `QT_QPA_PLATFORM`）启动一次，确认该功能可用；
3. 确认相关文档（README 的范围表、`src/ui` 里的对应控件）与实现一致；
4. 提交时写清"做了什么 + 对应原生位置"。

### 4.5 实例四：一条界面文字是怎么被翻译的

1. 界面文字分两类：`.ui` 表单里的（uic 生成的上下文是 `<页面类名>Base`），代码里写的（`self.tr(...)`，上下文是当前类名）。
2. 代码里的原生字符串统一写成显式上下文，便于与QGIS源代码 `.ts` 对齐：

   ```python
   self.mPanelMenu = self.mViewMenu.addMenu(QCoreApplication.translate('QgisApp', 'Panels'))
   ```

3. 想确认某条文字在中文下能否翻译，用一条命令验证（在项目目录执行）：

   ```powershell
   & 'C:\OSGeo4W\bin\python-qgis-ltr.bat' -c "import sys; sys.path.insert(0,'.'); from qgis.core import QgsApplication; a=QgsApplication([],False); QgsApplication.setPrefixPath(r'C:\OSGeo4W\apps\qgis-ltr',True); a.initQgis(); QgsApplication.setTranslation('zh-Hans'); from qgis.PyQt.QtCore import QCoreApplication as Q; print(Q.translate('QgisApp','Panels'))"
   ```

   输出中文说明上下文与目录条目都对；输出英文说明该字符串在 `qgis_zh-Hans.qm` 里没有对应条目（或上下文写错）。

### 4.6 实例五：判断一个 QGIS 类有没有 Python 绑定

写代码前先确认，避免白做或走错路线：

```powershell
& 'C:\OSGeo4W\bin\python-qgis-ltr.bat' -c "from qgis.gui import QgsDockableWidgetHelper"
# ImportError -> 没有绑定：按 §5 的四种手段处理（本仓库 src/gui/qgsdockablewidgethelper.py 就是这种情况）

& 'C:\OSGeo4W\bin\python-qgis-ltr.bat' -c "from qgis.gui import QgsMapCanvas; print([n for n in dir(QgsMapCanvas) if 'render' in n])"
# 能导入 -> 直接用，先看有没有你需要的成员
```

### 4.7 常用定位命令速查

| 想找什么 | 命令 |
| --- | --- |
| 某个 action 绑到哪个方法 | `Select-String -Path src\app\qgisapp.py -Pattern 'mActionXxx'` |
| 某个设置键在哪些地方读写 | `Select-String -Path src -Recurse -Pattern 'qgis/style'` |
| 某个原生类在端口里的对应文件 | `Get-ChildItem src -Recurse -Filter '*snapping*'` |
| 某条界面文字 | `Select-String -Path src -Recurse -Pattern 'Panels'` |
| 某个动态动作的登记 | `Select-String -Path src\app\qgisapp.py -Pattern 'mDynamicActions'` |

---

## 5. 移植方法的原则

1. **优先用 PyQGIS 绑定**。`qgis.core` / `qgis.gui` 里有的类直接实例化。
2. **没有绑定就照 C++ 复刻**。类名、方法名、信号名、参数顺序与语义对齐QGIS源代码；docstring 写明"对应 xxx.cpp 的 xxx()"。
3. **不写伪替身**。空壳类会掩盖真实缺口；确实受后端限制（如 DWG 版本）时在 [§9](#9-已知差异与限制) 写明原因。
4. **注释引用原生位置**。方便后来者对照源码验证：

   ```python
   # Native main.cpp style selection: qgis/style, fusion for non-default UI themes,
   # and the known-broken adwaita styles rejected outright.
   ```

5. **无绑定时的四种手段**（按优先级）：

   | 手段 | 适用场景 | 实例 |
   | --- | --- | --- |
   | 用**更下层** API 重组原逻辑 | 高层 API 未绑定，底层组件可用 | 嵌入图层：`QgsProject::createEmbeddedLayer()` 未绑定 → 用 `QgsLayerDefinition.loadLayerDefinitionLayers()` + 源工程路径解析复现；网格拾取：`nativeMesh()/triangularMesh()` 未绑定 → 走可绑定接口 |
   | **ctypes 直调原生 DLL** | 逻辑在 C++ 库里且无 Python 出口 | 拓扑规则引擎：解析 `plugin_topology.dll` 导出表 + `classFactory` + `QgisPlugin` vtable（`qgisnativepluginloader.py`）；OpenCL 设备枚举（`options/qgsopenclutils.py` 调 `OpenCL.dll`） |
   | **按 C++ 重写 Python 类** | 类整体未绑定，依赖的 Qt/QGIS 组件都可用 | `QgsProjectListItemDelegate`、`QgsNewsItemListItemDelegate`、`QgsProjectPreviewImage`、`QgsRecentProjectItemsModel`、`QgsTemplateProjectsModel`、`QgsWelcomePage`、`QgsVersionInfo`、`QgsDockableWidgetHelper` |
   | **绕开无法配置的 C++ 单例** | C++ 类存在，静态钩子无法从 Python 设置 | Python 控制台宿主 `PythonConsoleDock`（`QgsDockableWidgetHelper::sAddTabifiedDockWidgetFunction` 是 `std::function` 静态成员，PyQt 无法赋值，因此用端口自己的 helper 完成停靠） |

6. **就地修 bug**。按原生语义修，例如 `QgsVectorLayer.addCurvedRing()` 只接受 `QgsCurve`，就把捕获到的面归一化成曲线。
7. **不用退路式标签**。"部分实现（PyQGIS 绑定缺失）"这类逃避性状态不写；真做不了要写清具体限制与替代路径（该状态当前为空集）。

---

## 6. 关键子系统指南

### 6.1 启动时序：main.py 与原生 main.cpp/qgisapp.cpp

改启动行为时保持与原生相同的顺序，否则容易出现"设置不生效 / 面板不恢复"这类问题。

| 阶段 | 端口位置 | 原生对应 |
| --- | --- | --- |
| 参数解析、档案解析与切换 | `main.py::resolveProfile` | `main.cpp` 参数块 + `QgsUserProfileManager` |
| 组织/应用名、profile 根目录 | `main.py` 前置块 | `main.cpp` 设置 `QCoreApplication` 名称 |
| 样式选择（`qgis/style`、非默认主题强制 fusion、adwaita 拒绝） | `main.py` 样式块 | `main.cpp:1440-1475` |
| 主题应用 `QgsApplication.setUITheme()` | `main.py` | `QgisApp::setTheme()` → `QgsApplication::setUITheme()` |
| 本地化（命令行 → 用户覆盖 → 系统 locale） | `main.py` locale 块 | `main.cpp` locale 块 |
| 启动画面（尺寸/遮罩/居中） | `main.py` splash 块 | `main.cpp:1483-1509`（QGIS源代码已注释，语义保留） |
| 构造主窗口：分阶段启动消息、欢迎页、最近工程、文件过滤器、图标尺寸… | `src/app/qgisapp.py::__init__` | `qgisapp.cpp` 构造函数 |
| `show()` → `completeInitialization()` → `fileOpenAfterLaunch()` | `main.py` 尾部 | `main.cpp:1787-1793` |
| 退出：保存窗口状态、卸载插件、`exitQgis()` | `qgisapp.py::saveWindowState/closeEvent/fileExit` | `QgisApp` 同名方法 |

启动项目分流由 `QgisApp.fileOpenAfterLaunch()` 实现，对应原生 `qgisapp.cpp:5913-6030`：

| `qgis/projOpenAtLaunch` | 行为 |
| --- | --- |
| `0` | 显示欢迎页（central `QStackedWidget` 第 1 页），并连接 `newProject`/`projectRead` → `showMapCanvas` |
| `1` | 打开最近工程列表首项 |
| `2` | 打开 `qgis/projOpenAtLaunchPath` |
| `3` | 新建空白工程（`qgis/newProjectDefault` 为真时载入默认模板） |

失败保护：`qgis/projOpenedOKAtLaunch` 为假时提示一次 `Failed to open: …` 并把 `projOpenAtLaunch` 重置为 0，避免反复打开坏工程。
`layersChanged → showMapCanvas`：在欢迎页上添加图层或打开工程会自动切回画布。

### 6.2 主窗口控制器 qgisapp

按原生构造函数顺序展开：`createCanvas` / `createMenus` / `createStatusBar` / `createLayerTreeView` / `createDockWidgets` / `createMapTools` / `createActions` / `createToolBars`…

- `bind(name, callback, requirement, note)`：把动作连到处理器、按 `requirement` 登记可用条件（[§4.2](#42-实例一工程新建执行了什么)）。
- `mDynamicActions`：运行时创建的动作（工具栏/插件扩展点/接口方法），登记 `handler`/`note`/`inInterface`。
- `mRequirements` + `updateActionState()`：按当前图层类型/编辑状态启停动作。

### 6.3 选项对话框

- `src/app/options/qgsoptions.py` 是主对话框：先应用绑定表（`qgsoptionsbindings.py` 的 `PLAIN_BINDINGS`/`COMBO_BINDINGS`/`COLOR_BINDINGS`），再初始化各页，最后 `saveOptions()` 统一落盘并 `applyToApplication()` 处理可即时生效项。
- 26 页里的"工厂页"来自插件注册：`QgisAppInterface.registerOptionsWidgetFactory()` 收集，`qgsoptions.py` 逐页构建。新增页面优先用工厂方式，原生插件自带页面（Processing、渲染、高程、代码编辑器等）会自动出现。
- 易错点：
  - **保存语义对齐原生**：`UI/UITheme` 在 `qgsoptions.cpp:1497` 保存、`qgis/style` 在 `qgsoptions.cpp:1671` 保存、覆盖开关在 `qgsoptions.cpp:1873` 保存（`locale/overrideFlag` 曾漏写，导致"选了简体中文重启还是英文"）。
  - **未选中的下拉框不要写 `max(0, findData(...))`**：原生用 `findData()` 直接赋值，未命中为 `-1`；`max(0, …)` 会静默写入第一项（曾把 `locale/globalLocale` 写成 `C`）。
  - 组合框取值写回设置前把 `None` 归一化成 `''`。
  - 需要重启的项在标签上注明"（需要重启 QGIS）"。

### 6.4 最近工程、欢迎页、模板、自绘列表

| 端口文件 | 原生对应 | 说明 |
| --- | --- | --- |
| `qgsrecentprojectsitemsmodel.py` | `qgsrecentprojectsitemsmodel.cpp` | 模型与角色（Title/Path/NativePath/Crs/Pin/AnonymisedNativePath）、存在性检查（先项目存储后本地文件，结果缓存） |
| `qgsprojectlistitemdelegate.py` | `qgsprojectlistitemdelegate.cpp` | 两个自绘代理 + `QgsProjectPreviewImage` |
| `qgstemplateprojectsmodel.py` | `qgstemplateprojectsmodel.cpp` | 模板目录扫描、`preview.png` 解压读取、"New Empty Project" 占位项 |
| `qgswelcomepage.py` | `qgswelcomepage.cpp` | 三栏布局（最近工程 / 新闻 / 模板）、右键菜单（固定/取消固定/刷新/移除/清空）、版本横幅 |
| `qgsversioninfo.py` | `qgsversioninfo.cpp` | 版本检查（`https://version.qgis.org/version.txt`） |

- 存储与原生同键：`UI/recentProjects/N`（`title/path/previewImage/crs/pin`），含 `UI/recentProjectsList` 旧键迁移、`maxRecentProjects`（默认 20）截断、固定项置顶且不参与截断、保存工程时生成 250×177 预览图。
- 欢迎页在QGIS源代码 3.34 被整体注释（`qgisapp.cpp:1089-1132`），端口按类与设置项的原义实现出来，"启动时打开工程 = 欢迎页"才有落点。
- "New Empty Project" 行走 `fileNewBlank()`：QGIS源代码这里写的是 `QgisApp::instance()->newProject()`，而 `newProject` 是信号，C++ 里那行只是发射信号；端口走真正的新建工程路径。

### 6.5 启动画面（分阶段消息）

端口按原生顺序显示 11 段：

```
Checking database → Reading settings → Setting up the GUI → Checking provider plugins →
Starting Python → Restoring loaded plugins → Updating recent project paths →
Initializing file filters → Restoring window state → Populate saved styles → QGIS Ready!
```

实现要点：`QgisApp.showSplashMessage()` 用 `self.tr(text)`（QgisApp 上下文，可被翻译），对齐方式与文字颜色对齐原生（`releaseName() == "Master"` 绿色，否则黑色），每次消息后 `processEvents()` 让它逐段绘出；尺寸/遮罩/居中同原生（600×300 等比 + `setMask`）；`qgis/hideSplash` 与 `-n` 均生效；检查模式跳过启动画面。

### 6.6 本地化

- **加载机制**：`QgsApplication.setTranslation(code)` 安装 `qgis_<code>.qm` 与 `qt_<code>.qm`，精确匹配代码。系统 locale 为 `zh_CN` 时匹配不到已安装的 `qgis_zh-Hans.qm`，因此需要在选项里显式选语言并勾选覆盖系统语言环境（`locale/overrideFlag`）。
- 语言下拉框由 `QgsOptions.installedTranslations()` 枚举 `QgsApplication.i18nPath()` 下的 `qgis*.qm` 生成；选中语言会自动勾选覆盖开关。
- **不使用国旗图标**：语言代码对应的是语言而非国家，列表只显示语言自身的名称。
- 代码文本约定：原生字符串一律 `QCoreApplication.translate('<原生上下文>', '<原生英文源串>')`（已按此改写 249 处，验收方式是在 zh-Hans 下逐条断言"翻译结果 == 改写前的中文字面量"，当前 249/249 一致）；`.ui` 文本的上下文是 `<页面类名>Base`；端口自创且翻译目录里没有的文案保留中文。

### 6.7 主题、样式与图标尺寸

- `QgsApplication.setUITheme(theme)` 是完整主题实现（`style.qss` + `variables.qss` 变量替换 + `palette.txt` + 图标主题），经 `qApp->setStyleSheet` 应用。
- 原生规则：`UI/UITheme` 非 `default` 时强制 `fusion`；adwaita 样式拒绝。端口在 `main.py` 按同样规则选样式，并经 `QgsAppStyle` 代理安装（原生该类被 `#ifndef SIP_RUN` 排除出绑定，见 `src/app/qgsproxystyle.py`）。
- 图标尺寸：`QGIS_ICON_SIZE = 24`（非 macOS）；`QgisApp.setIconSizes(size)` 给工具栏 `size`、面板工具栏 `panelIconSize(size)`（16；`>32` 时 `size-16`；`==32` 时 24）。

### 6.8 面板与窗口状态持久化

- 布局在**首次 show** 时恢复（Qt `QTBUG-89034`，QGIS源代码同样把 `restoreState()` 挪到 `showEvent`），退出时经 `aboutToQuit → saveWindowState()` 写 `UI/state`、`UI/geometry`；无保存时用 `src/app/ui_defaults.py` 的默认布局。
- **延迟创建的 dock 需要额外处理**：`restoreState()` 只能恢复已存在的 dock。Python 控制台的宿主基类还依赖无法从 PyQt 设置的静态钩子，因此：
  - `src/app/qgspythonconsole.py` 用端口自己的 `QgsDockableWidgetHelper` 完成停靠，并保留控制台要求的契约 `dockToggleButton()/isUserVisible()/setUserVisible()/activate()`（控制台工具栏会调用 `parent.dockToggleButton()`）；
  - `UI/pythonConsoleVisible` 记录可见性，`showEvent()` 中**先重建控制台再 `restoreState()`**，停靠区域与几何由 `UI/state` 恢复；
  - `visibilityChanged` 接到菜单项勾选状态（原生 `console.py:65` 同款）。
- `QgsDockableWidgetHelper.toggleDockMode()` 的原生语义是"新建 dock 后 `setUserVisible(true)`"，不要按"上一个宿主是否可见"推断。
- Qt 只保存**有 `objectName`** 的 dock：普通面板不恢复时先查它的 `objectName`。

### 6.9 无 PyQGIS 绑定的实例清单

| 缺失的绑定 | 端口做法 | 文件 |
| --- | --- | --- |
| `QgsProject::createEmbeddedLayer()` | `QgsLayerDefinition.loadLayerDefinitionLayers()` + 源工程路径解析 | `src/app/qgisapp.py` |
| `QgsMeshLayer::nativeMesh()/triangularMesh()` | 走可绑定接口完成拾取/编辑 | `src/app/mesh/` |
| `QgsDockableWidgetHelper` | 按 C++ 复刻 Python 版 | `src/gui/qgsdockablewidgethelper.py` |
| `QgsVersionInfo` | 用 `QgsNetworkAccessManager` 复刻协议 | `src/app/qgsversioninfo.py` |
| `QgsProjectListItemDelegate` 等列表类 | 按 C++ 复刻 | [§6.4](#64-最近工程欢迎页模板自绘列表) |
| `QgsLoadRasterAttributeTableDialog` / `QgsCreateRasterAttributeTableDialog` | 按原生逻辑重建 | `src/app/qgsrasterattributetableapputils.py` |
| `QgsAppStyle` | 仿写代理样式 | `src/app/qgsproxystyle.py` |
| `QgsGui::nativePlatformInterface()` | 用 `QDesktopServices` 等价实现 | `src/app/qgswelcomepage.py` |
| 拓扑规则引擎 | ctypes 加载 `plugin_topology.dll` | `src/app/qgisnativepluginloader.py` |
| OpenCL 设备枚举 | ctypes 调 `OpenCL.dll` | `src/app/options/qgsopenclutils.py` |

---

## 7. 代码规范

**风格**

- 方法用 `camelCase`，与QGIS源代码 QGIS 命名一致。
- 紧凑单行（`if x: return y`）贴近 C++ 原版密度，逻辑复杂时才展开。
- 面向用户的文案：原生字符串走 `translate()`，端口自创文案用中文。
- 新模块开头一句 docstring，写明对应原生哪个文件。

**红线**

1. **不引入回归**：改动后至少手动走一遍受影响的界面路径，并确认启动无异常（见 [§10](#10-贡献流程)）。
2. **不用伪实现充数**：做不了就写清限制。
3. **不静默写错设置**：写 `QgsSettings` 前核对键名、默认值与原生一致（`locale/*`、`UI/*`、`qgis/*` 是历史事故高发区）。
4. **不新增第三方依赖**：只用 OSGeo4W 自带的 Python/PyQt/QGIS。
5. **不提交运行时产物与调试脚本**：`output/`、`.runtime/`、`images/images_rc.py`、`src/ui/ui_*.py` 已在忽略列表；临时脚本用完删除。
6. **改 `.ui` 后重编译**（`scripts/build-ui.cmd`），并确认 `uic.loadUi` 回退路径同样可用。
7. **判空用 `isDeleted()`**：`sip.isdeleted()` 只接受被包装的 C++ 对象，对纯 Python 协作对象会抛 `TypeError`（见 `src/app/qgisapp.py` 顶部 `isDeleted()`）。

---

## 8. 故障排查 FAQ

**启动时报 `Problem with OTB installation: OTB folder is not set.`（CRITICAL）**
这是 QGIS 自带 **OTB Provider 插件**的日志（`otbprovider/OtbAlgorithmProvider.py:126`）：Processing 启动时注册该 provider，它发现 Processing 里没有 OTB 目录（`OTB_FOLDER`）就记一条 CRITICAL 并跳过加载。本机未安装 OTB（`C:\OSGeo4W\apps` 下无 OTB，也没有 `otbApplicationLauncher*.exe`），因此这是预期结果，含义是"没有 OTB 那批遥感算法"；原生 QGIS 3.34.10 在同样未配置时也打印同一行。要用就装 OTB，并在 **设置 → 选项 → 处理 → 提供者 → OTB → OTB 文件夹** 指定路径（键 `Processing/Configuration/OTB_FOLDER`）；配置正确后日志变成 `Loading OTB 'x.y.z'.`。

**离屏运行刷屏 `QFontDatabase: Cannot find font directory …`**
offscreen 平台没有字体目录，属正常噪声；不要基于离屏字体度量做断言。

**启动画面不显示**
依次检查 `qgis/hideSplash` 设置、是否传了 `-n`、以及是否处于检查模式（检查模式跳过启动画面）。

**"选项窗口打不开"**
历史事故：`QgisApp` 未调用 `QgsUserProfileManager.setActiveUserProfile()`，`userProfile()` 为 `None`，用户配置页构造时崩溃。改 profile 相关代码后请跑 `--profile-test` 与 `--startup-test`。

**改了设置重启后不生效**
先确认该键**是否真的被保存**（多数历史事故是"只读没写"），再确认启动路径是否读取它（[§6.1](#61-启动时序mainpy-与原生-maincppqgisappcpp) 顺序表）。语言类问题另见 [§6.6](#66-本地化)：需要同时有 `locale/userLocale` 与 `locale/overrideFlag`。

**面板（尤其 Python 控制台）重启后消失**
见 [§6.8](#68-面板与窗口状态持久化)：延迟创建的 dock 需要"记录可见性 + 在 `restoreState()` 之前重建"。普通面板由 `UI/state` 恢复；某个普通面板不恢复时，先查它的 `objectName` 是否为空。

**直接运行 `main.py` 报 `ModuleNotFoundError: No module named 'src'`**
确认运行的是仓库根目录下的 `main.py`（它会把自身目录加入 `sys.path`）；把 `main.py` 挪到别处会破坏这一约定。

**调试时 stdout 突然不见了**
打开 Python 控制台会把 `sys.stdout` 重定向到控制台部件（原生行为），此时 `faulthandler.enable()` 之类会失败；调试脚本写文件而不是 `print`。

**`--xxx-test` 跑了别的检查**
`main.py` 是 `elif` 链：一次调用只跑第一个命中的标志，请一次只传一个。

---

## 9. 已知差异与限制

| 项 | 现状 | 原因 / 改进方向 |
| --- | --- | --- |
| DWG 导入（`mActionDwgImport`） | 状态 `partial` | 依赖 GDAL CAD 驱动（libopencad），支持 R2000 及更早版本，块插入模式不可用；DXF 已支持真实曲线（ARC/CIRCLE/bulge）与 ASCII/二进制图层状态。改进需更换 CAD 后端 |
| 3D 地图视图、GPS/GPX 入口 | 排除（4 条 action） | 按项目范围决定；`scripts/sync_upstream.py` 的 `OUT_OF_SCOPE_ACTIONS` 记录该决定，重新生成清单不会把它们算成待办 |
| 中文界面下 Qt 标准按钮（OK/Cancel）显示英文 | 与原生一致 | 原生按精确代码加载 `qt_<code>.qm`，而 `qt_zh-Hans.qm` 不存在（只有 `qt_zh_CN.qm`）；端口沿用原生行为 |
| 欢迎页自绘项 | 高度接近原生，非逐像素 | 自绘代理由 C++ 复刻；`QgsScopedQPainterState` 未绑定，用 `save()/restore()` 等价替换 |
| 端口自创文案 | 保持中文 | 改成 `tr()` 会在中文界面显示英文；若要英文界面，应把这些文案的英文源串补进翻译目录 |
| `QgsGui::nativePlatformInterface()` | 用 `QDesktopServices` 等价实现 | 该单例未绑定；"打开所在目录"等行为等价，调用路径不同 |
| Processing 提供者可执行性 | 取决于环境 | 例如 GRASS/OTB 需要各自安装与配置（见 FAQ）；端口负责注册与选项页，执行能力由 OSGeo4W 组件决定 |
| **本地化** | 用户界面语言项，统一取消了用户界面语言的旗帜的显示 | **存在项目作者个人不认可的旗帜** |

---

## 10. 贡献流程

1. **定位原生实现**：在 3.34.10 源码树找到对应 `*.cpp/*.h`（应用层 `src/app`，界面组件 `src/gui`），读清调用顺序与设置键。
2. **判断绑定可用性**：用 [§4.6](#46-实例五判断一个-qgis-类有没有-python-绑定) 的命令确认；不可用时按 [§5](#5-移植方法论硬规则) 选择手段。
3. **实现**：文件名/类名/方法名对齐原生，注释标注原生位置。
4. **自测**：在真桌面平台启动一次，走一遍受影响的功能路径，并确认启动消息与日志无异常。
5. **视觉验证（涉及界面时）**：用真桌面平台（不设 `QT_QPA_PLATFORM`）直接跑 `main.py` 并截图核对；离屏截图无字体、不可信。
7. **清理与提交**：删除临时脚本与临时配置目录；提交信息写清"做了什么 + 对应原生位置"，一个主题一个提交。

提交信息前缀沿用仓库现状：`修复…`、`实现…`、`本地化：…`。

---

## 11. 参考

**原生源码（3.34.10）关键文件**

| 主题 | 文件 |
| --- | --- |
| 启动时序、样式/locale/参数 | `src/app/main.cpp` |
| 主窗口、动作、设置、最近工程、启动分流 | `src/app/qgisapp.cpp` / `qgisapp.h` |
| 选项对话框 | `src/app/options/qgsoptions.cpp` |
| 欢迎页/最近工程/列表代理/模板 | `src/app/qgswelcomepage.cpp`、`qgsrecentprojectsitemsmodel.cpp`、`qgsprojectlistitemdelegate.cpp`、`qgstemplateprojectsmodel.cpp` |
| 版本检查 | `src/app/qgsversioninfo.cpp` |
| 停靠/浮动契约 | `src/gui/qgsdockablewidgethelper.cpp` |
| 控制台 | `python/console/console.py` |
| Processing 提供者注册 | `python/plugins/processing/Processing.py` |
| OTB 提供者 | `python/plugins/otbprovider/OtbAlgorithmProvider.py` |

**外部参考**

- PyQGIS API：<https://github.com/qgis/pyqgis-api-docs-builder/releases/download/3.34/pyqgis-docs-3.34.zip/>，注意，3.34版本的API已经不让在线查看了，你得下载
- QGIS 源码：<https://github.com/qgis/QGIS/tree/final-3_34_10>
- Qt 5.15：<https://doc.qt.io/qt-5/>

**仓库内入口速查**

| 我想… | 看这里 |
| --- | --- |
| 找到某个菜单项/按钮的代码 | [§4.1](#41-三步定位法) 三步定位法 |
| 加/改一个 action | [§4.4](#44-实例三新增一个-action完整闭环) + `qgisapp.py::createActions` |
| 改一个选项项 | [§4.3](#43-实例二改一个选项项样式设置) + `src/app/options/` |
| 改启动流程 | `main.py` + [§6.1](#61-启动时序mainpy-与原生-maincppqgisappcpp) |
| 改欢迎页/最近工程 | [§6.4](#64-最近工程欢迎页模板自绘列表) |
| 改一条翻译 | [§4.5](#45-实例四一条界面文字是怎么被翻译的) + [§6.6](#66-本地化) |
| 看某功能对应哪个原生文件 | [§11](#11-参考) 的原生文件表 |
| 排查会抛异常的选项页 | `scripts/exercise_options.py`、`window.runtimeErrors` |

---

## 附录 A：功能与入口速查

各子系统的入口、对应检查与报告文件。所有检查当前全部通过（20/20）。

| 子系统 | 主要入口 |
| --- | --- |
| 主窗口/动作总览（含属性表、控制台停靠、测量、选择、统计摘要、顶点编辑器、地图主题、图例过滤、地图提示） | 菜单与各工具栏 |
| 启动契约（分阶段启动消息、欢迎页、`projOpenAtLaunch` 四态、最近工程存储、控制台停靠） | 启动过程 |
| 配置档案（解析、询问策略、`--profile`/`-S`、退出写回 `lastProfile`） | 设置 → 用户配置 |
| 界面自定义（六类配置树、搜索、捕获 `Ctrl+M`、INI 导入导出、应用/重置/取消） | 设置 → 界面自定义 |
| 状态栏（坐标/范围、比例尺与锁定、放大镜、旋转、渲染进度、CRS 与日志按钮） | 状态栏 |
| 图层树右键（更改/修复数据源、可见比例尺缩放、栅格属性表、组 WMS 数据） | 图层面板右键 |
| 数字化与 CAD（移动/复制、分割、重塑、增删环、部件） | 高级数字化工具栏 |
| 修剪/延伸要素（线段捕捉、两侧修剪/延伸、Z/M、多部件、跨 CRS、拓扑节点、撤销） | 高级数字化工具栏 |
| 形状数字化（5 圆/4 椭圆/4 矩形/3 正多边形/半径圆弧，共 17 项） | 形状工具栏 |
| 填充环、添加环、添加部件与形状共用捕获 | 高级数字化工具栏 |
| 测量（距离/面积/角度/方位角，单位切换、椭球/平面、撤销） | 属性工具栏测量下拉 |
| 选择（矩形/多边形/自由手绘/半径，Shift/Ctrl 修饰语义） | 选择工具栏 |
| 统计摘要（字段/表达式、仅选中要素、后台可取消） | 视图菜单 / 属性工具栏 |
| 顶点编辑器（X/Y/Z/M 表格、双击修改、撤销、定位） | 顶点工具下拉 / 面板菜单 |
| 装饰：网格、布局范围、比例尺、图片、标题、版权、指北针 | 视图 → 装饰 |
| 注记：旧式（文本/SVG/HTML/表单）、新式注记图层、修改注记工具 | 注记工具栏 |
| 报表（章节树、字段分组、页眉/页脚、PDF 导出、工程保存） | 工程 → 新建报表 |
| 标注工具栏九个动作、修改标注、高亮固定标注、显示未放置标注 | 标注工具栏 |
| 高程剖面（图层树、剖面绘制/拾取、测量、X 轴缩放、单位、图片/PDF 导出） | 视图 → 高程剖面 |
| 网格编辑（三角化、翻转/合并边、新面预览、Z 修改、删除快捷键、撤销、坐标变换） | 网格工具栏 |
| 网格计算器、新建网格图层 | 网格菜单 |
| DWG/DXF 导入（图层选择、分组/合并、三种块模式、样式与标注映射） | 图层 → 导入 CAD |
| 数据类动作（DXF 导出、新建 SpatiaLite 图层、粘贴为新图层、要素动作、嵌入图层） | 工程/编辑菜单 |
| 形状捕获与网格批处理补充 | — |
| 工具栏运行时排列与动态按钮（注记创建、文字属性、Web 扩展接口） | 各工具栏 |
| 地理配准（24 个 Action、GCP、变换、栅格/矢量输出、GDAL 脚本） | 栅格 → 地理配准 |
| 自定义投影（原生 CRS 编辑表单、批量删除、取消不写入） | 设置 → 自定义投影 |
| 剖面图层树与网格顶点移动 | — |
| 选项对话框（26 页：常规/系统/用户配置/CRS/变换/数据源/GDAL/渲染/栅格/矢量/画布/地图工具/数字化/高程/颜色/字体/布局/变量/认证/网络/定位器/加速/代码编辑器/控制台/高级/处理） | 设置 → 选项 |
| 本地化（语言列表、覆盖开关、249 条原生字符串翻译） | 设置 → 选项 → 常规 → 本地化语言环境 |
| 主题与样式（`UI/UITheme`、`qgis/style`、fusion 规则、图标尺寸） | 设置 → 选项 → 常规 → 应用程序 |

> 说明：
>
> 1. 表中的子系统均已接入并在当前环境验证；第三方插件、服务器连接与各类数据格式建议用实际数据再验证一次。
>
> 2. 矩阵说明的是"该功能由哪项检查覆盖"。检查通过表示该批行为在当前环境验证通过，第三方插件、服务器连接、各类数据格式仍建议用实际数据验证。