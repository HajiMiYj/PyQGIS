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


def resolveProfile(args):
    """Resolve the startup profile like QgsUserProfileManager + main.cpp.

    QgsApplication fixes its profile folder at construction and there is no
    widget-capable QApplication yet on the ask path, so the selection policy is
    read straight from the profiles.ini the manager itself would use. Returns
    (folder, name, root, ask, missingLastProfile).
    """
    from qgis.core import Qgis, QgsUserProfileManager
    from qgis.PyQt.QtCore import QSettings, QStandardPaths

    if args.profile and Path(args.profile).is_dir():
        # Explicit folder: launchers and the test harness pass a directory.
        folder = str(Path(args.profile).resolve())
        root = QgsUserProfileManager.resolveProfilesFolder(str(Path(folder).parent))
        return folder, Path(folder).name, root, False, ''

    if args.smoke_test and not args.profile and not args.profiles_path:
        folder = str(ROOT / '.runtime/profile')
        root = QgsUserProfileManager.resolveProfilesFolder(str(ROOT / '.runtime'))
        return folder, 'default', root, False, ''

    basePath = args.profiles_path or os.environ.get('QGIS_CUSTOM_CONFIG_PATH', '')
    if not basePath:
        basePath = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    root = QgsUserProfileManager.resolveProfilesFolder(basePath)
    profileSettings = QSettings(str(Path(root) / 'profiles.ini'), QSettings.IniFormat)
    names = sorted(p.name for p in Path(root).iterdir() if p.is_dir()) if Path(root).is_dir() else []

    def defaultName():
        return profileSettings.value('/core/defaultProfile', 'default')

    name, ask, missingLastProfile = args.profile or '', False, ''
    if not name:
        if not names:
            name = defaultName()
        else:
            policy = int(profileSettings.value('/core/selectionPolicy', 0))
            if policy == int(Qgis.UserProfileSelectionPolicy.LastProfile):
                name = profileSettings.value('/core/lastProfile', '') or ''
                if name not in names:
                    missingLastProfile = name if name and name != defaultName() else ''
                    name = defaultName()
            elif policy == int(Qgis.UserProfileSelectionPolicy.AskUser):
                if len(names) == 1:
                    name = names[0]
                else:
                    # Provisional profile so QgsApplication can start; the chooser
                    # below replaces it and relaunches when the choice differs.
                    lastName = profileSettings.value('/core/lastProfile', '') or ''
                    name = lastName if lastName in names else defaultName()
                    ask = True
            else:
                name = defaultName()
    if not name:
        name = 'default'
    return str(Path(root) / name), name, root, ask, missingLastProfile


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
    parser.add_argument('--mesh-calculator-test', action='store_true', help='Run mesh calculator UI, time and output checks')
    parser.add_argument('--dwg-import-test', action='store_true', help='Run CAD import, preview, grouping and cancellation checks')
    parser.add_argument('--georeferencer-test', action='store_true', help='Run georeferencer actions, GCP IO, raster and vector output checks')
    parser.add_argument('--statusbar-test', action='store_true', help='Run native status bar layout and interaction checks')
    parser.add_argument('--partial-actions-test', action='store_true', help='Run focused annotation editing and report grouping checks')
    parser.add_argument('--layertree-test', action='store_true', help='Run layer-tree context-menu action checks')
    parser.add_argument('--startup-test', action='store_true', help='Run startup contract checks')
    parser.add_argument('--profile-test', action='store_true', help='Run user profile management checks')
    parser.add_argument('--profile', default=None, help='Profile name, or an explicit profile folder')
    parser.add_argument('-S', '--profiles-path', default=None, help='Path that contains the profiles folder')
    parser.add_argument('-C', '--nocustomization', action='store_true', help='Skip saved interface customization for this run')
    parser.add_argument('-n', '--nologo', action='store_true', help='Hide the splash screen for this run')
    parser.add_argument('-z', '--customizationfile', help='Use a QGIS customization INI file')
    args = parser.parse_args()
    if args.customizationfile:
        args.customizationfile = str(Path(args.customizationfile).resolve())
        if not Path(args.customizationfile).is_file(): parser.error('Customization INI file does not exist')
    if args.customization_test or args.mesh_edit_test or args.mesh_calculator_test or args.dwg_import_test or args.georeferencer_test or args.statusbar_test or args.layertree_test or args.startup_test or args.profile_test: args.smoke_test = True
    args.smoke_test = args.smoke_test or args.labeling_test or args.annotation_test or args.data_actions_test or args.toolbar_test or args.shape_test or args.remaining_actions_test or args.view_actions_test or args.decoration_test or args.partial_actions_test or args.trim_extend_test
    def stage(name):
        if args.smoke_test:
            path = ROOT / '.runtime/smoke-stages.txt'
            path.parent.mkdir(exist_ok=True)
            with path.open('a', encoding='utf-8') as stream: stream.write(name + '\n')
    stage('start')
    from qgis.PyQt.QtCore import Qt, QTranslator, QTimer, QSettings, QLocale

    if args.smoke_test:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(ROOT / '.runtime/smoke-settings'))
    from qgis.core import QgsApplication, Qgis, QgsSettings, QgsProject
    from qgis.gui import QgsGui
    # if Qgis.QGIS_VERSION_INT != 33410:
    #     raise RuntimeError(f'Requires QGIS 3.34.10, found {Qgis.QGIS_VERSION}')
    prefix = os.environ.get('QGIS_PREFIX_PATH', 'C:/OSGeo4W/apps/qgis-ltr')
    sys.path.insert(0, str(Path(prefix) / 'python/plugins'))
    # Organization/application names must be set before the profile root is
    # resolved: QStandardPaths derives the default profiles location from them,
    # and it has to match the tree QgsApplication will use afterwards. Native
    # QGIS uses "QGIS"/"QGIS3"; sharing that tree means this port and native QGIS
    # overwrite each other's settings, so it stays opt-in.
    from qgis.PyQt.QtCore import QCoreApplication
    if os.environ.get('QGIS_PYTHON_NATIVE_PROFILE') == '1':
        QCoreApplication.setOrganizationName(QgsApplication.QGIS_ORGANIZATION_NAME)
        QCoreApplication.setOrganizationDomain(QgsApplication.QGIS_ORGANIZATION_DOMAIN)
        QCoreApplication.setApplicationName(QgsApplication.QGIS_APPLICATION_NAME)
    else:
        QCoreApplication.setOrganizationName('QGIS-Python')
        QCoreApplication.setApplicationName('QGIS-Python-3.34')
    # Profile selection happens before QgsApplication exists (native main.cpp
    # resolves it after construction, which Python cannot do).
    profileFolder, profileName, rootProfileFolder, askProfile, missingLastProfile = resolveProfile(args)
    Path(profileFolder).mkdir(parents=True, exist_ok=True)
    # Native main.cpp application attributes.
    QgsApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QgsApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    from qgis.PyQt.QtGui import QGuiApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QgsApplication.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    if hasattr(Qt, 'AA_DisableWindowContextHelpButton'):
        QgsApplication.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    QgsApplication.setPrefixPath(prefix, True)
    app = QgsApplication([], True, profileFolder)
    # Register application resources before constructing Designer or native widgets.
    from images import images_rc
    from qgis.PyQt.QtGui import QPixmap, QColor
    from qgis.PyQt.QtWidgets import QSplashScreen
    # Splash screen. Upstream 3.34.10 has this block commented out, but Options
    # still exposes qgis/hideSplash and main.cpp still documents --nologo, so the
    # desktop port keeps it and honours both switches.
    splash = None
    if not args.smoke_test and not args.nologo and not QgsSettings().value('qgis/hideSplash', False, type=bool):
        splashPixmap = QPixmap(str(ROOT / 'images/splash/splash.png'))
        if not splashPixmap.isNull():
            splash = QSplashScreen(splashPixmap.scaledToWidth(480, Qt.SmoothTransformation))
            splash.show()
            splash.showMessage('正在初始化 QGIS…', Qt.AlignBottom | Qt.AlignHCenter, QColor('white'))
            app.processEvents()
    app.initQgis()
    app.setWindowIcon(QIcon(QgsApplication.appIconPath()))
    QgsGui.editorWidgetRegistry().initEditors()
    # Ask-user policy. Native shows the chooser before QgsApplication::init();
    # Python cannot change the profile folder after construction, so a different
    # choice relaunches with --profile (the same mechanism native
    # QgsUserProfileManager::loadUserProfile() uses to switch profiles).
    if askProfile:
        from qgis.PyQt.QtWidgets import QDialog
        from qgis.PyQt.QtCore import QProcess
        from qgis.core import QgsUserProfileManager
        from src.app.options.qgsuserprofileselectiondialog import QgsUserProfileSelectionDialog
        chooser = QgsUserProfileSelectionDialog(QgsUserProfileManager(rootProfileFolder))
        if chooser.exec_() != QDialog.Accepted:
            return 0
        chosen = chooser.selectedProfileName()
        if chosen and chosen != profileName:
            cleaned, skip = [], False
            for value in list(sys.argv[1:]):
                if skip: skip = False; continue
                if value == '--profile': skip = True; continue
                cleaned.append(value)
            QProcess.startDetached(sys.executable, [sys.argv[0]] + cleaned + ['--profile', chosen])
            return 0
    # Native main.cpp style selection: qgis/style, fusion for non-default UI
    # themes, and the known-broken adwaita styles rejected outright.
    from qgis.PyQt.QtWidgets import QApplication as _QApp, QStyleFactory
    settings = QgsSettings()
    styleKeys = [key.lower() for key in QStyleFactory.keys()]
    desiredStyle = settings.value('qgis/style', '', type=str)
    if settings.value('UI/UITheme', '', type=str) != 'default' and 'fusion' in styleKeys:
        desiredStyle = 'fusion'
    activeStyleName = _QApp.style().metaObject().className()
    if 'adwaita' in desiredStyle.lower() or (not desiredStyle and 'adwaita' in activeStyleName.lower()):
        if 'fusion' in styleKeys:
            desiredStyle = 'fusion'
    from src.app.qgsproxystyle import QgsAppStyle
    appStyle = QgsAppStyle(desiredStyle if desiredStyle else activeStyleName)
    _QApp.setStyle(appStyle)
    if desiredStyle and activeStyleName != desiredStyle:
        settings.setValue('qgis/style', desiredStyle)
    # Native QgisApp::setTheme() -> QgsApplication::setUITheme(): loads the theme's
    # style.qss (substituting its @variables), applies palette.txt and switches the
    # icon theme. Without this the UI theme setting has no effect whatsoever.
    QgsApplication.setUITheme(settings.value('UI/UITheme', 'default', type=str))
    # Native main.cpp locale block: command line, then the user override, then the
    # system locale; locale/globalLocale may override the default QLocale.
    translationCode = os.environ.get('QGIS_TRANSLATION_CODE', '')
    userTranslation = settings.value('locale/userLocale', '', type=str)
    globalLocale = settings.value('locale/globalLocale', '', type=str)
    localeOverride = settings.value('locale/overrideFlag', False, type=bool)
    showGroupSeparator = settings.value('locale/showGroupSeparator', False, type=bool) if localeOverride else False
    if not translationCode:
        if not localeOverride or not userTranslation:
            translationCode = QLocale().name()
            settings.setValue('locale/userLocale', translationCode)
        else:
            translationCode = userTranslation
    else:
        settings.setValue('locale/userLocale', translationCode)
    if localeOverride and globalLocale:
        QLocale.setDefault(QLocale(globalLocale))
    currentLocale = QLocale()
    if showGroupSeparator:
        currentLocale.setNumberOptions(currentLocale.numberOptions() & ~QLocale.OmitGroupSeparator)
    else:
        currentLocale.setNumberOptions(currentLocale.numberOptions() | QLocale.OmitGroupSeparator)
    QLocale.setDefault(currentLocale)
    # setTranslation() installs the qgis_<code>.qm and qt_<code>.qm translators.
    QgsApplication.setTranslation(translationCode)
    QgsApplication.setLocale(QLocale())
    QgsApplication.setMaxThreads(settings.value('qgis/max_threads', -1, type=int))
    # setTranslation() above already installed qgis_<code>.qm and qt_<code>.qm via
    # QgsApplication::installTranslators(), so no hardcoded translation is forced.
    from src.app.qgisapp import QgisApp
    window = QgisApp(customization=not args.nocustomization, customizationFile=args.customizationfile,
                     rootProfileFolder=rootProfileFolder, profileName=profileName)
    # Qt replaces the top level style with a QStyleSheetStyle once the theme
    # stylesheet is set, so keep the installed proxy for introspection.
    window.mAppStyle = appStyle
    originalHook = sys.excepthook
    def exceptionHook(kind, value, tb):
        detail = ''.join(traceback.format_exception(kind, value, tb))
        sys.__stderr__.write(detail)
        window.mMessageBar.pushCritical('Python', str(value))
        QgsApplication.messageLog().logMessage(detail, 'Python', Qgis.Critical)
        window.runtimeErrors.append(detail)
    sys.excepthook = exceptionHook
    window.show()
    if args.project:
        window.addProject(args.project)
    else:
        # Native main.cpp gives the canvas a usable extent when started without
        # a project or layer file.
        from qgis.core import QgsRectangle
        window.mMapCanvas.setExtent(QgsRectangle(-1, -1, 1, 1))
    # Native main.cpp: "make sure we don't have a dirty blank project after
    # launch" - without this an untouched session still prompts to save on exit.
    QgsProject.instance().setDirty(False)
    if splash is not None:
        splash.finish(window)
    # Native main.cpp warns when the "last used profile" policy fell back.
    if missingLastProfile:
        window.mMessageBar.pushWarning(
            '未找到配置档案',
            f"上次使用的配置档案 '{missingLastProfile}' 未找到，已改用默认配置档案。")
    if args.smoke_test:
        def smoke():
            if args.statusbar_test:
                from tests.src.python.test_qgisapp_statusbar import run
            elif args.layertree_test:
                from tests.src.python.test_qgisapp_layertree import run
            elif args.startup_test:
                from tests.src.python.test_qgisapp_startup import run
            elif args.profile_test:
                from tests.src.python.test_qgisapp_profile import run
            elif args.georeferencer_test:
                from tests.src.python.test_qgisapp_georeferencer import run
            elif args.dwg_import_test:
                from tests.src.python.test_qgisapp_dwgimport import run
            elif args.mesh_edit_test:
                from tests.src.python.test_qgisapp_meshediting import run
            elif args.mesh_calculator_test:
                from tests.src.python.test_qgisapp_meshcalculator import run
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
                if args.mesh_calculator_test: reportName = 'mesh-calculator-test.json'
                if args.dwg_import_test: reportName = 'dwg-import-test.json'
                if args.georeferencer_test: reportName = 'georeferencer-test.json'
                if args.statusbar_test: reportName = 'statusbar-test.json'
                if args.layertree_test: reportName = 'layertree-test.json'
                if args.startup_test: reportName = 'startup-test.json'
                if args.profile_test: reportName = 'profile-test.json'
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
