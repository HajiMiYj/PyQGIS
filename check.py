"""内置检查的运行器（开发工具，与运行应用无关）。

用法（在仓库根目录，用 OSGeo4W 解释器）：

    python-qgis-ltr.bat check.py --check             # 默认套件
    python-qgis-ltr.bat check.py --startup-test      # 单项
    python-qgis-ltr.bat check.py --help              # 全部标志

每项检查都复用 main.py 的原生启动顺序构造真实的 QgisApp，再调用
tests/src/python/ 下对应模块的 run()/runReport()，把报告写到 output/<标志名>.json
（默认套件为 output/check.json），并保存一张窗口截图。任一未处理异常都会让
该检查失败并把报告里的 runtimeErrors 置为非空。
"""
import argparse
import json
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
import sys
import traceback

from PyQt5.QtCore import QTimer

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from main import runApplication  # noqa: E402

# (命令行标志, 模块名, 入口函数)。报告文件名由标志推导：--startup-test -> startup-test.json
CHECKS = (
    ('--statusbar-test', 'test_qgisapp_statusbar', 'run'),
    ('--layertree-test', 'test_qgisapp_layertree', 'run'),
    ('--startup-test', 'test_qgisapp_startup', 'run'),
    ('--profile-test', 'test_qgisapp_profile', 'run'),
    ('--georeferencer-test', 'test_qgisapp_georeferencer', 'run'),
    ('--dwg-import-test', 'test_qgisapp_dwgimport', 'run'),
    ('--mesh-edit-test', 'test_qgisapp_meshediting', 'run'),
    ('--mesh-calculator-test', 'test_qgisapp_meshcalculator', 'run'),
    ('--customization-test', 'test_qgscustomization', 'run'),
    ('--trim-extend-test', 'test_qgisapp_trimextendfeature', 'run'),
    ('--partial-actions-test', 'test_qgisapp_partialactions', 'run'),
    ('--decoration-test', 'test_qgisapp_decorations', 'run'),
    ('--view-actions-test', 'test_qgisapp_viewactions', 'run'),
    ('--remaining-actions-test', 'test_qgisapp_remainingactions', 'run'),
    ('--shape-test', 'test_qgisapp_shapes', 'run'),
    ('--toolbar-test', 'test_qgisapp_toolbars', 'run'),
    ('--data-actions-test', 'test_qgisapp_dataactions', 'run'),
    ('--annotation-test', 'test_qgisapp_annotations', 'run'),
    ('--labeling-test', 'test_qgisapp_labeling', 'runReport'),
)
DEFAULT_CHECK = ('test_qgisapp', 'run')
MISSING_MODULES = (
    '未找到检查模块 {name}。\n'
    'tests/ 与 docs/ 不随仓库提供（见 README §7.6），请在带有 tests/ 的工作副本上运行检查。'
)


def parseArguments(argv=None):
    parser = argparse.ArgumentParser(description='运行本项目的内置检查。')
    parser.add_argument('--check', action='store_true', help='运行默认套件（不指定其它标志时同样运行它）')
    for flag, _, _ in CHECKS:
        parser.add_argument(flag, action='store_true')
    return parser.parse_args(argv)


def selectedCheck(args):
    """返回 (报告文件名, 模块名, 入口函数)；一次只运行第一个命中的标志。"""
    for flag, module, entry in CHECKS:
        if getattr(args, flag[2:].replace('-', '_')):
            return flag[2:] + '.json', module, entry
    return 'check.json', DEFAULT_CHECK[0], DEFAULT_CHECK[1]


def resolveCheck(module, entry):
    """在构造应用之前确认检查模块存在，避免白启动一次窗口。"""
    name = 'tests.src.python.' + module
    try:
        available = find_spec(name) is not None
    except ModuleNotFoundError:
        available = False
    if not available:
        raise SystemExit(MISSING_MODULES.format(name=name))
    return getattr(import_module(name), entry)


def runCheck(check, reportName, window):
    report = check(window)
    report['runtimeErrors'] = window.runtimeErrors
    if window.runtimeErrors:
        raise AssertionError(window.runtimeErrors)
    out = ROOT / 'output'
    out.mkdir(exist_ok=True)
    (out / reportName).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    window.grab().save(str(out / 'qgis-python.png'))


def main(argv=None):
    args = parseArguments(argv)
    reportName, module, entry = selectedCheck(args)
    check = resolveCheck(module, entry)

    def onReady(app, window, context):
        def run():
            try:
                runCheck(check, reportName, window)
                window.prepareToQuit()
                app.exit(0)
            except Exception:
                traceback.print_exc(file=sys.__stderr__)
                app.exit(1)

        # Give the window a moment to lay out before a check starts driving it.
        QTimer.singleShot(1200, run)

    return runApplication(argv=[], checkMode=True, onReady=onReady)


if __name__ == '__main__':
    sys.exit(main())
