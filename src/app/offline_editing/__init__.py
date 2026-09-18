"""Offline editing: dialog, progress dialog and plugin actions.

Port of src/plugins/offline_editing. The native plugin is a C++ core plugin whose
logic lives entirely in QgsOfflineEditing, which is available from PyQGIS, so the
whole plugin is reproduced here instead of loading plugin_offlineediting.dll.
"""
