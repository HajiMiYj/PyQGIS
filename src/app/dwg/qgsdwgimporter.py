"""Python CAD import backend for QgsDwgImportDialog.

QGIS 3.34's libdxfrw-based QgsDwgImporter is not SIP-exported. This backend
uses the installed GDAL DXF/CAD readers. Its GeoPackage geometry tables use
the native dialog's names; reader limitations remain explicit in the UI.
"""
from contextlib import contextmanager
import json
import math
import codecs
import os
from pathlib import Path
import re
import tempfile

from osgeo import gdal, ogr, osr


class QgsDwgImporter:
    TABLES = ('hatches', 'lines', 'polylines', 'texts', 'points', 'inserts')
    FIELDS = {
        'layer': ogr.OFTString, 'space': ogr.OFTInteger, 'block': ogr.OFTInteger,
        'color': ogr.OFTString, 'linewidth': ogr.OFTReal, 'text': ogr.OFTString,
        'height': ogr.OFTReal, 'angle': ogr.OFTReal, 'font': ogr.OFTString,
        'style': ogr.OFTString, 'source_layer': ogr.OFTString,
        'source_fid': ogr.OFTInteger64, 'attributes': ogr.OFTString,
        'linewidth_unit': ogr.OFTString, 'dash_pattern': ogr.OFTString,
        'dash_unit': ogr.OFTString, 'capstyle': ogr.OFTString, 'joinstyle': ogr.OFTString,
        'height_unit': ogr.OFTString, 'hali': ogr.OFTString, 'vali': ogr.OFTString,
        'bold': ogr.OFTInteger, 'italic': ogr.OFTInteger,
        'underline': ogr.OFTInteger, 'strikeout': ogr.OFTInteger,
    }

    def __init__(self, database, crs):
        self.mDatabase = str(database)
        self.mCrs = crs
        self.mWarnings = []
        self.mCounts = {}
        self.mDriver = ''
        self.mDxfEncoding = None

    @staticmethod
    @contextmanager
    def readerOptions(expandInserts, encoding=None):
        # Thread-local options must cover both opening and feature iteration.
        # Do not change how other QGIS providers open DXF files afterwards.
        options = {'DXF_INLINE_BLOCKS': 'TRUE' if expandInserts else 'FALSE',
                   'DXF_MERGE_BLOCK_GEOMETRIES': 'FALSE'}
        if encoding: options['DXF_ENCODING'] = encoding
        previous = {key: gdal.GetThreadLocalConfigOption(key) for key in options}
        try:
            for key, value in options.items(): gdal.SetThreadLocalConfigOption(key, value)
            yield
        finally:
            for key, value in previous.items(): gdal.SetThreadLocalConfigOption(key, value)

    @staticmethod
    def styleProperties(style, tool):
        # Preserve the complete OGR style too; this only extracts basic drawing
        # colors/widths/text. Quoted commas and escaped quotes stay intact.
        match = re.search(r'\b' + tool + r'\(((?:"(?:\\.|[^"\\])*"|[^)])*)\)', style or '', re.IGNORECASE)
        if not match: return {}
        values = {}
        for token in re.finditer(r'(\w+):("(?:\\.|[^"\\])*"|[^,]*)', match.group(1)):
            value = token.group(2).strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            values[token.group(1).lower()] = value
        return values

    @staticmethod
    def number(value, default=0.0):
        match = re.match(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?', str(value or ''))
        result = float(match.group()) if match else default
        return result if math.isfinite(result) else default

    @classmethod
    def styleSize(cls, text, default=0.0, defaultUnit='mm'):
        """Normalize paper sizes to mm while retaining ground-unit sizes."""
        text = str(text or '').strip().lower()
        match = re.search(r'(g|px|pt|mm|cm|in)\s*$', text)
        unit = match.group(1) if match else defaultUnit
        value = cls.number(text, default)
        if unit == 'g': return value, 'MapUnit'
        return value * {'px': 25.4/96, 'pt': 25.4/72, 'mm': 1, 'cm': 10, 'in': 25.4}[unit], 'MM'

    @staticmethod
    def styleColor(value):
        # OGR uses RRGGBBAA, whereas Qt interprets eight-digit hex as AARRGGBB.
        if re.fullmatch(r'#[0-9a-fA-F]{8}', value or ''):
            return ','.join(str(int(value[i:i+2], 16)) for i in (1, 3, 5, 7))
        return value or '#000000'

    @classmethod
    def styleFields(cls, style):
        label, pen = cls.styleProperties(style, 'LABEL'), cls.styleProperties(style, 'PEN')
        brush, symbol = cls.styleProperties(style, 'BRUSH'), cls.styleProperties(style, 'SYMBOL')
        width, widthUnit = cls.styleSize(pen.get('w'), 0.25)
        height, heightUnit = cls.styleSize(label.get('s'), 1, 'g')
        pattern = pen.get('p', '').strip()
        unitMatch = re.search(r'(g|px|pt|mm|cm|in)$', pattern, re.I)
        dashUnit, dashValues = 'MM', []
        if unitMatch:
            for value in pattern[:unitMatch.start()].split():
                length, dashUnit = cls.styleSize(value + unitMatch.group())
                if length < 0: dashValues = []; break
                dashValues.append(length)
        if len(dashValues) % 2 or not any(dashValues): dashValues = []
        anchor = int(cls.number(label.get('p'), 10))
        if not 1 <= anchor <= 12: anchor = 10
        return {
            'color': cls.styleColor(label.get('c') or pen.get('c') or brush.get('fc') or symbol.get('c')),
            'linewidth': max(0, width), 'linewidth_unit': widthUnit,
            'height': max(0, height), 'height_unit': heightUnit,
            'angle': cls.number(label.get('a')), 'font': label.get('f', '').split(',')[0].strip(),
            'hali': ('Left', 'Center', 'Right')[(anchor-1) % 3],
            'vali': ('Bottom', 'Half', 'Top', 'Base')[(anchor-1) // 3],
            'bold': int(cls.number(label.get('bo')) != 0), 'italic': int(cls.number(label.get('it')) != 0),
            'underline': int(cls.number(label.get('un')) != 0), 'strikeout': int(cls.number(label.get('st')) != 0),
            'dash_pattern': ';'.join(format(value, '.15g') for value in dashValues), 'dash_unit': dashUnit,
            'capstyle': {'r': 'round', 'p': 'square'}.get(pen.get('cap', '').lower(), 'flat'),
            'joinstyle': {'r': 'round', 'b': 'bevel'}.get(pen.get('j', '').lower(), 'miter'),
        }

    def readDxfLayerTable(self, drawing, progress=None):
        """Read ASCII DXF LAYER records, retaining off/frozen/locked flags.

        Geometry still comes exclusively from GDAL. Binary DXF/DWG keep the
        driver fallback instead of guessing a binary record layout.
        """
        if Path(drawing).suffix.lower() != '.dxf': return {}
        result, section, record, values, variable = {}, '', '', {}, ''
        encoding, version = 'cp1252', ''
        override = gdal.GetConfigOption('DXF_ENCODING')
        def saveLayer():
            if section != 'TABLES' or record != 'LAYER' or 2 not in values: return
            name = values[2].decode(override or encoding, errors='strict')
            name = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), name)
            result[name] = {'ocolor': int(values.get(62, b'7')), 'flags': int(values.get(70, b'0'))}
        try:
            with Path(drawing).open('rb') as stream:
                if stream.read(22).startswith(b'AutoCAD Binary DXF'):
                    self.mWarnings.append('二进制 DXF 的原始图层隐藏/冻结状态暂未读取。')
                    return {}
                stream.seek(0)
                count = 0
                while True:
                    codeLine = stream.readline()
                    if not codeLine: break
                    raw = stream.readline()
                    if not raw: raise ValueError('不完整的 DXF 组码')
                    code, value = int(codeLine.strip()), raw.rstrip(b'\r\n')
                    count += 1
                    if progress and count % 2048 == 0 and progress(0) is False: raise InterruptedError('已取消导入。')
                    if code == 0:
                        saveLayer()
                        record, values = value.decode('ascii').strip().upper(), {}
                        if record == 'ENDSEC':
                            if section == 'TABLES': break
                            section = ''
                    elif record == 'SECTION' and code == 2:
                        section = value.decode('ascii').strip().upper()
                        if section in ('BLOCKS', 'ENTITIES'): break
                    if section == 'HEADER':
                        if code == 9: variable = value.decode('ascii').strip()
                        elif variable == '$ACADVER' and code == 1:
                            version = value.decode('ascii').strip()
                            if version >= 'AC1021': encoding = 'utf-8'
                        elif variable == '$DWGCODEPAGE' and code == 3 and version < 'AC1021':
                            page = value.decode('ascii').strip()
                            candidate = re.sub(r'^(ANSI_|DOS)', 'cp', page, flags=re.I)
                            codecs.lookup(candidate)
                            encoding = candidate
                    values[code] = value
        except (OSError, ValueError, LookupError, UnicodeError) as error:
            self.mWarnings.append(f'无法完整读取 DXF 图层状态，使用已解析状态与驱动默认值：{error}')
        self.mDxfEncoding = override or encoding
        return result

    def importDrawing(self, drawing, expandInserts=True, useCurves=False,
                      addInsertPoints=False, progress=None):
        """Write a new package atomically. Raise on failure or cancellation.

        Python cannot name a method `import`, as the C++ importer does.
        Existing packages are never overwritten; the dialog can load them.
        """
        drawing, destination = Path(drawing), Path(self.mDatabase)
        if not drawing.is_file(): raise ValueError('源图纸不存在。')
        if destination.suffix.lower() != '.gpkg': raise ValueError('目标文件必须是 .gpkg。')
        if destination.exists(): raise FileExistsError('目标文件已存在，请加载已有包，或选择新的 GeoPackage 文件名。')
        if not self.mCrs.isValid(): raise ValueError('请先选择图纸的坐标参考系。')
        if useCurves: raise ValueError('当前读取后端不能保证原版曲线导入，请关闭“使用曲线”。')
        if drawing.suffix.lower() != '.dxf' and (not expandInserts or addInsertPoints):
            raise ValueError('DWG 读取后端暂不支持选择块插入模式。')
        self.mWarnings, self.mCounts = [], {}
        self.mDriver = ''
        self.mDxfEncoding = None
        layerStates = self.readDxfLayerTable(drawing, progress)
        descriptor, tempName = tempfile.mkstemp(prefix='.' + destination.stem + '-', suffix='.gpkg', dir=destination.parent)
        os.close(descriptor)
        os.unlink(tempName)
        package = None
        tables, layerNames = {}, set()
        try:
            driver = ogr.GetDriverByName('GPKG')
            if driver is None: raise RuntimeError('OSGeo 环境缺少 GeoPackage 驱动。')
            package = driver.CreateDataSource(tempName)
            if package is None: raise RuntimeError(gdal.GetLastErrorMsg())
            srs = osr.SpatialReference()
            with osr.ExceptionMgr():
                if srs.ImportFromWkt(self.mCrs.toWkt()) != 0: raise ValueError('无法写入图纸 CRS。')
            if package.StartTransaction() != 0: raise RuntimeError('无法开始 GeoPackage 事务。')
            passes = [(expandInserts, False)]
            if expandInserts and addInsertPoints: passes.append((False, True))
            count, missing = 0, 0
            for expand, insertsOnly in passes:
                with self.readerOptions(expand, self.mDxfEncoding):
                    source = None
                    gdal.PushErrorHandler('CPLQuietErrorHandler')
                    try:
                        source = gdal.OpenEx(str(drawing), gdal.OF_VECTOR | gdal.OF_READONLY,
                                             allowed_drivers=['DXF', 'CAD', 'DWG'])
                        if source is None:
                            raise RuntimeError(gdal.GetLastErrorMsg() or '当前 CAD 驱动无法读取此图纸版本。')
                        self.mDriver = source.GetDriver().ShortName
                        for index in range(source.GetLayerCount()):
                            sourceLayer = source.GetLayer(index)
                            # The non-inline DXF blocks table holds definitions,
                            # not positioned model-space entities.
                            if sourceLayer.GetName().lower() == 'blocks': continue
                            for feature in sourceLayer:
                                if progress and count % 128 == 0 and progress(count) is False:
                                    raise InterruptedError('已取消导入。')
                                count += 1
                                attributes = feature.items()
                                values = {key.lower(): value for key, value in attributes.items()}
                                insert = bool(values.get('blockname'))
                                if insertsOnly and not insert: continue
                                if values.get('paperspace'): continue
                                geometry = feature.GetGeometryRef()
                                if geometry is None or geometry.IsEmpty():
                                    missing += 1
                                    continue
                                style = feature.GetStyleString() or ''
                                label = self.styleProperties(style, 'LABEL')
                                pen = self.styleProperties(style, 'PEN')
                                brush = self.styleProperties(style, 'BRUSH')
                                symbol = self.styleProperties(style, 'SYMBOL')
                                layerName = str(values.get('layer') or sourceLayer.GetName())
                                text = str(values.get('text') or label.get('t') or '')
                                row = {'layer': layerName, 'space': 0, 'block': -1,
                                       'color': label.get('c') or pen.get('c') or brush.get('fc') or symbol.get('c') or '#000000',
                                       'linewidth': self.number(pen.get('w'), 0.25),
                                       'height': self.number(label.get('s'), 1), 'angle': self.number(label.get('a')),
                                       'font': label.get('f', ''), 'text': text, 'style': style,
                                       'source_layer': sourceLayer.GetName(), 'source_fid': feature.GetFID(),
                                       'attributes': json.dumps(attributes, ensure_ascii=False, default=str)}
                                row.update(self.styleFields(style))
                                state = layerStates.get(layerName, {})
                                if state.get('ocolor', 7) < 0 or state.get('flags', 0) & 1:
                                    # GDAL represents an off/frozen layer using
                                    # transparent entity colors. Visibility now
                                    # belongs to the layer tree, so it is reversible.
                                    color = row['color'].split(',')
                                    if len(color) == 4 and color[3] == '0':
                                        row['color'] = ','.join(color[:3] + ['255'])
                                def writeGeometry(part):
                                    nonlocal missing
                                    flat = ogr.GT_Flatten(part.GetGeometryType())
                                    if flat == ogr.wkbGeometryCollection:
                                        for n in range(part.GetGeometryCount()): writeGeometry(part.GetGeometryRef(n))
                                        return
                                    if flat in (ogr.wkbPoint, ogr.wkbMultiPoint):
                                        table = 'inserts' if insert and not expand else 'texts' if text else 'points'
                                    elif flat in (ogr.wkbLineString, ogr.wkbMultiLineString, ogr.wkbCircularString, ogr.wkbCompoundCurve, ogr.wkbMultiCurve):
                                        table = 'lines'
                                    elif flat in (ogr.wkbPolygon, ogr.wkbMultiPolygon, ogr.wkbCurvePolygon, ogr.wkbMultiSurface):
                                        table = 'hatches'
                                    else:
                                        missing += 1
                                        return
                                    if table not in tables:
                                        target = package.CreateLayer(table, srs, ogr.wkbUnknown)
                                        if target is None: raise RuntimeError(gdal.GetLastErrorMsg())
                                        for name, kind in self.FIELDS.items():
                                            if target.CreateField(ogr.FieldDefn(name, kind)) != 0: raise RuntimeError(gdal.GetLastErrorMsg())
                                        tables[table] = target
                                    target = tables[table]
                                    output = ogr.Feature(target.GetLayerDefn())
                                    for name, value in row.items(): output.SetField(name, value)
                                    output.SetGeometry(part)
                                    if target.CreateFeature(output) != 0: raise RuntimeError(gdal.GetLastErrorMsg())
                                    self.mCounts[table] = self.mCounts.get(table, 0) + 1
                                    layerNames.add(layerName)
                                writeGeometry(geometry)
                            feature, sourceLayer, geometry = None, None, None
                    finally:
                        source = None
                        gdal.PopErrorHandler()
            if not self.mCounts: raise ValueError('未读到可导入的模型空间几何。')
            metadata = package.CreateLayer('layers', geom_type=ogr.wkbNone)
            for name, kind in (('name', ogr.OFTString), ('ocolor', ogr.OFTInteger), ('flags', ogr.OFTInteger)):
                if metadata.CreateField(ogr.FieldDefn(name, kind)) != 0: raise RuntimeError(gdal.GetLastErrorMsg())
            for name in sorted(layerNames | set(layerStates)):
                feature = ogr.Feature(metadata.GetLayerDefn())
                feature.SetField('name', name)
                feature.SetField('ocolor', layerStates.get(name, {}).get('ocolor', 7))
                feature.SetField('flags', layerStates.get(name, {}).get('flags', 0))
                if metadata.CreateFeature(feature) != 0: raise RuntimeError(gdal.GetLastErrorMsg())
            feature, metadata = None, None
            if progress and progress(count) is False: raise InterruptedError('已取消导入。')
            if package.CommitTransaction() != 0: raise RuntimeError(gdal.GetLastErrorMsg())
            tables.clear()
            if package.Close() != 0: raise RuntimeError('GeoPackage 关闭失败，未发布目标文件。')
            package = None
            if destination.exists(): raise FileExistsError('目标文件已被创建，请选择新的文件名。')
            os.rename(tempName, destination)
            if missing: self.mWarnings.append(f'{missing} 个无几何或不支持的几何未导入。')
            return dict(self.mCounts)
        finally:
            tables.clear()
            if package is not None: package.Close()
            package = None
            for suffix in ('', '-wal', '-shm', '-journal'):
                temporary = Path(tempName + suffix)
                if temporary.exists(): temporary.unlink()
