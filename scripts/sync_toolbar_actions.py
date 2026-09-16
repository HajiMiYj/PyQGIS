"""Inventory dynamic actions from QGIS 3.34 application/registry source.

Run separately from sync_upstream: this never rewrites the main window UI.
sourceKey identifies metadata IDs or C++ members, not invented QObject names.
"""
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('QGIS_SOURCE_ROOT', r'C:\QGIS_COMPILE\QGIS-final-3_34_10'))


def main():
    actions = []
    for path in sorted((SOURCE / 'src/app/maptools').glob('qgsmaptoolshape*.cpp')):
        cpp = path.read_text(encoding='utf-8')
        header = path.with_suffix('.h').read_text(encoding='utf-8')
        ids = re.findall(r'TOOL_ID(?:_\w+)?\s*=\s*QStringLiteral\(\s*"([^"]+)"', cpp + header)
        if not ids: continue
        namesBody = re.search(r'Metadata::name\(\) const\s*\{(.*?)\nQIcon', cpp, re.S)
        names = re.findall(r'QObject::tr\(\s*"([^"]+)"', namesBody[1])
        iconBody = re.search(r'Metadata::icon\(\) const\s*\{(.*?)\nQgsMapToolShapeAbstract', cpp, re.S)
        icons = re.findall(r'QStringLiteral\(\s*"([^"]+)"', iconBody[1])
        group = re.search(r'return QgsMapToolShapeAbstract::ShapeCategory::(\w+)', cpp)[1]
        assert len(ids) == len(names) == len(icons), path
        for toolId, name, icon in zip(ids, names, icons):
            actions.append(dict(sourceKey='shape:' + toolId, toolbar='mShapeDigitizeToolBar', text=name,
                                source=path.relative_to(SOURCE).as_posix(), group=group, icon=icon,
                                objectName=None, location='toolbar submenu',
                                note='原版 Shape 元数据动态动作；尚未移植捕获工具，未放入工具栏。'))
    assert len([a for a in actions if a['toolbar'] == 'mShapeDigitizeToolBar']) == 17
    path = SOURCE / 'src/app/mesh/qgsmaptooleditmeshframe.cpp'
    cpp = path.read_text(encoding='utf-8')
    labels = {'mActionRemoveVerticesFillingHole': 'Remove Selected Vertices and Fill Hole(s)',
              'mActionRemoveVerticesWithoutFillingHole': 'Remove Selected Vertices without Filling Hole(s)'}
    primary = {'mActionDigitizing', 'mActionSelectByPolygon', 'mActionSelectByExpression', 'mActionTransformCoordinates', 'mActionForceByLines'}
    for member, constructor in re.findall(r'(mAction\w+) = new QAction\( (.*?) \);', cpp):
        name = re.search(r'tr\( "([^"]+)"', constructor)
        icon = re.search(r'QStringLiteral\( "([^"]+)"', constructor)
        objectName = re.search(re.escape(member) + r'->setObjectName\( QStringLiteral\( "([^"]+)"', cpp)
        actions.append(dict(sourceKey='mesh:' + member, toolbar='mMeshToolBar', text=name[1] if name else labels[member],
                            source=path.relative_to(SOURCE).as_posix(), group='Mesh', icon=icon[1] if icon else '',
                            objectName=objectName[1] if objectName else None,
                            location='toolbar' if member in primary else 'mesh menu' if member == 'mActionReindexMesh' else 'map context menu',
                            note='原版网格编辑工具动态动作；编辑状态、鼠标交互和撤销联动尚未移植，未放入对应入口。'))
    actions.append(dict(sourceKey='mesh:mWidgetActionForceByLine', toolbar='mMeshToolBar', text='Force by Line Settings',
                        source=path.relative_to(SOURCE).as_posix(), group='Mesh', objectName=None, location='toolbar submenu',
                        note='原版线约束设置 QWidgetAction：交点新顶点、Z 插值、容差和单位；尚未移植。'))
    path = SOURCE / 'src/gui/annotations/qgsannotationitemguiregistry.cpp'
    cpp = path.read_text(encoding='utf-8')
    for itemType, name, icon in re.findall(r'new QgsAnnotationItemGuiMetadata\( QStringLiteral\( "([^"]+)" \),\s*QObject::tr\( "([^"]+)" \),\s*QgsApplication::getThemeIcon\( QStringLiteral\( "([^"]+)"', cpp):
        actions.append(dict(sourceKey='annotation:' + itemType, toolbar='mAnnotationsToolBar', text='Create ' + name,
                            source=path.relative_to(SOURCE).as_posix(), group='Annotation', icon=icon, objectName=None,
                            location='toolbar', note='原版注册表创建；实际 QObject 名由翻译后的 visibleName 动态生成。'))
    assert len([a for a in actions if a['toolbar'] == 'mAnnotationsToolBar']) == 5
    path = SOURCE / 'src/ui/georeferencer/qgsgeorefpluginguibase.ui'
    form = ET.parse(path)
    cpp = (SOURCE / 'src/app/georeferencer/qgsgeorefmainwindow.cpp').read_text(encoding='utf-8')
    icons = dict(re.findall(r'(mAction\w+)->setIcon\( QgsApplication::getThemeIcon\( QStringLiteral\( "([^"]+)"', cpp))
    for action in form.findall('.//action'):
        name = action.get('name')
        toolbar = next((widget.get('name') for widget in form.findall('.//widget')
                        if widget.get('class') == 'QToolBar' and any(a.get('name') == name for a in widget.findall('addaction'))), '')
        actions.append(dict(sourceKey='georeferencer:' + name, toolbar='georeferencer.' + toolbar if toolbar else '',
                            text=action.findtext("property[@name='text']/string", name), objectName=name,
                            source=path.relative_to(SOURCE).as_posix(), group='Georeferencer', icon=icons.get(name, ''),
                            location='toolbar' if toolbar else 'menu', note='原版地理配准窗口 Action。'))
    payload = {'version': '3.34.10', 'actions': actions, 'extensionPoints': [
        {'toolbar': 'mWebToolBar', 'source': 'src/app/qgisapp.cpp', 'note': '原版为空的插件扩展工具栏；由插件调用 addWebToolBarIcon/addWebToolBarWidget 填入，没有固定内置 Action 清单。'}]}
    (ROOT / 'docs/upstream-toolbar-actions.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Imported {len(actions)} dynamic actions and one Web extension point.')


if __name__ == '__main__': main()
