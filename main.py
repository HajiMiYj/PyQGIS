"""Python counterpart of src/app/main.cpp. Requires OSGeo4W QGIS 3.34.10.

Run it with the OSGeo4W interpreter:

    python-qgis-ltr.bat main.py [project] [-n] [-C] [-z INI] [--profile NAME] [-S DIR]

The built-in checks live in check.py and reuse buildSession() from this module.
"""
import argparse
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import traceback

from PyQt5.QtGui import QIcon

# main.py lives in the repository root, which has to be importable for
# "from src.app..." and the images/resources packages.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def parseArguments(argv=None):
    """Native main.cpp command line: an optional project plus the startup switches."""
    parser = argparse.ArgumentParser()
    parser.add_argument('project', nargs='?')
    parser.add_argument('--profile', default=None, help='配置档案名，或直接的档案目录')
    parser.add_argument('-S', '--profiles-path', default=None, help='包含 profiles 目录的路径')
    parser.add_argument('-C', '--nocustomization', action='store_true', help='本次跳过已保存的界面自定义')
    parser.add_argument('-n', '--nologo', action='store_true', help='本次不显示启动画面')
    parser.add_argument('-z', '--customizationfile', help='使用指定的界面自定义 INI')
    args = parser.parse_args(argv)
    if args.customizationfile:
        args.customizationfile = str(Path(args.customizationfile).resolve())
        if not Path(args.customizationfile).is_file():
            parser.error('界面自定义 INI 不存在')
    return args


def resolveProfile(profile=None, profilesPath=None, checkMode=False):
    """Resolve the startup profile like QgsUserProfileManager + main.cpp.

    QgsApplication fixes its profile folder at construction and there is no
    widget-capable QApplication yet on the ask path, so the selection policy is
    read straight from the profiles.ini the manager itself would use. Returns
    (folder, name, root, ask, missingLastProfile).
    """
    from qgis.core import Qgis, QgsUserProfileManager
    from qgis.PyQt.QtCore import QSettings, QStandardPaths

    if profile and Path(profile).is_dir():
        folder = str(Path(profile).resolve())
        root = QgsUserProfileManager.resolveProfilesFolder(str(Path(folder).parent))
        return folder, Path(folder).name, root, False, ''

    if checkMode and not profile and not profilesPath:
        # Checks keep a scratch profile inside the repository.
        folder = str(ROOT / '.runtime/profile')
        root = QgsUserProfileManager.resolveProfilesFolder(str(ROOT / '.runtime'))
        return folder, 'default', root, False, ''

    basePath = profilesPath or os.environ.get('QGIS_CUSTOM_CONFIG_PATH', '')
    if not basePath:
        basePath = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    root = QgsUserProfileManager.resolveProfilesFolder(basePath)
    profileSettings = QSettings(str(Path(root) / 'profiles.ini'), QSettings.IniFormat)
    names = sorted(p.name for p in Path(root).iterdir() if p.is_dir()) if Path(root).is_dir() else []

    def defaultName():
        return profileSettings.value('/core/defaultProfile', 'default')

    name, ask, missingLastProfile = profile or '', False, ''
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


def installExceptionHook(window):
    """Surface unhandled exceptions in the message bar and the log panel."""

    def exceptionHook(kind, value, tb):
        detail = ''.join(traceback.format_exception(kind, value, tb))
        sys.__stderr__.write(detail)
        window.mMessageBar.pushCritical('Python', str(value))
        from qgis.core import QgsApplication, Qgis
        QgsApplication.messageLog().logMessage(detail, 'Python', Qgis.Critical)
        window.runtimeErrors.append(detail)

    sys.excepthook = exceptionHook


