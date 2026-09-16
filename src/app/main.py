"""Python counterpart of src/app/main.cpp. Requires OSGeo4W QGIS 3.34.10."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

from PyQt5.QtGui import QIcon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('project', nargs='?')
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--labeling-test', action='store_true', help='Run only the label-toolbar integration checks')
    parser.add_argument('--annotation-test', action='store_true', help='Run annotation and embedded-group integration checks')
    parser.add_argument('--data-actions-test', action='store_true', help='Run DXF, SpatiaLite and mesh action integration checks')
    parser.add_argument('--toolbar-test', action='store_true', help='Run dynamic toolbar integration checks')
    parser.add_argument('--shape-test', action='store_true', help='Run shape digitizing integration checks')
    parser.add_argument('--remaining-actions-test', action='store_true', help='Run shape completion and mesh editing batch checks')
    parser.add_argument('--view-actions-test', action='store_true', help='Run report, elevation profile and version parser checks')
    parser.add_argument('--decoration-test', action='store_true', help='Run decoration actions, rendering and project roundtrip checks')
    parser.add_argument('--trim-extend-test', action='store_true', help='Run trim/extend snapping, geometry and undo checks')
    parser.add_argument('--customization-test', action='store_true', help='Run customization draft, INI, capture and startup checks')
    parser.add_argument('--mesh-edit-test', action='store_true', help='Run mesh triangulation, edge, face preview and keyboard checks')
    parser.add_argument('--dwg-import-test', action='store_true', help='Run CAD import, preview, grouping and cancellation checks')
    parser.add_argument('--georeferencer-test', action='store_true', help='Run georeferencer actions, GCP IO, raster and vector output checks')
    parser.add_argument('--statusbar-test', action='store_true', help='Run native status bar layout and interaction checks')
    parser.add_argument('--partial-actions-test', action='store_true', help='Run focused annotation editing and report grouping checks')
    parser.add_argument('--profile', default=str(ROOT / '.runtime/profile'))
    parser.add_argument('-C', '--nocustomization', action='store_true', help='Skip saved interface customization for this run')
    parser.add_argument('-z', '--customizationfile', help='Use a QGIS customization INI file')
    args = parser.parse_args()
    if args.customizationfile:
        args.customizationfile = str(Path(args.customizationfile).resolve())
        if not Path(args.customizationfile).is_file(): parser.error('Customization INI file does not exist')
    if args.customization_test or args.mesh_edit_test or args.dwg_import_test or args.georeferencer_test or args.statusbar_test: args.smoke_test = True
    args.smoke_test = args.smoke_test or args.labeling_test or args.annotation_test or args.data_actions_test or args.toolbar_test or args.shape_test or args.remaining_actions_test or args.view_actions_test or args.decoration_test or args.partial_actions_test or args.trim_extend_test
    def stage(name):
        if args.smoke_test:
            path = ROOT / '.runtime/smoke-stages.txt'
            path.parent.mkdir(exist_ok=True)
            with path.open('a', encoding='utf-8') as stream: stream.write(name + '\n')
    stage('start')
    from qgis.PyQt.QtCore import Qt, QTranslator, QTimer, QSettings

    if args.smoke_test:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(ROOT / '.runtime/smoke-settings'))
    from qgis.core import QgsApplication, Qgis, QgsSettings, QgsProject
    from qgis.gui import QgsGui
    # if Qgis.QGIS_VERSION_INT != 33410:
    #     raise RuntimeError(f'Requires QGIS 3.34.10, found {Qgis.QGIS_VERSION}')
    prefix = os.environ.get('QGIS_PREFIX_PATH', 'C:/OSGeo4W/apps/qgis-ltr')
    sys.path.insert(0, str(Path(prefix) / 'python/plugins'))
    Path(args.profile).mkdir(parents=True, exist_ok=True)
    QgsApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([], True, args.profile)
    app.setOrganizationName('QGIS-Python')
    app.setApplicationName('QGIS-Python-3.34')
    app.setStyle('Fusion')
    # Register application resources before constructing Designer or native widgets.
    from images import images_rc
    from qgis.PyQt.QtGui import QPixmap, QColor
    from qgis.PyQt.QtWidgets import QSplashScreen
    pixmap = QPixmap(str(ROOT / 'images/splash/splash.png'))
    scaled_pixmap = pixmap.scaledToWidth(480, Qt.SmoothTransformation)
    # scaled_pixmap = pixmap.scaledToHeight(300, Qt.SmoothTransformation)
    splash = QSplashScreen(scaled_pixmap)
    if not args.smoke_test and not QgsSettings().value('qgis/hideSplash', False, type=bool):
        splash.show()
        splash.showMessage('正在初始化 QGIS…', Qt.AlignBottom | Qt.AlignHCenter, QColor('white'))
        app.processEvents()
    app.initQgis()
    app.setWindowIcon(QIcon(QgsApplication.appIconPath()))
    QgsGui.editorWidgetRegistry().initEditors()
    translator = QTranslator(app)
    if translator.load(str(Path(prefix) / 'i18n/qgis_zh-Hans.qm')):
        app.installTranslator(translator)
    from src.app.qgisapp import QgisApp
    window = QgisApp(customization=not args.nocustomization, customizationFile=args.customizationfile)
    originalHook = sys.excepthook
    def exceptionHook(kind, value, tb):
        detail = ''.join(traceback.format_exception(kind, value, tb))
        sys.__stderr__.write(detail)
        window.mMessageBar.pushCritical('Python', str(value))
        QgsApplication.messageLog().logMessage(detail, 'Python', Qgis.Critical)
        window.runtimeErrors.append(detail)
    sys.excepthook = exceptionHook
    window.show()
    splash.finish(window)
    if args.project:
        window.addProject(args.project)
    if args.smoke_test:
        def smoke():
            if args.statusbar_test:
                from tests.src.python.test_qgisapp_statusbar import run
            elif args.georeferencer_test:
                from tests.src.python.test_qgisapp_georeferencer import run
            elif args.dwg_import_test:
                from tests.src.python.test_qgisapp_dwgimport import run
            elif args.mesh_edit_test:
                from tests.src.python.test_qgisapp_meshediting import run
            elif args.customization_test:
                from tests.src.python.test_qgscustomization import run
            elif args.trim_extend_test:
                from tests.src.python.test_qgisapp_trimextendfeature import run
            elif args.partial_actions_test:
                from tests.src.python.test_qgisapp_partialactions import run
            elif args.decoration_test:
                from tests.src.python.test_qgisapp_decorations import run
            elif args.view_actions_test:
                from tests.src.python.test_qgisapp_viewactions import run
            elif args.remaining_actions_test:
                from tests.src.python.test_qgisapp_remainingactions import run
            elif args.shape_test:
                from tests.src.python.test_qgisapp_shapes import run
            elif args.toolbar_test:
                from tests.src.python.test_qgisapp_toolbars import run
            elif args.data_actions_test:
                from tests.src.python.test_qgisapp_dataactions import run
            elif args.annotation_test:
                from tests.src.python.test_qgisapp_annotations import run
            elif args.labeling_test:
                from tests.src.python.test_qgisapp_labeling import runReport as run
            else:
                from tests.src.python.test_qgisapp import run
            try:
                report = run(window)
                report['runtimeErrors'] = window.runtimeErrors
                if window.runtimeErrors:
                    raise AssertionError(window.runtimeErrors)
                out = ROOT / 'output'
                out.mkdir(exist_ok=True)
                reportName = 'remaining-actions-test.json' if args.remaining_actions_test else 'shape-test.json' if args.shape_test else 'toolbar-test.json' if args.toolbar_test else 'data-actions-test.json' if args.data_actions_test else 'annotation-test.json' if args.annotation_test else 'labeling-test.json' if args.labeling_test else 'smoke-test.json'
                if args.view_actions_test: reportName = 'view-actions-test.json'
                if args.decoration_test: reportName = 'decoration-test.json'
                if args.trim_extend_test: reportName = 'trim-extend-test.json'
                if args.customization_test: reportName = 'customization-test.json'
                if args.mesh_edit_test: reportName = 'mesh-edit-test.json'
                if args.dwg_import_test: reportName = 'dwg-import-test.json'
                if args.georeferencer_test: reportName = 'georeferencer-test.json'
                if args.statusbar_test: reportName = 'statusbar-test.json'
                if args.partial_actions_test: reportName = 'partial-actions-test.json'
                (out / reportName).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                stage('report-written')
                window.grab().save(str(out / 'qgis-python.png'))
                stage('screenshot-written')
                window.prepareToQuit()
                app.exit(0)
                stage('exit-requested')
            except Exception:
                (ROOT / '.runtime/last-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
                traceback.print_exc(file=sys.__stderr__)
                app.exit(1)
        QTimer.singleShot(1200, smoke)
    result = app.exec_()
    stage('event-loop-exited:' + str(result))
    sys.excepthook = sys.__excepthook__
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    window.shutdown()
    stage('shutdown')
    # Release Python-owned GUI objects before destroying provider registries.
    from qgis.PyQt import sip
    QgsProject.instance().clear()
    app.processEvents()
    sip.delete(window)
    stage('window-deleted')
    app.exitQgis()
    stage('qgis-exited')
    return result


if __name__ == '__main__':
    try:
        exitCode = main()
    except Exception:
        (ROOT / '.runtime/last-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    sys.exit(exitCode)
