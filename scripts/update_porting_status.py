"""One checklist with audited action states, independent of prose notes."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]

# Concrete omissions belonging to each action, not broad pending QA or an
# unfinished neighboring action. Shared shape capture, dimensions, topology,
# ring/part completion and radius-arc continuation passed the shape batch.
PARTIAL_ACTIONS = {
    'mActionShowGeoreferencer',            # Raster projective, PDF output and docking remain.
    'georeferencer:mActionStartGeoref',
    'georeferencer:mActionTransformSettings',
    'georeferencer:mActionGeorefConfig',
    'mActionDwgImport',                   # GDAL CAD backend; libdxfrw fidelity/version coverage remains.
    'mActionEmbedLayers',                 # Individual embedded layers.
    'mesh:mActionDigitizing',             # Face/edge picking and movement; vertex movement exists.
    'mesh:mActionSelectByPolygon',        # Polygon selection of faces.
    'mesh:mActionSelectByExpression',     # Face selection highlight/zoom.
    'mesh:mActionTransformCoordinates',   # Full face/edge preview.
    'mesh:mActionFacesRefinement',        # Hovered face branch.
    'mesh:mActionRemoveFaces',            # Hovered face branch.
    'mesh:mActionSplitFaces',             # Hovered face branch.
}

# Implementations written in a batch awaiting the user's combined runtime QA.
PENDING_RUNTIME_ACTIONS = {'mMainAnnotationLayerProperties', 'mActionElevationProfile'}


def implementationState(action):
    if action['status'] == 'excluded-gps': return 'excluded-gps'
    if action.get('objectName') == 'mActionAddLayerSeparator' and action['status'] == 'connected': return 'ui-placeholder'
    if action.get('objectName') == 'mActionOptions': return 'paused'
    key = action.get('sourceKey') or action['objectName']
    if action['status'] == 'not-ported': return 'not-ported'
    if key in PARTIAL_ACTIONS: return 'partial'
    if key in PENDING_RUNTIME_ACTIONS: return 'implemented-pending-debug'
    return 'implemented'


def cell(value): return str(value or '').replace('|', '\\|').replace('\n', ' ')


def label(action):
    return {'excluded-gps': '排除 GPS', 'not-ported': '未实现', 'paused': '暂停',
            'ui-placeholder': '已接入（隐藏插入锚点）',
            'partial': '部分实现', 'implemented': '已接入',
            'implemented-pending-debug': '已接入，待调试'}[implementationState(action)]


def writeChecklist(status):
    lines = ['# 功能移植清单', '', '| 原版 Action | 名称 | 状态 |', '| --- | --- | --- |']
    for action in status['actions'] + status.get('dynamicActions', []):
        key = action.get('sourceKey') or action['objectName']
        lines.append(f"| `{key}` | {cell(action['text'].replace('&', ''))} | {label(action)} |")
    path = root / '功能移植清单.md'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


if __name__ == '__main__':
    statusPath = root / 'docs/implementation-status.json'
    status = json.loads(statusPath.read_text(encoding='utf-8'))
    for action in status['actions'] + status.get('dynamicActions', []):
        action['implementationState'] = implementationState(action)
    statusPath.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    writeChecklist(status)
