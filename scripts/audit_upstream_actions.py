"""Read-only source census. Candidates are not proof of missing behavior.

Native widgets expose their own actions; source text matching cannot decide
whether those actions are available at runtime. Audited entries belong to the
single porting checklist, while this JSON retains evidence for further review.
"""
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('QGIS_SOURCE_ROOT', r'C:\QGIS_COMPILE\QGIS-final-3_34_10'))


def main():
    statusPath = ROOT / 'docs/implementation-status.json'
    if not statusPath.exists():
        raise SystemExit(
            f'缺少 {statusPath}。该文件由应用启动时生成（docs/ 只放生成物，可随时删除）：'
            '先运行一次 main.py，再执行本脚本。')
    status = json.loads(statusPath.read_text(encoding='utf-8'))
    static = {a['objectName'] for a in status['actions']}
    dynamic = {a['sourceKey'] for a in status.get('dynamicActions', [])}
    ui = []
    for path in sorted((SOURCE/'src/ui').rglob('*.ui')):
        for action in ET.parse(path).findall('.//action'):
            name = action.get('name')
            mainWindow = path.name == 'qgisapp.ui'
            georef = path.name == 'qgsgeorefpluginguibase.ui'
            key = name if mainWindow else 'georeferencer:'+name if georef else path.relative_to(SOURCE).as_posix()+':'+name
            ui.append(dict(source=path.relative_to(SOURCE).as_posix(), name=name, key=key,
                           text=action.findtext("property[@name='text']/string", ''),
                           inventoried=(name in static if mainWindow else key in dynamic),
                           review='GPS excluded' if re.search('gps|gpx', name, re.I) else
                                  'main/georeferencer explicit inventory' if mainWindow or georef else
                                  'requires runtime/delegation review'))
    cpp = []
    pattern = re.compile(r'\b(\w+)\s*=\s*(?:new\s+QAction\s*\(|\w+->addAction\s*\(\s*tr\s*\()')
    for path in sorted((SOURCE/'src/app').rglob('*.cpp')):
        content = path.read_text(encoding='utf-8')
        for match in pattern.finditer(content):
            cpp.append(dict(source=path.relative_to(SOURCE).as_posix(), name=match[1],
                            line=content.count('\n', 0, match.start())+1,
                            snippet=content[match.start():content.find('\n', match.start())].strip()))
    payload = dict(version='3.34.10', scope='All src/ui action declarations and candidate src/app C++ constructors; not a complete runtime census.',
                   missingMainUi=[a['name'] for a in ui if a['source']=='src/ui/qgisapp.ui' and not a['inventoried']],
                   uiActions=ui, cppCandidates=cpp,
                   confirmedMissing=[a['sourceKey'] for a in status.get('dynamicActions', []) if a['status'] == 'not-ported'],
                   caveat='C++ candidates can repeat, be platform-specific, or belong to native widgets. Do not classify them as unimplemented from regex matches alone.')
    (ROOT/'docs/action-source-audit.json').parent.mkdir(parents=True, exist_ok=True)
    (ROOT/'docs/action-source-audit.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(uiDeclarations=len(ui), cppCandidates=len(cpp), missingMainUi=payload['missingMainUi'],
                          confirmedMissing=payload['confirmedMissing']), ensure_ascii=False))


if __name__ == '__main__': main()
