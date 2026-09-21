# QGIS Python 3.34.10：桌面应用层的源码级移植

用 **PyQGIS + PyQt5** 在 OSGeo4W 上重建 QGIS 3.34.10 的**桌面应用层**（`src/app`、`src/gui` 中原本由 C++ 实现、Python 无法直接复用的部分）。
移植基准是 QGIS `final-3_34_10` 源码树：**能用 PyQGIS 绑定就直接用原生实现；没有绑定的，照 C++ 源码在 Python 里复刻**，不写"看起来像"的替身类。

| 指标 | 现状 |
| --- | --- |
| 上游 action 清单 | 222 条（`docs/upstream-actions.json`） |
| 已接入 | **216 条** |
| 部分实现 | 1 条（`mActionDwgImport`，见 [§10](#10-已知差异与限制)） |
| UI 占位（隐藏插入锚点） | 1 条（`mActionAddLayerSeparator`） |
| 未实现 | **0 条** |
| 范围外（GPS + 3D） | 4 条，按项目决定排除 |
| 动态 action（工具栏/插件/接口扩展点） | 88 条已接入，0 条未实现 |
| 选项页面 | 26 页 |
| 代码规模 | `src/app` 186 个模块、`src/gui` 12 个、`src/ui` 50 个 `.ui` |
| 运行时套件 | 20 套，全部通过（见 [§6](#6-测试体系)） |

> 上表数字不是手写文档：程序每次启动都会重新统计并生成 `功能移植清单.md` 与 `docs/implementation-status.json`（见 [§7](#7-状态文档与脚本)）。

---

## 目录

- [1. 这是什么 / 不是什么](#1-这是什么与不是什么)
- [2. 环境与快速开始](#2-环境与快速开始)
- [3. 目录结构](#3-目录结构)
- [4. 移植方法论（硬规则）](#4-移植方法论硬规则)
- [5. 关键子系统开发者指南](#5-关键子系统开发者指南)
- [6. 测试体系](#6-测试体系)
- [7. 状态文档与脚本](#7-状态文档与脚本)
- [8. 代码规范与评审红线](#8-代码规范与评审红线)
- [9. 故障排查 FAQ](#9-故障排查-faq)
- [10. 已知差异与限制](#10-已知差异与限制)
- [11. 贡献流程](#11-贡献流程)
- [12. 参考](#12-参考)
- [附录 A：功能与验收矩阵](#附录-a功能与验收矩阵)

---

## 1. 这是什么与不是什么

**是**：一个可独立启动的 QGIS 桌面程序（入口 `src/app/main.py`）。应用层逻辑按原版 C++ 文件一一对应地移植，行为以原生源码为准绳，改哪里都能在源码树里找到对照。

**不是**：

- 不是内核重写。`qgis.core` / `qgis.gui` / `qgis.PyQt` 全部来自 OSGeo4W 的 `qgis-ltr`；端口只负责**应用层**，以及少量被绑定遗漏的 gui/app 类。
- 不是原版 QGIS 的完整替代品：3D 地图视图与 GPS 相关入口**按决定排除**；DWG 导入受 GDAL/libopencad 后端限制（[§10](#10-已知差异与限制)）。
- 不是插件集合：Processing、DB Manager、MetaSearch、GRASS/OTB provider 等都是 OSGeo4W 里的原版插件，端口负责的是它们的**启动、集成与接口**（`iface` 契约、选项页工厂、action 插入等）。

---

## 2. 环境与快速开始

### 2.1 前置条件

| 依赖 | 说明 |
| --- | --- |
| OSGeo4W | 默认 `C:\OSGeo4W`，需含 `apps/qgis-ltr`（3.34.10）与 `bin/python-qgis-ltr.bat` |
| Python | **不要用系统 Python**，一律经 `python-qgis-ltr.bat` 启动 |
| PyQt5 / QScintilla | OSGeo4W 自带，无需 pip 安装 |

版本基准是 3.34.10；`main.py` 里保留着版本断言但目前被注释（历史原因），实际按 3.34.10 的 API 面编写。

### 2.2 启动

```powershell
cd C:\Users\worker306\Documents\ChatGPT\qgis_python
.\run-qgis-python.cmd                       # 启动 GUI
.\run-qgis-python.cmd path\to\project.qgz   # 启动并打开工程
.\run-qgis-python.cmd -n                    # 本次不显示启动画面
.\run-qgis-python.cmd -C                    # 本次跳过界面自定义（排查入口被隐藏时用）
.\run-qgis-python.cmd -z "C:\path\customization.ini"   # 指定外部自定义 INI
.\run-qgis-python.cmd --profile 名称         # 指定配置档案（也可传档案目录）
.\run-qgis-python.cmd -S "D:\profiles"      # 指定 profiles 根目录
```

`run-qgis-python.cmd` 只做两件事：把仓库根目录与 `apps/qgis-ltr/python/plugins` 加进 `PYTHONPATH`，再调用
`python-qgis-ltr.bat src\app\main.py %*`。**测试也走同一个入口**（[§6](#6-测试体系)）。

### 2.3 环境变量

| 变量 | 作用 |
| --- | --- |
| `OSGEO4W_ROOT` | OSGeo4W 根目录，默认 `C:\OSGeo4W` |
| `QGIS_PREFIX_PATH` | QGIS 资源前缀，默认 `C:/OSGeo4W/apps/qgis-ltr` |
| `QGIS_CUSTOM_CONFIG_PATH` | 覆盖配置根目录（**做隔离实验/回归时最常用**） |
| `QGIS_PYTHON_NATIVE_PROFILE` | 置 `1` 时使用原生 `QGIS`/`QGIS3` 组织与应用名，与原生 QGIS 共用同一份配置树；默认关闭，端口用自己的 `QGIS-Python/QGIS-Python-3.34` 树，避免两边互相覆盖布局与选项 |
| `QGIS_TRANSLATION_CODE` | 强制指定界面翻译代码（等价原生 `--lang`） |
| `QGIS_SOURCE_ROOT` | 仅 `scripts/*` 使用：本地 3.34.10 源码树路径（脚本默认 `C:\QGIS_COMPILE\QGIS-final-3_34_10`） |
| `QT_QPA_PLATFORM` | 置 `offscreen` 做无头运行；跑测试时必须设置 |

### 2.4 生成物与构建脚本

| 输入 | 产物 | 何时重跑 |
| --- | --- | --- |
| `images/images.qrc` | `images/images_rc.py` | **首次取得代码后必须执行**；资源变更后同样 |
| `src/ui/qgisapp.ui` | `src/ui/ui_qgisapp.py` | 修改主窗口 UI 后（有产物时优先加载，否则回退 `uic.loadUi`） |
| `src/ui/qgsrastercalcdialogbase.ui` | `src/ui/ui_qgsrastercalcdialogbase.py` | 同上 |
| 其余 48 个 `.ui`（含 `qgsmeasurebase`、`qgsstatisticalsummarybase`、注记/报表/网格/装饰/CAD/选项等） | 运行时 `uic.loadUi` | 无需编译，改完直接重启；若 `src/ui/` 里存在同名 `ui_*.py` 会被优先加载（该文件不入库） |

```powershell
.\scripts\build-resources.cmd
.\scripts\build-ui.cmd
```

**首次取得代码后必须先跑 `build-resources.cmd`**：`main.py` 启动时会 `from images import images_rc`，缺了它无法启动。
`build-ui.cmd` 用于重建两个预编译 UI（`images/images_rc.py`、`src/ui/ui_*.py` 都被 `.gitignore` 忽略）；缺失时 `qgisapp.py` 会回退到 `uic.loadUi`，因此它不影响能否启动。
`src/app/**/*.py` 是手写逻辑，不经过 pyuic/pyrcc；运行时引用的原生控件（浏览器、属性表、渲染器等）也不需要重新编译它们的 `.ui`。

---

## 3. 目录结构

```
qgis_python/
├─ run-qgis-python.cmd          启动器（GUI 与测试共用入口）
├─ LICENSE                      GPL-3.0（与上游 QGIS 一致）
├─ 功能移植清单.md              程序启动时自动重写的 action 状态台账（已入库）
├─ src/
│  ├─ app/                      对应原生 src/app/*.cpp：应用层，主要开发区（186 个模块）
│  │  ├─ main.py                入口，对应 src/app/main.cpp（时序见 §5.1）
│  │  ├─ qgisapp.py             主窗口控制器，对应 qgisapp.cpp/.h
│  │  ├─ qgisappinterface.py    对应 qgisappinterface.cpp（iface 契约、选项页工厂、action 工厂）
│  │  ├─ qgsproxystyle.py       对应 qgsproxystyle.cpp（QgsAppStyle，被 #ifndef SIP_RUN 排除出绑定）
│  │  ├─ ui_defaults.py         由 ui_defaults.h 转写的默认窗口布局
│  │  ├─ qgsnativepluginloader.py  用 ctypes 驱动无绑定的原生插件（拓扑规则引擎）
│  │  ├─ options/               选项对话框与各页面（对应 qgsoptions.cpp + 各 OptionsWidgetFactory）
│  │  ├─ decorations/  dwg/  elevation/  georeferencer/  labeling/  layout/
│  │  ├─ maptools/  mesh/  vertextool/  annotations/  locator/  offline_editing/  pluginmanager/
│  │  └─ qgswelcomepage.py 等   欢迎页/最近工程/模板/自绘代理（§5.4）
│  ├─ gui/                      对应原生 src/gui：**被绑定遗漏**的 gui 类在此用 Python 复刻（12 个）
│  │  ├─ qgsdockablewidgethelper.py   对应 qgsdockablewidgethelper.cpp（PyQGIS 未暴露）
│  │  └─ annotations/  maptools/      注记工具、形状工具基类等
│  └─ ui/                       50 个原版 .ui + 5 个预编译 ui_*.py
├─ python/                      随包发布的 Python 控制台副本（console/、plugins/）
├─ images/                      原版图标与启动图资源
├─ resources/                   customization.xml 等
├─ scripts/                     移植审计、同步与构建脚本（§7）
├─ tests/src/python/            27 个测试模块（**未入库**，见 §6.6）
├─ docs/                        生成的审计数据（**未入库**）
├─ output/                      运行/测试产物：报告 JSON、临时目录、截图（被忽略）
└─ .runtime/                    smoke 模式隔离设置与阶段日志（被忽略）
```

---

## 4. 移植方法论（硬规则）

1. **优先用 PyQGIS 绑定**。`qgis.core` / `qgis.gui` 里有的类直接实例化，不在 Python 里重写。
2. **没有绑定，就照 C++ 复刻**。类名、方法名、信号名、参数顺序与语义对齐原生；docstring 写明"对应 xxx.cpp 的 xxx()"。
3. **不写伪替身**。不允许用空壳类冒充原生行为；确实受后端限制（如 DWG 版本）必须在状态台账标 `partial` 并在 [§10](#10-已知差异与限制) 说明原因。
4. **注释引用原生位置**。新增/修复行为时给出原生函数名或 `文件:行`，例如：
   ```python
   # Native main.cpp style selection: qgis/style, fusion for non-default UI themes,
   # and the known-broken adwaita styles rejected outright.
   ```
   后来者据此可直接对照源码验证。
5. **无绑定时的四种手段**（按优先级）：

   | 手段 | 适用场景 | 实例 |
   | --- | --- | --- |
   | 用**更下层** API 重组原逻辑 | 高层 API 未绑定，但底层组件可用 | 嵌入图层：`QgsProject::createEmbeddedLayer()` 未绑定 → `QgsLayerDefinition.loadLayerDefinitionLayers()` + 源工程路径解析器复现步骤；网格拾取：`nativeMesh()/triangularMesh()` 未绑定 → 走可绑定接口 |
   | **ctypes 直调原生 DLL** | 逻辑在 C++ 库中且无 Python 出口 | 拓扑规则引擎：解析 `plugin_topology.dll` 导出表 + `classFactory` + `QgisPlugin` vtable（`qgisnativepluginloader.py`）；OpenCL 设备枚举（`options/qgsopenclutils.py` 直调 `OpenCL.dll`） |
   | **按 C++ 重写 Python 类** | 类整体未绑定，但依赖的 Qt/QGIS 组件都可用 | `QgsProjectListItemDelegate`、`QgsNewsItemListItemDelegate`、`QgsProjectPreviewImage`、`QgsRecentProjectItemsModel`、`QgsTemplateProjectsModel`、`QgsWelcomePage`、`QgsVersionInfo`、`QgsDockableWidgetHelper` |
   | **绕开无法配置的 C++ 单例** | C++ 类存在，但其静态钩子无法从 Python 设置 | Python 控制台宿主 `PythonConsoleDock`（`QgsDockableWidgetHelper::sAddTabifiedDockWidgetFunction` 是 `std::function` 静态成员，PyQt 无法赋值，故用端口自己的 helper 停靠） |

6. **就地修 bug，不掩盖**。测试暴露的崩溃按原生语义修，例：`QgsVectorLayer.addCurvedRing()` 只接受 `QgsCurve`，就把捕获到的面归一化成曲线；`sip.isdeleted()` 不能用于纯 Python 对象，就加 `isDeleted()` 判断包装类型。
7. **不留退路式标签**。禁止"部分实现（PyQGIS 绑定缺失）"这类逃避性状态；真做不了要写清具体限制与替代路径（当前该状态为空集）。

---

## 5. 关键子系统开发者指南

### 5.1 启动时序：main.py 与原生 main.cpp/qgisapp.cpp

改启动行为时**必须保持与原生相同的顺序**，否则会出现"设置不生效 / 面板不恢复"这类问题。

| 阶段 | 端口位置 | 原生对应 |
| --- | --- | --- |
| 参数解析、档案解析与切换 | `main.py`（`resolveProfile`） | `main.cpp` 参数块 + `QgsUserProfileManager` |
| 组织/应用名、profile 根目录 | `main.py` 前置块 | `main.cpp` 设置 `QCoreApplication` 名称 |
| 样式选择（`qgis/style`、非默认主题强制 fusion、adwaita 拒绝） | `main.py` 样式块 | `main.cpp:1440-1475` |
| 主题应用 `QgsApplication.setUITheme()` | `main.py` | `QgisApp::setTheme()` → `QgsApplication::setUITheme()` |
| 本地化（命令行 → 用户覆盖 → 系统 locale） | `main.py` locale 块 | `main.cpp` locale 块 |
| 启动画面（尺寸/遮罩/居中） | `main.py` splash 块 | `main.cpp:1483-1509`（上游已注释，语义保留） |
| 构造主窗口：分阶段 splash、欢迎页、最近工程、文件过滤器、图标尺寸… | `qgisapp.py::__init__` | `qgisapp.cpp` 构造函数 |
| `show()` → `completeInitialization()` → `fileOpenAfterLaunch()` | `main.py` 尾部 | `main.cpp:1787-1793` |
| 退出：保存窗口状态、卸载插件、`exitQgis()` | `qgisapp.py::saveWindowState/closeEvent/fileExit` | `QgisApp::saveWindowState/closeEvent/fileExit` |

启动项目分流由 `QgisApp.fileOpenAfterLaunch()` 实现，对应原生 `qgisapp.cpp:5913-6030`：

| `qgis/projOpenAtLaunch` | 行为 |
| --- | --- |
| `0` | 显示**欢迎页**（central `QStackedWidget` 第 1 页），并连接 `newProject`/`projectRead` → `showMapCanvas` |
| `1` | 打开最近工程列表首项 |
| `2` | 打开 `qgis/projOpenAtLaunchPath` |
| `3` | 新建空白工程（`qgis/newProjectDefault` 为真时用默认模板） |

失败保护：`qgis/projOpenedOKAtLaunch` 为假时提示一次 `Failed to open: …` 并把 `projOpenAtLaunch` 重置为 0，避免反复打开坏工程。
另注意：`projOpenAtLaunch` 默认 0，因此**默认启动落在欢迎页**；添加图层或打开工程会自动切回画布（`layersChanged → showMapCanvas`）。

### 5.2 主窗口控制器 qgisapp

按原生构造函数顺序展开：`createCanvas` / `createMenus` / `createStatusBar` / `createLayerTreeView` / `createDockWidgets` / `createMapTools` / `createActions` / `createToolBars`…

- `bind(name, handler, note=…)`：把动作对象名绑到 Python 处理器，并登记进 `mImplementedActions`（供状态台账统计）。
- `mDynamicActions`：非 `.ui` 声明的动作（运行时创建、插件扩展点、接口方法），登记 `handler`/`note`/`inInterface`。
- `coverage()`：汇总 `mActionInventory`（来自 `docs/upstream-actions.json`）与动态动作目录，产出状态数据。
- `writeCoverage()`：写 `docs/implementation-status.json` 并重写 `功能移植清单.md`。

加/改动作的标准流程：

```python
# 1) 在 createActions()（或对应 create*）里声明并绑定
self.bind('mActionFoo', self.foo, note='该动作做什么、对应原生哪个函数')
# 2) 运行时创建（不在 .ui 里）的动作登记到动态清单，工具栏/接口可见性会被核对
self.mDynamicActions['qgisapp:mActionFoo'] = dict(
    action=self.mActionFoo, handler='foo', note='…', inInterface=True)
# 3) 跑相关套件（§6），并确认 功能移植清单.md 的状态变化符合预期
```

### 5.3 选项对话框 `src/app/options/`

- `qgsoptions.py` 是主对话框：先应用绑定表（`qgsoptionsbindings.py` 的 `PLAIN_BINDINGS` / `COMBO_BINDINGS` / `COLOR_BINDINGS`），再初始化各页，最后 `saveOptions()` 统一落盘并 `applyToApplication()` 处理可即时生效项。
- 26 页中的"工厂页"来自插件注册：`QgisAppInterface.registerOptionsWidgetFactory()` 收集，`qgsoptions.py` 逐页构建（`app.mQgisInterface.mOptionsFactories`）。**新增页面优先走工厂方式**，原生插件自带页面会自动出现（Processing、渲染、高程、代码编辑器等就是这样接进来的）。
- 改这里之前必读的易错点：
  - **保存语义必须对齐原生**。`locale/overrideFlag` 曾漏写，导致"选了简体中文重启还是英文"；`UI/UITheme` 在 `qgsoptions.cpp:1497` 保存、`qgis/style` 在 `qgsoptions.cpp:1671` 保存，两者都要写。
  - **未选中的下拉框不要写 `max(0, findData(...))`**。原生是 `findData()` 直接赋值，未命中即 `-1`（未选中）；用 `max(0, …)` 会静默写入"第一项"，例如把 `locale/globalLocale` 写成 `C`。
  - 组合框取值写回设置前把 `None` 归一化成 `''`，避免落进无效 QVariant。
  - 需要重启的项在标签上注明"（需要重启 QGIS）"，与原生提示一致。
- 逐页构造与应用的排查脚本：`scripts/exercise_options.py`（定位崩溃页）。

### 5.4 最近工程、欢迎页、模板、自绘列表

| 端口文件 | 原生对应 | 说明 |
| --- | --- | --- |
| `qgsrecentprojectsitemsmodel.py` | `qgsrecentprojectsitemsmodel.cpp` | 模型与角色（Title/Path/NativePath/Crs/Pin/AnonymisedNativePath）、存在性检查（先项目存储后本地文件，结果缓存） |
| `qgsprojectlistitemdelegate.py` | `qgsprojectlistitemdelegate.cpp` | 两个自绘代理 + `QgsProjectPreviewImage`（缩略图圆角化） |
| `qgstemplateprojectsmodel.py` | `qgstemplateprojectsmodel.cpp` | 模板目录扫描、`preview.png` 解压读取、"New Empty Project" 占位项 |
| `qgswelcomepage.py` | `qgswelcomepage.cpp` | 三栏布局（最近工程 / 新闻 / 模板）、右键菜单（固定/取消固定/刷新/移除/清空）、版本横幅 |
| `qgsversioninfo.py` | `qgsversioninfo.cpp` | 版本检查（`https://version.qgis.org/version.txt`），类未绑定故用 `QgsNetworkAccessManager` 复刻 |

- 存储与原生同键：**`UI/recentProjects/N`**（`title/path/previewImage/crs/pin`），含 `UI/recentProjectsList` 旧键迁移、`maxRecentProjects`（默认 20）截断、固定项置顶且不参与截断、保存工程时生成 250×177 预览图（`createPreviewImage`）。
- 欢迎页在上游 3.34 被整体注释（`qgisapp.cpp:1089-1132`），但设置项与类都还在。端口把它实现出来，"启动时打开工程 = 欢迎页"才有意义。
- 点模板行的 "New Empty Project" 调用 `fileNewBlank()`：上游写的是 `QgisApp::instance()->newProject()`，而 `newProject` 是**信号**，那行在 C++ 里只是发射信号（上游死代码）；端口必须走真正的新建工程路径。

### 5.5 启动画面（分阶段消息）

原生 3.34 把 splash 构造与 `mSplash->showMessage(...)` 全注释掉了，但**文本与顺序保留**。端口按原生顺序显示 11 段：

```
Checking database → Reading settings → Setting up the GUI → Checking provider plugins →
Starting Python → Restoring loaded plugins → Updating recent project paths →
Initializing file filters → Restoring window state → Populate saved styles → QGIS Ready!
```

实现要点：`QgisApp.showSplashMessage()` 用 `self.tr(text)`（**QgisApp 上下文**，可被翻译），对齐方式与文字颜色对齐原生（`releaseName() == "Master"` 绿色，否则黑色），每次消息后 `processEvents()` 让它逐段绘出；尺寸/遮罩/居中同原生（600×300 等比 + `setMask`）；`qgis/hideSplash` 与 `-n/--nologo` 均生效；smoke 模式跳过 splash。

### 5.6 本地化

- **加载机制**：`QgsApplication.setTranslation(code)` 内部安装 `qgis_<code>.qm` 与 `qt_<code>.qm`，**精确匹配代码**。系统 locale 是 `zh_CN` 时匹配不到已安装的 `qgis_zh-Hans.qm`，所以必须在选项里显式选语言并勾选覆盖系统语言环境（`locale/overrideFlag`）。
- 语言下拉框由 `QgsOptions.installedTranslations()` 枚举 `QgsApplication.i18nPath()` 下的 `qgis*.qm` 生成；**选中语言会自动勾选覆盖开关**（否则选择不会生效）。
- **不使用国旗图标**：语言代码不等于国家，给 `zh-Hant` 之类挂地区旗帜会带出政治主张，因此列表只显示语言自身的名称。
- 代码文本约定：
  - 原生字符串（能在 `qgis_zh-Hans.ts` 精确匹配到的）一律 `QCoreApplication.translate('<原生上下文>', '<原生英文源串>')`，已按此改写 249 处；验收方式是在 zh-Hans 下逐条断言"翻译结果 == 改写前的中文字面量"（当前 249/249 一致）。
  - 上下文必须与原生 `tr()` 所在类一致：`.ui` 文本是 `<页面类名>Base`（uic 生成），代码里 `self.tr()` 用当前类名。写错上下文会出现"翻译装了但界面不变"。
  - 端口自创、翻译目录里没有的文案保留中文（改成 `tr()` 反而会在中文界面显示英文）。

### 5.7 主题、样式与图标尺寸

- `QgsApplication.setUITheme(theme)` 是完整主题实现（`style.qss` + `variables.qss` 变量替换 + `palette.txt` + 图标主题），经 `qApp->setStyleSheet` 应用，**必须调用**，否则主题设置毫无效果。
- 原生规则：`UI/UITheme` 非 `default` 时强制 `fusion`；adwaita 样式一律拒绝。端口在 `main.py` 按同样规则选样式，并经 `QgsAppStyle` 代理安装（原生该类被排除出绑定，见 `src/app/qgsproxystyle.py`）。
- 图标尺寸：`QGIS_ICON_SIZE = 24`（非 macOS）；`QgisApp.setIconSizes(size)` 给工具栏 `size`、面板工具栏 `panelIconSize(size)`（16；`>32` 时 `size-16`；`==32` 时 24）。

### 5.8 面板与窗口状态持久化

- 布局在**首次 show** 时恢复（Qt `QTBUG-89034`，原生同样把 `restoreState()` 挪到 `showEvent`），退出时经 `aboutToQuit → saveWindowState()` 写 `UI/state`、`UI/geometry`；无保存时用 `src/app/ui_defaults.py` 的默认布局兜底。
- **延迟创建的 dock 无法被 `restoreState()` 恢复**（恢复时对象还不存在）。Python 控制台正是这种情况，且其 C++ 基类依赖无法从 PyQt 设置的静态钩子。做法：
  - `src/app/qgspythonconsole.py` 用端口自己的 `QgsDockableWidgetHelper` 完成停靠，保留控制台要求的契约 `dockToggleButton()/isUserVisible()/setUserVisible()/activate()`（控制台工具栏会调用 `parent.dockToggleButton()`）；
  - 用 `UI/pythonConsoleVisible` 记录可见性，并在 `showEvent()` 中**先重建控制台再 `restoreState()`**，让停靠区域/几何由 `UI/state` 恢复；
  - `visibilityChanged` 接到菜单项勾选状态（原生 `console.py:65` 同款），避免"控制台开着但菜单未勾选"。
- 改这块的注意点：`QgsDockableWidgetHelper.toggleDockMode()` 的原生语义是"新建 dock 后 `setUserVisible(true)`"，不要按"上一个宿主是否可见"推断，否则首次创建恒隐藏（历史 bug）。
- Qt 只保存**有 `objectName`** 的 dock；若发现某个普通面板不恢复，先查它的 `objectName`。

### 5.9 无 PyQGIS 绑定的实例清单

| 缺失的绑定 | 端口做法 | 文件 |
| --- | --- | --- |
| `QgsProject::createEmbeddedLayer()` | `QgsLayerDefinition.loadLayerDefinitionLayers()` + 源工程路径解析复现 | `qgisapp.py` |
| `QgsMeshLayer::nativeMesh()/triangularMesh()` | 走可绑定接口完成拾取/编辑 | `mesh/` |
| `QgsDockableWidgetHelper` | 按 C++ 复刻 Python 版 | `src/gui/qgsdockablewidgethelper.py` |
| `QgsVersionInfo` | 用 `QgsNetworkAccessManager` 复刻协议 | `qgsversioninfo.py` |
| `QgsProjectListItemDelegate` / 最近工程模型 / 模板模型 / 欢迎页 | 按 C++ 复刻 | [§5.4](#54-最近工程欢迎页模板自绘列表) |
| `QgsLoadRasterAttributeTableDialog` / `QgsCreateRasterAttributeTableDialog` | 按原生逻辑重建 | `qgsrasterattributetableapputils.py` |
| `QgsAppStyle`（被 `#ifndef SIP_RUN` 排除） | 仿写代理样式 | `qgsproxystyle.py` |
| `QgsGui::nativePlatformInterface()` | 用 `QDesktopServices` 等价实现 | `qgswelcomepage.py` |
| 拓扑规则引擎 | ctypes 加载 `plugin_topology.dll` | `qgsnativepluginloader.py` |
| OpenCL 设备枚举 | ctypes 调 `OpenCL.dll` | `options/qgsopenclutils.py` |

---

## 6. 测试体系

### 6.1 设计

测试不是 pytest 用例，而是**挂在应用启动流程里的套件函数**：每个模块暴露 `run(app)`（部分为 `runReport(app)`），由 `main.py` 在窗口构造完成后调用。因此每条断言都在真实主窗口、真实画布、真实 `QgsSettings` 下执行，能覆盖"只有经 `main.py` 才会出现"的问题（选项窗口打不开、启动画面缺段、控制台不恢复等）。

### 6.2 运行

**一个套件 = 一次进程调用**：`main.py` 内部是 `elif` 链，同一次调用只执行第一个命中的标志。

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\run-qgis-python.cmd --smoke-test          # 默认套件（聚合 widgets/actions 检查）
.\run-qgis-python.cmd --startup-test        # 启动契约：分阶段 splash、欢迎页、projOpenAtLaunch、最近工程、控制台
.\run-qgis-python.cmd --georeferencer-test
```

全量回归（20 套，本项目交付前的验证矩阵）：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$flags = @('--smoke-test','--startup-test','--profile-test','--layertree-test','--data-actions-test',
           '--mesh-edit-test','--mesh-calculator-test','--georeferencer-test','--remaining-actions-test',
           '--dwg-import-test','--statusbar-test','--customization-test','--trim-extend-test',
           '--partial-actions-test','--annotation-test','--labeling-test','--shape-test',
           '--view-actions-test','--decoration-test','--toolbar-test')
$fail = @()
foreach ($f in $flags) {
  & .\run-qgis-python.cmd $f | Out-Null
  if ($LASTEXITCODE -ne 0) { $fail += $f; "FAILED: $f" }
}
"ran $($flags.Count) suites; failures: $($fail.Count)"
```

### 6.3 结果与判定

- 报告写到 `output/<name>-test.json`（`smoke-test.json`、`startup-test.json`、`georeferencer-test.json`…）。
- 报告含 `checks`（人可读检查项）与 `runtimeErrors`：`main.py` 用 `sys.excepthook` 把**任何**未处理异常记进 `window.runtimeErrors`，非空即判该套件失败。所以"套件通过"等价于"运行期没有异常"。
- 失败时退出码非 0，并在 stderr 给出断言位置。

### 6.4 隔离与环境

- smoke 模式（`--smoke-test` 或任何 `--xxx-test`）会把 `QSettings` 用户路径重定向到 `.runtime/smoke-settings` 并跳过 splash。套件不应污染真实 profile；若自己写了设置，请在结束时恢复（先例：`test_qgisapp_georeferencer.py` 恢复最近工程列表，`test_qgisapp_startup.py` 清除 `UI/pythonConsoleVisible`）。
- 无头运行必须 `QT_QPA_PLATFORM=offscreen`。离屏下字体/布局噪声多（`QFontDatabase`、`propagateSizeHints`、`QMimeDatabase` 警告属正常），涉及文本渲染的断言不要依赖离屏字体度量。
- 时序敏感：涉及画布几何、工具栏布局、鼠标事件的断言要留 `processEvents()`，或把瞄准点从角点向内偏移（`test_qgisapp_partialactions.py` 就是这么处理节点拾取的）。
- 打开 Python 控制台会把 `sys.stdout` 重定向进控制台部件（原生行为），需要真实 `fileno()` 的调用（如 `faulthandler.enable()`）会失败；调试脚本请写文件而非 `print`。

### 6.5 新增套件

1. 在 `tests/src/python/` 新建 `test_qgisapp_xxx.py`，实现 `def run(app)` 并 `return dict(checks=[...])`（或 `runReport`）。
2. 在 `main.py` 参数表加 `--xxx-test`，并在 `elif` 链中加 `from tests.src.python.test_qgisapp_xxx import run`。
3. 在 `reportName` 逻辑里补齐该套件的 JSON 文件名（否则会落到默认名）。
4. 单独跑一次，再把它加进全量回归列表。

### 6.6 注意：`tests/` 与 `docs/` 未入库

`.gitignore` 排除了 `tests/`、`docs/`、`output/`、`.runtime/`、`images/images_rc.py`、`src/ui/ui_*.py`。也就是：

- 克隆仓库后**没有测试套件与审计数据**，需自行保留/生成（按 §6.5 的约定编写即可被 `main.py` 调度）；
- `docs/*.json` 由 [§7](#7-状态文档与脚本) 的脚本生成，`功能移植清单.md` 由程序启动时生成，**都不要手工编辑**。

---

## 7. 状态文档与脚本

| 文件 | 生成者 | 用途 | 何时重跑 |
| --- | --- | --- | --- |
| `功能移植清单.md` | 程序启动时 `QgisApp.writeCoverage()` | 面向人的 action 状态表（中文标签） | 每次启动自动更新，**已入库** |
| `docs/implementation-status.json` | 同上 | 机器可读状态（`status`/`handler`/`note`/`implementationState`） | 同上 |
| `docs/upstream-actions.json` | `scripts/sync_upstream.py` | 从原版 `qgisapp.ui` + `qgisapp.cpp` 提取的 222 条 action 与槽映射，GPS/3D 标为排除 | 上游 UI/源码更新时 |
| `docs/upstream-toolbar-actions.json` | `scripts/sync_toolbar_actions.py` | 运行时创建的动态 action 目录（工具栏/接口扩展点） | 上游更新时 |
| `docs/upstream-icons.json` | `scripts/sync_resources.py` | 图标清单（核对主题图标是否齐备） | 资源更新时 |
| `docs/action-source-audit.json` | `scripts/audit_upstream_actions.py` | 逐条 action 的源码级审计证据 | 需要复核时 |
| `docs/options-status.json` | 构造选项对话框时由 `src/app/options/qgsoptions.py` 写出 | 控件接线清单（`implementedControls`/`unportedControls`/页数） | 每次构造选项对话框时更新 |
| `scripts/sync_options.py` | — | 从上游导入选项表单与字面量绑定，**重写 `src/app/options/qgsoptionsbindings.py`** | 上游选项表单变化时 |
| `scripts/audit_options.py` | — | 逐页打印控件接线与未接线项（仅 stdout），定位接线缺口 | 排查选项接线时 |
| `scripts/audit_toolbars.py` | — | 对照 `.ui` 复查运行时工具栏排列 | 改工具栏时 |
| `scripts/exercise_options.py` | — | 逐页构造并应用选项对话框，定位崩溃页 | 改选项时 |
| `scripts/update_porting_status.py` | 被程序与人工共用 | 状态标签与清单渲染（`PARTIAL_ACTIONS`、`ui-placeholder` 判定在此） | 状态口径变化时 |

生成/重跑（先设置源码树路径）：

```powershell
$env:QGIS_SOURCE_ROOT = 'C:\Users\worker306\Desktop\QGIS-final-3_34_10'
python scripts/sync_upstream.py
python scripts/sync_toolbar_actions.py
python scripts/update_porting_status.py
```

状态枚举（`implementationState` → 清单标签）：

| 状态 | 标签 | 含义 |
| --- | --- | --- |
| `implemented` | 已接入 | 已实现且有运行时套件覆盖 |
| `partial` | 部分实现 | 已实现但受后端能力限制（当前仅 DWG 导入） |
| `ui-placeholder` | 已接入（隐藏插入锚点） | `.ui` 里的分隔符占位对象，无行为 |
| `excluded-gps` | 排除（范围外：GPS/3D） | 按项目决定不做 |
| `not-ported` | 未实现 | 当前为 0 |
| `blocked-bindings` | 部分实现（PyQGIS 绑定缺失） | 保留状态位；当前为空集，历史条目均已用更下层 API 完成 |

---

## 8. 代码规范与评审红线

**风格**

- 与原生同名同序：方法用 `camelCase`（QGIS 习惯，不要改成 PEP8 风格）。
- 大量使用紧凑单行（`if x: return y`）贴近 C++ 原版密度；逻辑复杂时才展开。
- 面向用户的文案：原生字符串走 `translate()`，端口自创文案用中文。
- 新模块开头一句 docstring，写明"对应原生哪个文件"。

**红线**

1. **不得引入回归**：改动后必须跑完全量 20 套（[§6.2](#62-运行)）。
2. **不得用伪实现充数**：做不了就写清限制。
3. **不得静默写错设置**：写 `QgsSettings` 前核对键名、默认值与原生一致（`locale/*`、`UI/*`、`qgis/*` 是历史事故高发区）。
4. **不新增第三方依赖**：只用 OSGeo4W 自带的 Python/PyQt/QGIS。
5. **不提交运行时产物**：`output/`、`.runtime/`、`images/images_rc.py`、`src/ui/ui_*.py` 已在忽略列表；临时调试脚本用完删除。
6. **改 `.ui` 后重编译**（`scripts/build-ui.cmd`），并确认 `uic.loadUi` 回退路径同样可用。
7. **判空用 `isDeleted()`**：`sip.isdeleted()` 只接受被包装的 C++ 对象，对纯 Python 协作对象会抛 `TypeError`（见 `qgisapp.py` 顶部 `isDeleted()`）。
8. **不要在 `elif` 链测试调度之外新造入口**：新套件按 [§6.5](#65-新增套件) 接入，保持"一个标志一个套件"。

---

## 9. 故障排查 FAQ

**启动时报 `Problem with OTB installation: OTB folder is not set.`（CRITICAL）**
这是 QGIS 自带 **OTB Provider 插件**的日志（`otbprovider/OtbAlgorithmProvider.py:126`）：Processing 启动时无条件注册该 provider，它发现 Processing 里没有 OTB 目录（`OTB_FOLDER`）就记一条 CRITICAL 并跳过加载。本机未安装 OTB（`C:\OSGeo4W\apps` 下无 OTB，也没有 `otbApplicationLauncher*.exe`），所以这是**预期结果**，只意味着没有 OTB 那批遥感算法；原生 QGIS 3.34.10 在同样未配置时也打印同一行。要用就装 OTB，并在 **设置 → 选项 → 处理 → 提供者 → OTB → OTB 文件夹** 指定路径（键 `Processing/Configuration/OTB_FOLDER`）；配置正确后日志变成 `Loading OTB 'x.y.z'.`。

**离屏运行刷屏 `QFontDatabase: Cannot find font directory …`**
offscreen 平台没有字体目录，属正常噪声；不要基于离屏字体度量做断言。

**启动画面不显示 / 只出现一次**
检查 `qgis/hideSplash`、是否传了 `-n/--nologo`、以及是否处于 smoke 模式（smoke 主动跳过 splash）。

**"选项窗口打不开"**
历史事故：`QgisApp` 未调用 `QgsUserProfileManager.setActiveUserProfile()`，`userProfile()` 为 `None`，用户配置页构造时崩溃。改 profile 相关代码后请跑 `--profile-test` 与 `--startup-test`。

**改了设置重启后不生效**
先确认该键**是否真的被保存**（多数历史事故是"只读没写"），再确认启动路径是否读取它（[§5.1](#51-启动时序mainpy-与原生-maincppqgisappcpp) 顺序表）。语言类问题另见 [§5.6](#56-本地化)：必须同时有 `locale/userLocale` 与 `locale/overrideFlag`。

**面板（尤其 Python 控制台）重启后消失**
见 [§5.8](#58-面板与窗口状态持久化)：延迟创建的 dock 需要"记录可见性 + 在 `restoreState()` 之前重建"。普通面板（图层/浏览器/消息日志等）由 `UI/state` 正常恢复；若某个普通面板也不恢复，先查它的 `objectName` 是否为空。

**调试时 stdout 突然不见了**
打开 Python 控制台会把 `sys.stdout` 重定向到控制台部件（原生行为），此时 `faulthandler.enable()` 之类会失败；调试脚本写文件而不是 `print`。

**`--xxx-test` 跑了别的套件**
`main.py` 是 `elif` 链：一次调用只跑第一个命中的标志，请一次只传一个。

---

## 10. 已知差异与限制

| 项 | 现状 | 原因 / 改进方向 |
| --- | --- | --- |
| DWG 导入（`mActionDwgImport`） | 状态 `partial` | 依赖 GDAL CAD 驱动（libopencad），仅支持 R2000 及更早版本，块插入模式不可用；DXF 已支持真实曲线（ARC/CIRCLE/bulge）与 ASCII/二进制图层状态。改进需更换 CAD 后端 |
| 3D 地图视图、GPS/GPX 入口 | 排除（4 条 action） | 按项目范围决定；`scripts/sync_upstream.py` 的 `OUT_OF_SCOPE_ACTIONS` 记录该决定，重新生成清单不会把它们算成待办 |
| 中文界面下 Qt 标准按钮（OK/Cancel）仍为英文 | 与原生一致 | 原生按精确代码加载 `qt_<code>.qm`，而 `qt_zh-Hans.qm` 不存在（只有 `qt_zh_CN.qm`）；端口沿用原生行为，不额外改加载策略 |
| 欢迎页自绘项 | 高度接近原生，非逐像素 | 自绘代理按 C++ 复刻；`QgsScopedQPainterState` 未绑定，用 `save()/restore()` 等价替换 |
| 端口自创文案 | 保持中文 | 改成 `tr()` 会在中文界面显示英文；若要英文界面，应把这些文案的英文源串补进翻译目录 |
| `QgsGui::nativePlatformInterface()` | 用 `QDesktopServices` 等价实现 | 该单例未绑定；"打开所在目录"等行为等价但非系统原生 API |
| `tests/`、`docs/` 不入库 | 见 [§6.6](#66-注意tests-与-docs-未入库) | 若希望他人开箱即跑测试，需要调整 `.gitignore` 并把套件与审计数据入库 |
| Processing 提供者可执行性 | 取决于环境 | 例如 GRASS/OTB 需要各自安装与配置（见 FAQ）；端口负责注册与选项页，执行能力由 OSGeo4W 组件决定 |

---

## 11. 贡献流程

1. **定位原生实现**：在 3.34.10 源码树找到对应 `*.cpp/*.h`（应用层 `src/app`，界面组件 `src/gui`），读清调用顺序与设置键。
2. **判断绑定可用性**：用 `python-qgis-ltr.bat` 对目标类做 `dir()`；不可用则按 [§4.5](#4-移植方法论硬规则) 选择手段。
3. **实现**：文件名/类名/方法名对齐原生，注释标注原生位置。
4. **自测**：先跑相关套件，再跑全量 20 套（[§6.2](#62-运行)）；必要时按 [§6.5](#65-新增套件) 增补断言——优先加进 `--startup-test` 或对应子系统套件，而不是新造套件。
5. **视觉验证（涉及界面时）**：用真桌面平台（不设 `QT_QPA_PLATFORM`）经 `run-qgis-python.cmd` 启动并截图核对；离屏截图无字体、不可信。
6. **更新状态**：确认 `功能移植清单.md` 的状态变化符合预期（**不要手工编辑**）。
7. **清理与提交**：删除临时脚本与临时配置目录；提交信息写清"做了什么 + 对应原生位置"，一个主题一个提交。

提交信息前缀沿用仓库现状：`修复…`、`实现…`、`本地化：…`。

---

## 12. 参考

**原生源码（3.34.10）关键文件**

| 主题 | 文件 |
| --- | --- |
| 启动时序、样式/locale/参数 | `src/app/main.cpp` |
| 主窗口、动作、设置、最近工程、启动分流 | `src/app/qgisapp.cpp` / `qgisapp.h` |
| 选项对话框 | `src/app/options/qgsoptions.cpp` |
| 欢迎页/最近工程/列表代理/模板 | `src/app/qgswelcomepage.cpp`、`qgsrecentprojectsitemsmodel.cpp`、`qgsprojectlistitemdelegate.cpp`、`qgstemplateprojectsmodel.cpp` |
| 版本检查 | `src/app/qgsversioninfo.cpp` |
| 停靠/浮动契约 | `src/gui/qgsdockablewidgethelper.cpp` |
| 控制台 | `python/console/console.py`（随包副本在 `python/console/`） |
| Processing 提供者注册 | `python/plugins/processing/Processing.py` |
| OTB 提供者 | `python/plugins/otbprovider/OtbAlgorithmProvider.py` |

**外部参考**

- PyQGIS API：<https://qgis.org/pyqgis/3.34/>
- QGIS 源码：<https://github.com/qgis/QGIS/tree/final-3_34_10>
- Qt 5.15（`QMainWindow::saveState/restoreState`、`QDockWidget`）：<https://doc.qt.io/qt-5/>

**仓库内入口速查**

| 我想… | 看这里 |
| --- | --- |
| 改启动流程 | `src/app/main.py` + [§5.1](#51-启动时序mainpy-与原生-maincppqgisappcpp) |
| 加/改一个 action | `qgisapp.py::createActions` + [§5.2](#52-主窗口控制器-qgisapp) |
| 改选项页 | `src/app/options/qgsoptions.py` + [§5.3](#53-选项对话框-srcappoptions) |
| 改欢迎页/最近工程 | `qgswelcomepage.py` 等 + [§5.4](#54-最近工程欢迎页模板自绘列表) |
| 改启动画面 | `main.py` splash 块 + `QgisApp.showSplashMessage` |
| 改翻译/语言列表 | `qgsoptions.py::installedTranslations` + [§5.6](#56-本地化) |
| 加测试 | `tests/src/python/` + `main.py` 的 `elif` 链 + [§6.5](#65-新增套件) |
| 看当前完成度 | `功能移植清单.md`、`docs/implementation-status.json` |
| 排查崩溃页 | `scripts/exercise_options.py`、`window.runtimeErrors` |

---

## 附录 A：功能与验收矩阵

各子系统的入口、对应套件与报告文件。所有套件当前全部通过（20/20）。

| 子系统 | 主要入口 | 检查标志 → 报告 |
| --- | --- | --- |
| 主窗口/动作总览（含属性表、控制台停靠、测量、选择、统计摘要、顶点编辑器、地图主题、图例过滤、地图提示） | 菜单与各工具栏 | `--smoke-test` → `output/smoke-test.json` |
| 启动契约（分阶段 splash、欢迎页、`projOpenAtLaunch` 四态、最近工程存储、控制台停靠） | 启动过程 | `--startup-test` → `output/startup-test.json` |
| 配置档案（解析、询问策略、`--profile`/`-S`、退出写回 `lastProfile`） | 设置 → 用户配置 | `--profile-test` → `output/profile-test.json` |
| 界面自定义（六类配置树、搜索、捕获 `Ctrl+M`、INI 导入导出、应用/重置/取消） | 设置 → 界面自定义 | `--customization-test` → `output/customization-test.json` |
| 状态栏（坐标/范围、比例尺与锁定、放大镜、旋转、渲染进度、CRS 与日志按钮） | 状态栏 | `--statusbar-test` → `output/statusbar-test.json` |
| 图层树右键（更改/修复数据源、可见比例尺缩放、栅格属性表、组 WMS 数据） | 图层面板右键 | `--layertree-test` → `output/layertree-test.json` |
| 数字化与 CAD（移动/复制、分割、重塑、增删环、部件） | 高级数字化工具栏 | `--smoke-test` |
| 修剪/延伸要素（线段捕捉、两侧修剪/延伸、Z/M、多部件、跨 CRS、拓扑节点、撤销） | 高级数字化工具栏 | `--trim-extend-test` → `output/trim-extend-test.json` |
| 形状数字化（5 圆/4 椭圆/4 矩形/3 正多边形/半径圆弧，共 17 项） | 形状工具栏 | `--shape-test` → `output/shape-test.json` |
| 填充环、添加环、添加部件与形状共用捕获 | 高级数字化工具栏 | `--shape-test`、`--smoke-test` |
| 测量（距离/面积/角度/方位角，单位切换、椭球/平面、撤销） | 属性工具栏测量下拉 | `--smoke-test` |
| 选择（矩形/多边形/自由手绘/半径，Shift/Ctrl 修饰语义） | 选择工具栏 | `--smoke-test` |
| 统计摘要（字段/表达式、仅选中要素、后台可取消） | 视图菜单 / 属性工具栏 | `--smoke-test` |
| 顶点编辑器（X/Y/Z/M 表格、双击修改、撤销、定位） | 顶点工具下拉 / 面板菜单 | `--smoke-test` |
| 装饰：网格、布局范围、比例尺、图片、标题、版权、指北针 | 视图 → 装饰 | `--decoration-test` → `output/decoration-test.json` |
| 注记：旧式（文本/SVG/HTML/表单）、新式注记图层、修改注记工具 | 注记工具栏 | `--annotation-test`、`--partial-actions-test` |
| 报表（章节树、字段分组、页眉/页脚、PDF 导出、工程保存） | 工程 → 新建报表 | `--partial-actions-test` → `output/partial-actions-test.json` |
| 标注工具栏九个动作、修改标注、高亮固定标注、显示未放置标注 | 标注工具栏 | `--labeling-test` → `output/labeling-test.json` |
| 高程剖面（图层树、剖面绘制/拾取、测量、X 轴缩放、单位、图片/PDF 导出） | 视图 → 高程剖面 | `--view-actions-test` → `output/view-actions-test.json` |
| 网格编辑（三角化、翻转/合并边、新面预览、Z 修改、删除快捷键、撤销、坐标变换） | 网格工具栏 | `--mesh-edit-test` → `output/mesh-edit-test.json` |
| 网格计算器、新建网格图层 | 网格菜单 | `--mesh-calculator-test` → `output/mesh-calculator-test.json` |
| DWG/DXF 导入（图层选择、分组/合并、三种块模式、样式与标注映射） | 图层 → 导入 CAD | `--dwg-import-test` → `output/dwg-import-test.json` |
| 数据类动作（DXF 导出、新建 SpatiaLite 图层、粘贴为新图层、要素动作、嵌入图层） | 工程/编辑菜单 | `--data-actions-test` → `output/data-actions-test.json` |
| 形状捕获与网格批处理补充 | — | `--remaining-actions-test` → `output/remaining-actions-test.json` |
| 工具栏运行时排列与动态按钮（注记创建、文字属性、Web 扩展接口） | 各工具栏 | `--toolbar-test` → `output/toolbar-test.json` |
| 地理配准（24 个 Action、GCP、变换、栅格/矢量输出、GDAL 脚本） | 栅格 → 地理配准 | `--georeferencer-test` → `output/georeferencer-test.json` |
| 自定义投影（原生 CRS 编辑表单、批量删除、取消不写入） | 设置 → 自定义投影 | `tests/src/python/test_qgisapp_customprojection.py` → `output/custom-projection-test.json` |
| 剖面图层树与网格顶点移动 | — | `tests/src/python/test_qgisapp_profilemesh.py` → `output/profile-mesh-test.json` |
| 选项对话框（26 页：常规/系统/用户配置/CRS/变换/数据源/GDAL/渲染/栅格/矢量/画布/地图工具/数字化/高程/颜色/字体/布局/变量/认证/网络/定位器/加速/代码编辑器/控制台/高级/处理） | 设置 → 选项 | `--smoke-test`（页面构造）、`scripts/exercise_options.py`（逐页构造） |
| 本地化（语言列表、覆盖开关、249 条原生字符串翻译） | 设置 → 选项 → 常规 → 本地化语言环境 | `--startup-test`（含翻译解析断言） |
| 主题与样式（`UI/UITheme`、`qgis/style`、fusion 规则、图标尺寸） | 设置 → 选项 → 常规 → 应用程序 | `--startup-test`、`--toolbar-test` |

> 说明：
> 1. 除最后两行外，表中各行均由 [§6.2](#62-运行) 的 20 个 CLI 套件覆盖，全部通过；最后两行（自定义投影、剖面树/网格移动）是**直接运行**的检查模块（`python-qgis-ltr.bat tests/src/python/xxx.py`），不在这 20 个标志里，同样已验证通过（exit 0、`errors: []`）。
> 2. 矩阵只说明"该功能由哪个套件覆盖"。套件通过表示该批行为在当前环境验证通过，**不代表**所有真实数据格式都已验收——第三方插件、服务器连接、各类数据格式仍需用实际数据验证。
