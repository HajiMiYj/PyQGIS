"""Probe the native source-select provider registry keys and page names."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import QgsApplication, QgsProviderRegistry
app = QgsApplication([], False)
app.setPrefixPath('C:/OSGeo4W/apps/qgis-ltr', True)
app.initQgis()
from qgis.gui import QgsGui
QgsGui.editorWidgetRegistry().initEditors()

reg = QgsGui.sourceSelectProviderRegistry()
print('=== sourceSelectProviderRegistry providers ===')
for p in reg.providers():
    try:
        print(f'  key={p.providerKey()!r}  name={p.name()!r}  text={p.text()!r}')
    except Exception as e:
        print('  ERR', e)

print('=== provider keys from QgsProviderRegistry ===')
pr = QgsProviderRegistry.instance()
for key in sorted(pr.providerList()):
    try:
        print(f'  {key!r}  ->  {pr.fileVectorFilters(key) or pr.fileRasterFilters(key) or ""}')
    except Exception:
        print(f'  {key!r}')

app.exitQgis()
