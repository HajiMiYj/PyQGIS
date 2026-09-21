"""One checklist with audited action states, independent of prose notes."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]

# Concrete omissions belonging to each action, not broad pending QA or an
# unfinished neighboring action. Shared shape capture, dimensions, topology,
# ring/part completion and radius-arc continuation passed the shape batch.
PARTIAL_ACTIONS = {
    # GDAL CAD backend: DWG is limited to what libopencad reads (R2000 and some
    # earlier) and DWG block insert modes are unavailable; DXF now keeps true
    # curves (ARC/CIRCLE/bulges) and reads ASCII *and* binary layer state.
    'mActionDwgImport',
}

# Audited as needing a native DLL load rather than a PyQGIS reimplementation:
# the topology rule engine has no Python equivalent, so plugin_topology.dll is
# driven through classFactory + QgisPlugin's vtable (see qgsnativepluginloader).
# Historical notes kept for the record, all since resolved through lower-level API:
#  - mesh: face/edge picking used to look impossible because QgsMeshLayer
#    nativeMesh()/triangularMesh() are unbound; the actions were in fact already
#    implemented on the map tool and only mislabelled here.
#  - embed layers: QgsProject::createEmbeddedLayer() is unbound, so the layer
#    branch replays its steps with QgsLayerDefinition.loadLayerDefinitionLayers()
#    plus the source project's path resolver and dependency order.
BLOCKED_BINDING_ACTIONS = {
    # No action currently needs this state: every previously listed entry was
    # implemented through lower-level API instead of being left unavailable.
}

# Implementations that already passed their runtime suites (elevation profile via
# --view-actions-test, annotation layer properties via --annotation-test).
PENDING_RUNTIME_ACTIONS = set()


def implementationState(action):
    if action['status'] == 'excluded-gps': return 'excluded-gps'
    if action.get('objectName') == 'mActionAddLayerSeparator' and action['status'] == 'connected': return 'ui-placeholder'
    key = action.get('sourceKey') or action['objectName']
    if action['status'] == 'not-ported': return 'not-ported'
    if key in BLOCKED_BINDING_ACTIONS: return 'blocked-bindings'
    if key in PARTIAL_ACTIONS: return 'partial'
    if key in PENDING_RUNTIME_ACTIONS: return 'implemented-pending-debug'
    return 'implemented'


def cell(value): return str(value or '').replace('|', '\\|').replace('\n', ' ')


def label(action):
    return {'excluded-gps': '排除（范围外：GPS/3D）', 'not-ported': '未实现', 'paused': '暂停',
            'ui-placeholder': '已接入（隐藏插入锚点）',
            'partial': '部分实现', 'implemented': '已接入',
            'implemented-pending-debug': '已接入，待调试',
            'blocked-bindings': '部分实现（PyQGIS 绑定缺失）'}[implementationState(action)]


def writeChecklist(status):
    lines = ['# 功能移植清单', '', '| 原版 Action | 名称 | 状态 |', '| --- | --- | --- |']
    for action in status['actions'] + status.get('dynamicActions', []):
        key = action.get('sourceKey') or action['objectName']
        lines.append(f"| `{key}` | {cell(action['text'].replace('&', ''))} | {label(action)} |")
    path = root / '功能移植清单.md'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


if __name__ == '__main__':
    statusPath = root / 'output/implementation-status.json'
    if not statusPath.exists():
        raise SystemExit(
            f'缺少 {statusPath}。该文件由应用启动时生成（生成物在 output/，不入库）：'
            '先运行一次 main.py，再执行本脚本。')
    status = json.loads(statusPath.read_text(encoding='utf-8'))
    for action in status['actions'] + status.get('dynamicActions', []):
        action['implementationState'] = implementationState(action)
    statusPath.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    writeChecklist(status)
