"""Copy upstream resources and extract QgisApp::setTheme dynamic icon assignments."""
from pathlib import Path
import os
import json
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('QGIS_SOURCE_ROOT', r'C:\QGIS_COMPILE\QGIS-final-3_34_10'))
images = ROOT / 'images'
images.mkdir(exist_ok=True)
qrc = SOURCE / 'images/images.qrc'
for element in ET.parse(qrc).findall('.//file'):
    target = images / element.text
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / 'images' / element.text, target)
shutil.copyfile(qrc, images / 'images.qrc')
(images / 'splash').mkdir(exist_ok=True)
shutil.copyfile(SOURCE / 'images/splash/splash.png', images / 'splash/splash.png')
cpp = (SOURCE / 'src/app/qgisapp.cpp').read_text(encoding='utf-8')
icons = dict(re.findall(r'(m\w+)->setIcon\(\s*QgsApplication::getThemeIcon\(\s*QStringLiteral\(\s*"([^"]+)"', cpp))
(ROOT / 'manifests/upstream-icons.json').write_text(json.dumps(icons, indent=2), encoding='utf-8')
(images / '__init__.py').write_text('"""QGIS image resources and QgisApp::setTheme icon assignments."""\nTHEME_ICONS = ' + repr(icons) + '\n', encoding='utf-8')
print(f'Copied QGIS resources and {len(icons)} dynamic icon assignments.')