def buildSession(argv=None, checkMode=False):
    """Create QgsApplication and the main window following native main.cpp order.

    Returns (app, window, context). check.py calls this with checkMode=True to run
    its checks against a real window and event loop.
    """
    args = parseArguments([] if checkMode else argv)
    from qgis.PyQt.QtCore import Qt, QTimer, QSettings, QLocale

    if checkMode:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(ROOT / '.runtime/check-settings'))
    from qgis.core import QgsApplication, Qgis, QgsSettings, QgsProject
    from qgis.gui import QgsGui
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
    profileFolder, profileName, rootProfileFolder, askProfile, missingLastProfile = resolveProfile(
        profile=args.profile, profilesPath=args.profiles_path, checkMode=checkMode)
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
    from qgis.PyQt.QtGui import QPixmap, QGuiApplication
    from qgis.PyQt.QtWidgets import QSplashScreen
    # Splash screen. Upstream 3.34.10 has this block commented out, but Options
    # still exposes qgis/hideSplash and main.cpp still documents --nologo, so the
    # desktop port keeps it and honours both switches. Sizing, mask and the
    # staged messages follow the native QSplashScreen setup.
    splash = None
    if not checkMode and not args.nologo and not QgsSettings().value('qgis/hideSplash', False, type=bool):
        splashPixmap = QPixmap(str(ROOT / 'images/splash/splash.png'))
        if not splashPixmap.isNull():
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                splashPixmap.setDevicePixelRatio(screen.devicePixelRatio())
            devicePixelRatio = splashPixmap.devicePixelRatioF()
            splash = QSplashScreen(splashPixmap.scaled(
                int(600 * devicePixelRatio), int(300 * devicePixelRatio),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if screen is not None:
                center = screen.availableGeometry().center()
                splash.move(center - splash.rect().center())
            splash.setMask(splashPixmap.mask())
            splash.show()
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
            return app, None, SimpleNamespace(splash=splash, missingLastProfile='', exited=True)
        chosen = chooser.selectedProfileName()
        if chosen and chosen != profileName:
            cleaned, skip = [], False
            for value in list(argv if argv is not None else sys.argv[1:]):
                if skip: skip = False; continue
                if value == '--profile': skip = True; continue
                cleaned.append(value)
            QProcess.startDetached(sys.executable, [sys.argv[0]] + cleaned + ['--profile', chosen])
            return app, None, SimpleNamespace(splash=splash, missingLastProfile='', exited=True)
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
                     rootProfileFolder=rootProfileFolder, profileName=profileName,
                     splash=splash, skipVersionCheck=checkMode)
    # Qt replaces the top level style with a QStyleSheetStyle once the theme
    # stylesheet is set, so keep the installed proxy for introspection.
    window.mAppStyle = appStyle
    installExceptionHook(window)
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
    # Native main.cpp calls completeInitialization() right after show(); it emits
    # initializationCompleted, which QgisApp::fileOpenAfterLaunch() answers by
    # honouring qgis/projOpenAtLaunch (welcome page / most recent / specific / new).
    window.completeInitialization()
    if checkMode:
        # Checks drive the map canvas, while qgis/projOpenAtLaunch == 0 makes the
        # welcome page the startup view, so bring the canvas forward.
        window.showMapCanvas()
    QgsProject.instance().setDirty(False)
    # Native main.cpp warns when the "last used profile" policy fell back.
    if missingLastProfile:
        window.mMessageBar.pushWarning(
            '未找到配置档案',
            f"上次使用的配置档案 '{missingLastProfile}' 未找到，已改用默认配置档案。")
    context = SimpleNamespace(splash=splash, missingLastProfile=missingLastProfile,
                              profileName=profileName, profileFolder=profileFolder,
                              rootProfileFolder=rootProfileFolder, args=args, exited=False)
    return app, window, context


def finishSession(app, window):
    """Native shutdown sequence: release the window before QGIS unloads providers."""
    from qgis.core import QgsProject
    sys.excepthook = sys.__excepthook__
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    window.shutdown()
    from qgis.PyQt import sip
    QgsProject.instance().clear()
    app.processEvents()
    sip.delete(window)
    app.exitQgis()


def runApplication(argv=None, checkMode=False, onReady=None):
    """Build the session, run the event loop, then shut down. Returns the exit code.

    onReady(app, window, context) runs once the window is on screen and before the
    event loop starts; check.py uses it to schedule the selected check.
    """
    app, window, context = buildSession(argv, checkMode=checkMode)
    if context.exited:
        return 0
    if onReady is not None:
        onReady(app, window, context)
    result = app.exec_()
    finishSession(app, window)
    return result


def main(argv=None):
    return runApplication(argv)


if __name__ == '__main__':
    sys.exit(main())
