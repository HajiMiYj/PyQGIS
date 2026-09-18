"""Verify db_manager and MetaSearch plugin import chains resolve on OSGeo4W."""
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from qgis.core import QgsApplication, Qgis
app = QgsApplication([], False)
app.setPrefixPath('C:/OSGeo4W/apps/qgis-ltr', True)
app.initQgis()
from qgis.gui import QgsGui
QgsGui.editorWidgetRegistry().initEditors()

# Ensure the plugins dir is importable exactly like main.py does.
sys.path.insert(0, 'C:/OSGeo4W/apps/qgis-ltr/python/plugins')

from db_manager import classFactory as dbFactory
print('db_manager classFactory OK ->', dbFactory)

from MetaSearch import classFactory as msFactory
print('MetaSearch classFactory OK ->', msFactory)

from MetaSearch.plugin import MetaSearchPlugin
from MetaSearch.dialogs.maindialog import MetaSearchDialog
from MetaSearch.util import get_help_url, open_url, StaticContext
print('MetaSearch import chain OK')

from db_manager.db_manager_plugin import DBManagerPlugin
from db_manager.db_manager import DBManager
print('db_manager import chain OK')

app.exitQgis()
print('ALL IMPORTS OK')
