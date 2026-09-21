"""Copy the exact 3.34.10 UI, strip GPS and record upstream action/slot mapping."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('QGIS_SOURCE_ROOT', r'C:\QGIS_COMPILE\QGIS-final-3_34_10'))

# Actions deliberately outside the port, reported as excluded rather than as
# pending work: the 3D map views, which the project scope excludes with GPS.
OUT_OF_SCOPE_ACTIONS = {'mActionNew3DMapCanvas', 'mActionManage3DMapViews'}


def main():
    uiPath = SOURCE / 'src/ui/qgisapp.ui'
    cppPath = SOURCE / 'src/app/qgisapp.cpp'
    tree = ET.parse(uiPath)
    root = tree.getroot()
    actions = []
    cpp = cppPath.read_text(encoding='utf-8')
    slots = dict(re.findall(r'connect\(\s*(mAction\w+),\s*&QAction::\w+,\s*this,\s*&QgisApp::(\w+)', cpp))
    excluded = {e.get('name') for e in root.iter() if re.search('gps|gpx', e.get('name', ''), re.I)}
    # 3D map views are out of scope by decision, exactly like GPS; keeping them
    # here means regenerating the manifest does not turn them into pending work.
    excluded |= {name for name in
                 (e.get('name') for e in root.iter()) if name in OUT_OF_SCOPE_ACTIONS}
    for e in root.findall('.//action'):
        name = e.get('name')
        actions.append({'objectName': name, 'text': e.findtext("property[@name='text']/string", ''),
                        'cppSlot': slots.get(name), 'excluded': name in excluded})
    for parent in root.iter():
        for child in list(parent):
            if child.get('name') in excluded or child.tag == 'resources':
                parent.remove(child)
            elif child.tag == 'iconset':
                child.attrib.pop('resource', None)
    target = ROOT / 'src/ui/qgisapp.ui'
    target.parent.mkdir(parents=True, exist_ok=True)
    tree.write(target, encoding='utf-8', xml_declaration=True)
    rasterUi = ET.parse(SOURCE / 'src/ui/qgsrastercalcdialogbase.ui')
    for header in rasterUi.findall('.//customwidget/header'): header.text = 'qgis.gui'
    custom = ET.SubElement(rasterUi.find('customwidgets'), 'customwidget')
    ET.SubElement(custom, 'class').text = 'QgsScrollArea'
    ET.SubElement(custom, 'extends').text = 'QScrollArea'
    ET.SubElement(custom, 'header').text = 'qgis.gui'
    rasterUi.write(ROOT / 'src/ui/qgsrastercalcdialogbase.ui', encoding='utf-8', xml_declaration=True)
    measureUi = ET.parse(SOURCE / 'src/ui/qgsmeasurebase.ui')
    for header in measureUi.findall('.//customwidget/header'): header.text = 'qgis.gui'
    measureUi.write(ROOT / 'src/ui/qgsmeasurebase.ui', encoding='utf-8', xml_declaration=True)
    statisticsUi = ET.parse(SOURCE / 'src/ui/qgsstatisticalsummarybase.ui')
    for header in statisticsUi.findall('.//customwidget/header'): header.text = 'qgis.gui'
    statisticsUi.write(ROOT / 'src/ui/qgsstatisticalsummarybase.ui', encoding='utf-8', xml_declaration=True)
    for relative in ('qgsannotationwidgetbase.ui', 'qgstextannotationdialogbase.ui',
                     'qgsformannotationdialogbase.ui', 'qgsprojectlayergroupdialogbase.ui',
                     'annotations/qgsannotationlayerpropertiesbase.ui',
                     'annotations/qgsannotationitempropertieswidgetbase.ui',
                     'qgsdxfexportdialogbase.ui', 'qgsnewspatialitelayerdialogbase.ui',
                     'mesh/qgsmeshcalculatordialogbase.ui', 'mesh/qgsnewmeshlayerdialogbase.ui'):
        annotationUi = ET.parse(SOURCE / 'src/ui' / relative)
        for header in annotationUi.findall('.//customwidget/header'): header.text = 'qgis.gui'
        for widget in annotationUi.findall('.//customwidget'):
            if widget.findtext('class') == 'QgsProviderConnectionComboBox':
                widget.find('header').text = 'src.gui.qgsproviderconnectioncombobox'
        # The application already loads images.images_rc before creating its UI.
        for resources in annotationUi.findall('resources'): annotationUi.getroot().remove(resources)
        target = ROOT / 'src/ui' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        annotationUi.write(target, encoding='utf-8', xml_declaration=True)
    docs = ROOT / 'docs'
    docs.mkdir(exist_ok=True)
    manifest = {'version': '3.34.10', 'tag': 'final-3_34_10',
                'uiSHA256': hashlib.sha256(uiPath.read_bytes()).hexdigest(),
                'cppSHA256': hashlib.sha256(cppPath.read_bytes()).hexdigest(),
                'actions': actions}
    (root / 'manifests' / 'upstream-actions.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(SOURCE / 'LICENSE', ROOT / 'LICENSE')
    print(f'Imported {len(actions)} upstream actions; removed {len(excluded)} GPS/GPX objects.')


if __name__ == '__main__':
    main()
