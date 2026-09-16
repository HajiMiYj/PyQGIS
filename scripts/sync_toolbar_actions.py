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
    # C++ creates these outside qgisapp.ui. Keep their source variable names,
    # including local variables, as scoped keys instead of inventing UI actions.
    for name, label in [('actionAddGroup', 'Add Group'), ('actionExpandAll', 'Expand All'),
                        ('actionCollapseAll', 'Collapse All'), ('mActionStyleDock', 'Layer Styling'),
                        ('mFilterLegendByMapContentAction', 'Filter Legend by Map Content'),
                        ('mFilterLegendToggleShowPrivateLayersAction', 'Show Private Layers'),
                        ('clearRecentProjectsAction', 'Clear List'), ('openProfileFolderAction', 'Open Active Profile Folder'),
                        ('newProfileAction', 'New Profile…')]:
        actions.append(dict(sourceKey='qgisapp:'+name, objectName=name, text=label, toolbar='',
                            source='src/app/qgisapp.cpp', group='Main window dynamic', icon='',
                            location='menu or layer panel', note='原版 C++ 动态创建入口。'))
    for name, label in [('actionZoomToGroup', 'Zoom to Group'), ('actionMoveOutOfGroup', 'Move Out of Group'),
                        ('actionMoveToTop', 'Move to Top'), ('actionMoveToBottom', 'Move to Bottom'),
                        ('actionCheckAndAllChildren', 'Check Group and All Children'),
                        ('actionUncheckAndAllChildren', 'Uncheck Group and All Children'),
                        ('actionCheckAndAllParents', 'Check Layer and All Parents'),
                        ('actionShowLabels', 'Show Labels'), ('changeDataSource', 'Change / Repair Data Source…'),
                        ('legendGroupSetWmsData', 'Set Group WMS Data…'),
                        ('openRasterAttributeTable', 'Open Raster Attribute Table'),
                        ('createRasterAttributeTable', 'Create Raster Attribute Table'),
                        ('loadRasterAttributeTableFromFile', 'Load Raster Attribute Table from VAT.DBF'),
                        ('zoomToLayerScale', 'Zoom to Visible Scale')]:
        actions.append(dict(sourceKey='layertree:'+name, objectName=None, text=label, toolbar='',
                            source='src/app/qgsapplayertreeviewmenuprovider.cpp', group='Layer tree context', icon='',
                            location='context menu', note='以原版工厂方法或槽名识别的右键入口。'))
    actions.append(dict(sourceKey='qgisapp:updateProjectFromTemplates', objectName=None, text='New from Template', toolbar='',
                        source='src/app/qgisapp.cpp', group='Main window dynamic', icon='', location='menu',
                        note='原版工程模板目录动态菜单。'))
    for key, name, label, toolbar, source in [
        ('db_manager:action', 'dbManager', '数据库管理器（DB Manager）', 'mDatabaseToolBar', 'python/plugins/db_manager/db_manager_plugin.py'),
        ('offline_editing:mActionConvertProject', 'mActionConvertProject', '转换为离线工程', 'mDatabaseToolBar', 'src/plugins/offline_editing/offline_editing_plugin.cpp'),
        ('offline_editing:mActionSynchronize', 'mActionSynchronize', '同步离线工程', 'mDatabaseToolBar', 'src/plugins/offline_editing/offline_editing_plugin.cpp'),
        ('topology:mQActionPointer', 'mQActionPointer', '拓扑检查器（Topology Checker）', 'mVectorToolBar', 'src/plugins/topology/topol.cpp'),
        ('MetaSearch:action_run', None, '元数据目录搜索（MetaSearch）', 'mWebToolBar', 'python/plugins/MetaSearch/plugin.py'),
    ]:
        actions.append(dict(sourceKey=key, objectName=name, text=label, toolbar=toolbar, source=source,
                            group='Bundled plugins', icon='', location='toolbar', note='原版随附插件提供的工具栏入口。'))
    payload = {'version': '3.34.10', 'actions': actions, 'extensionPoints': [
        {'toolbar': 'mWebToolBar', 'source': 'src/app/qgisapp.cpp', 'note': '原版为空的插件扩展工具栏；由插件调用 addWebToolBarIcon/addWebToolBarWidget 填入，没有固定内置 Action 清单。'}]}
    (ROOT / 'docs/upstream-toolbar-actions.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Imported {len(actions)} dynamic actions and one Web extension point.')


if __name__ == '__main__': main()
