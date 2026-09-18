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
    # DWG/DXF version tags, used to report what the installed driver can read.
    # GDAL's CAD driver (libopencad) covers R2000; later tags are reported instead
    # of surfacing an opaque driver error.
    CAD_VERSIONS = {
        'AC1006': 'R10', 'AC1009': 'R11/R12', 'AC1012': 'R13', 'AC1014': 'R14',
        'AC1015': 'R2000', 'AC1018': 'R2004', 'AC1021': 'R2007', 'AC1024': 'R2010',
        'AC1027': 'R2013', 'AC1032': 'R2018',
    }
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
        self.mSourceVersion = ''

    @classmethod
    def describeVersion(cls, tag):
        """Human readable name for an AC#### version tag."""
        tag = (tag or '').strip().upper()
        return f'{tag} ({cls.CAD_VERSIONS[tag]})' if tag in cls.CAD_VERSIONS else tag

    @classmethod
    def readDwgVersion(cls, drawing):
        """The version tag stored in a DWG header's first six bytes."""
        try:
            with Path(drawing).open('rb') as stream:
                tag = stream.read(6).decode('ascii', 'ignore').strip().upper()
        except OSError:
            return ''
        return tag if re.fullmatch(r'AC\d{4}', tag or '') else ''

    def sourceVersion(self, drawing):
        """Detected drawing version, from the DXF header or the DWG header."""
        if Path(drawing).suffix.lower() == '.dwg':
            self.mSourceVersion = self.readDwgVersion(drawing)
        return self.mSourceVersion

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

    @staticmethod
    def iterDxfPairs(stream, progress=None):
        """Yield (group code, raw value, binary flag) pairs from an ASCII *or* binary DXF.

        Binary DXF (sentinel "AutoCAD Binary DXF") stores the group code in one
        byte, or as 0xFF plus a little-endian 16-bit code, followed by a value
        whose layout depends on the group-code range. Native reads both through
        libdxfrw; GDAL only surfaces the parsed result, so the raw records are
        read here. The binary flag matters: an ASCII value like b'0' would be
        mistaken for binary data if only its byte length were considered.
        """
        import struct
        sentinel = stream.read(22)
        binary = sentinel.startswith(b'AutoCAD Binary DXF')
        if not binary:
            stream.seek(0)
        count = 0
        while True:
            if binary:
                header = stream.read(1)
                if not header: return
                code = header[0]
                if code == 0xFF:
                    raw = stream.read(2)
                    if len(raw) < 2: return
                    code = struct.unpack('<H', raw)[0]
            else:
                codeLine = stream.readline()
                if not codeLine: return
                code = int(codeLine.strip())
            count += 1
            if progress and count % 4096 == 0 and progress(0) is False:
                raise InterruptedError('已取消导入。')
            if not binary:
                raw = stream.readline()
                if not raw: raise ValueError('不完整的 DXF 组码')
                yield code, raw.rstrip(b'\r\n'), False
                continue
            yield code, QgsDwgImporter.binaryDxfValue(stream, code), True

    @staticmethod
    def binaryDxfValue(stream, code):
        """Read one binary DXF value whose layout follows from its group code."""
        import struct
        def take(size):
            raw = stream.read(size)
            if len(raw) < size: raise ValueError('不完整的二进制 DXF 值')
            return raw
        if 0 <= code <= 9 or code in (100, 102, 105) or 300 <= code <= 309 \
                or 320 <= code <= 369 or 390 <= code <= 399 or 410 <= code <= 419 \
                or 430 <= code <= 439 or 470 <= code <= 481 or code == 999 \
                or 1000 <= code <= 1009:
            if 310 <= code <= 319:
                return take(take(1)[0])
            raw, chunk = b'', b''
            while True:
                chunk = take(1)
                if chunk in (b'\x00', b''): break
                raw += chunk
            return raw
        if 310 <= code <= 319: return take(take(1)[0])
        if 10 <= code <= 59 or 110 <= code <= 149 or 210 <= code <= 239 \
                or 460 <= code <= 469 or 1010 <= code <= 1059:
            return take(8)
        if 60 <= code <= 79 or 170 <= code <= 179 or 270 <= code <= 289 \
                or 370 <= code <= 389 or 400 <= code <= 409 or 1060 <= code <= 1070:
            return take(2)
        if 90 <= code <= 99 or 420 <= code <= 429 or 440 <= code <= 459 or code == 1071:
            return take(4)
        if 160 <= code <= 169:
            return take(8)
        if 290 <= code <= 299:
            return take(1)
        return take(1)

    @staticmethod
    def pairNumber(raw, default=0.0, binary=False, code=None):
        """Numeric value of a group code, respecting the DXF flavour.

        Eight-byte binary values are int64 only for the 160-169 range; every
        other eight-byte range holds a double.
        """
        import struct
        if not binary:
            try:
                return float(bytes(raw).decode('ascii', 'ignore').strip() or default)
            except ValueError:
                return default
        if len(raw) == 8:
            if code is not None and 160 <= code <= 169: return float(struct.unpack('<q', raw)[0])
            return struct.unpack('<d', raw)[0]
        if len(raw) == 4: return float(struct.unpack('<i', raw)[0])
        if len(raw) == 2: return float(struct.unpack('<h', raw)[0])
        if len(raw) == 1: return float(raw[0])
        try: return float(bytes(raw).decode('ascii', 'ignore').strip() or default)
        except ValueError: return default

    @staticmethod
    def pairText(raw, encoding='utf-8'):
        return raw.decode(encoding, errors='replace') if isinstance(raw, bytes) else str(raw)

    def readDxfLayerTable(self, drawing, progress=None):
        """Read LAYER table records, retaining off/frozen/locked flags.

        Works for ASCII and binary DXF. Geometry still comes from GDAL; this only
        recovers the raw layer state GDAL does not expose.
        """
        result, section, record, values, variable = {}, '', '', {}, ''
        encoding, version = 'cp1252', ''
        override = gdal.GetConfigOption('DXF_ENCODING')
        def saveLayer():
            if section != 'TABLES' or record != 'LAYER' or 2 not in values: return
            name = self.pairText(values[2], override or encoding)
            name = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), name)
            result[name] = {'ocolor': int(self.pairNumber(values.get(62), 7, binary, 62)),
                            'flags': int(self.pairNumber(values.get(70), 0, binary, 70))}
        try:
            with Path(drawing).open('rb') as stream:
                for code, raw, binary in self.iterDxfPairs(stream, progress):
                    if code == 0:
                        saveLayer()
                        record, values = self.pairText(raw, 'ascii').strip().upper(), {}
                        if record == 'ENDSEC':
                            if section == 'TABLES': break
                            section = ''
                    elif record == 'SECTION' and code == 2:
                        section = self.pairText(raw, 'ascii').strip().upper()
                        if section in ('BLOCKS', 'ENTITIES'): break
                    if section == 'HEADER':
                        if code == 9: variable = self.pairText(raw, 'ascii').strip()
                        elif variable == '$ACADVER' and code == 1:
                            version = self.pairText(raw, 'ascii').strip()
                            self.mSourceVersion = version
                            if version >= 'AC1021': encoding = 'utf-8'
                        elif variable == '$DWGCODEPAGE' and code == 3 and version < 'AC1021':
                            page = self.pairText(raw, 'ascii').strip()
                            candidate = re.sub(r'^(ANSI_|DOS)', 'cp', page, flags=re.I)
                            codecs.lookup(candidate)
                            encoding = candidate
                    values[code] = raw
        except (OSError, ValueError, LookupError, UnicodeError) as error:
            self.mWarnings.append(f'无法完整读取 DXF 图层状态，使用已解析状态与驱动默认值：{error}')
        self.mDxfEncoding = override or encoding
        return result

    @staticmethod
    def circularStringWkt(points):
        z = points[0][2] is not None
        coordinates = ','.join(f'{p[0]:.15g} {p[1]:.15g}' + (f' {p[2]:.15g}' if z else '') for p in points)
        return ('CIRCULARSTRING Z (' if z else 'CIRCULARSTRING (') + coordinates + ')'

    @staticmethod
    def arcPoints(centre, radius, startDegrees, endDegrees, z=None):
        """Three points describing the counter-clockwise DXF arc.

        DXF arcs sweep counter-clockwise, which is also what CIRCULARSTRING
        requires, so start, apex and end are emitted in that order.
        """
        sweep = (endDegrees - startDegrees) % 360.0
        if sweep == 0.0: sweep = 360.0
        def point(angle):
            radians = math.radians(angle)
            return (centre[0] + radius * math.cos(radians), centre[1] + radius * math.sin(radians), z)
        return [point(startDegrees), point(startDegrees + sweep / 2.0), point(startDegrees + sweep)]

    @staticmethod
    def bulgeApex(first, second, bulge):
        """Mid point of the arc described by a polyline bulge (DXF group code 42)."""
        return ((first[0] + second[0]) / 2.0 + bulge * (second[1] - first[1]) / 2.0,
                (first[1] + second[1]) / 2.0 - bulge * (second[0] - first[0]) / 2.0)

    @classmethod
    def polylineCurveWkt(cls, vertices, bulges, closed, z=None, elevations=None):
        """COMPOUNDCURVE for a polyline whose vertices may carry bulge arcs.

        ``elevations`` holds per-vertex Z for 3D polylines (each VERTEX carries its
        own code 30); ``z`` is the constant elevation of a 2D polyline.
        """
        def level(index):
            if elevations is not None and index < len(elevations): return elevations[index]
            return z
        points = [(x, y, level(index)) for index, (x, y) in enumerate(vertices)]
        if closed and points and vertices[0] != vertices[-1]:
            points.append(points[0])
            # The last vertex's bulge describes the closing segment.
            bulges = list(bulges) + [bulges[-1] if bulges else 0.0]
        if len(points) < 2: return None
        parts, run = [], [points[0]]
        for index in range(len(points) - 1):
            bulge = bulges[index] if index < len(bulges) else 0.0
            if abs(bulge) < 1e-12:
                run.append(points[index + 1])
                continue
            if len(run) > 1: parts.append(('line', run))
            run = [points[index + 1]]
            apex = cls.bulgeApex(points[index], points[index + 1], bulge)
            parts.append(('arc', [points[index], (apex[0], apex[1], z), points[index + 1]]))
        if len(run) > 1: parts.append(('line', run))
        if not any(kind == 'arc' for kind, _ in parts):
            coordinates = ','.join(f'{p[0]:.15g} {p[1]:.15g}' + (f' {p[2]:.15g}' if p[2] is not None else '')
                                   for p in points)
            return ('LINESTRING Z (' if z is not None else 'LINESTRING (') + coordinates + ')'
        def render(part):
            kind, part_points = part
            if kind == 'arc': return cls.circularStringWkt(part_points)
            coordinates = ','.join(f'{p[0]:.15g} {p[1]:.15g}' + (f' {p[2]:.15g}' if p[2] is not None else '')
                                   for p in part_points)
            return ('(' if z is None else '(') + coordinates + ')'
        return ('COMPOUNDCURVE Z (' if z is not None else 'COMPOUNDCURVE (') + ','.join(render(p) for p in parts) + ')'

    def readDxfCurves(self, drawing, progress=None):
        """{entity handle: WKT} for entities the native importer keeps as curves.

        GDAL strokes arcs, circles and bulge polylines into dense polylines and
        offers no curve output, so those entities are parsed here and their
        geometry substituted into the matching GDAL feature by entity handle.
        Only circular arcs are representable (QGIS has no ellipse or spline curve
        geometry either, and native strokes both as well).
        """
        curves, record, values, vertices, bulges, levels = {}, None, {}, [], [], []
        flavour = {'binary': False}

        def number(code, default=0.0):
            return self.pairNumber(values[code], default, flavour['binary'], code) if code in values else default

        def current(default=0.0):
            """Value of the group code being read right now (values[] is one behind)."""
            return self.pairNumber(raw, default, flavour['binary'], code)

        def elevation(*codes):
            for code in codes:
                value = number(code, 0.0)
                if value: return value
            return None

        def closed():
            return bool(int(number(70)) & 1)

        def finish():
            nonlocal record, values, vertices, bulges, levels
            handle = self.pairText(values[5], 'ascii') if 5 in values else ''
            wkt = None
            if record == 'ARC':
                wkt = self.circularStringWkt(self.arcPoints(
                    (number(10), number(20)), number(40), number(50), number(51), elevation(30)))
            elif record == 'CIRCLE':
                wkt = self.circularStringWkt(self.arcPoints(
                    (number(10), number(20)), number(40), 0.0, 360.0, elevation(30)))
            elif record in ('LWPOLYLINE', 'POLYLINE'):
                # A 3D polyline stores one Z per VERTEX; the POLYLINE record only
                # carries a zero placeholder, so per-vertex values win when present.
                perVertex = levels if any(levels) else None
                wkt = self.polylineCurveWkt(vertices, bulges, closed(), elevation(30, 38), perVertex)
            if wkt and handle: curves[handle] = wkt
            record, values, vertices, bulges, levels = None, {}, [], [], []

        try:
            with Path(drawing).open('rb') as stream:
                for code, raw, binary in self.iterDxfPairs(stream, progress):
                    flavour['binary'] = binary
                    if code == 0:
                        name = self.pairText(raw, 'ascii').strip().upper()
                        if name == 'VERTEX' and record in ('POLYLINE', 'VERTEX'):
                            record = 'VERTEX'
                            continue
                        if name == 'SEQEND':
                            # SEQEND closes a POLYLINE; the vertices collected so
                            # far belong to it, and its values are still current.
                            record = 'POLYLINE'
                            finish()
                            continue
                        finish()
                        record = name
                        continue
                    if record == 'VERTEX':
                        # A vertex belongs to the surrounding POLYLINE record.
                        if code == 10:
                            vertices.append((current(), 0.0))
                            bulges.append(0.0)
                            levels.append(0.0)
                        elif code == 20 and vertices:
                            vertices[-1] = (vertices[-1][0], current())
                        elif code == 42 and bulges:
                            bulges[-1] = current()
                        elif code == 30 and levels:
                            levels[-1] = current()
                        else:
                            values.setdefault(code, raw)
                        continue
                    if record not in ('ARC', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE'): continue
                    if record == 'LWPOLYLINE' and code == 10:
                        vertices.append((current(), 0.0))
                        bulges.append(0.0)
                    elif record == 'LWPOLYLINE' and code == 20 and vertices:
                        vertices[-1] = (vertices[-1][0], current())
                    elif record == 'LWPOLYLINE' and code == 42 and bulges:
                        bulges[-1] = current()
                    values[code] = raw
                finish()
        except (OSError, ValueError, LookupError, UnicodeError) as error:
            self.mWarnings.append(f'无法完整读取 DXF 曲线实体，已退回驱动折线：{error}')
        return curves

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
        isDxf = drawing.suffix.lower() == '.dxf'
        if useCurves and not isDxf:
            raise ValueError('DWG 二进制格式不含 DXF 实体记录，无法保留原版曲线；请对 DXF 使用“使用曲线”，'
                             '或关闭该选项后导入 DWG。')
        if not isDxf and (not expandInserts or addInsertPoints):
            raise ValueError('DWG 读取后端（GDAL CAD）不支持选择块插入模式，请对 DXF 使用该选项。')
        self.mWarnings, self.mCounts = [], {}
        self.mDriver = ''
        self.mDxfEncoding = None
        self.mSourceVersion = ''
        version = self.sourceVersion(drawing)
        layerStates = self.readDxfLayerTable(drawing, progress)
        # GDAL never emits curve geometries, so the native "use curves" behaviour
        # is recovered by parsing the entities and substituting the matching
        # feature geometry by entity handle.
        curveGeometry = self.readDxfCurves(drawing, progress) if (useCurves and isDxf) else {}
        if curveGeometry:
            types = {}
            for wkt in curveGeometry.values():
                types[wkt.split(' ', 1)[0]] = types.get(wkt.split(' ', 1)[0], 0) + 1
            self.mWarnings.append('保留为真曲线：' + '、'.join(f'{name} {count}' for name, count in sorted(types.items())))
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
                        # Prefer READ_ALL for DWG: the CAD driver defaults to
                        # READ_FAST, which skips data an importer should see. Fall
                        # back to the driver default if the option is rejected.
                        attempts = [{'MODE': 'READ_ALL'}, {}] if not isDxf else [{}]
                        for openOptions in attempts:
                            options = {'open_options': openOptions} if openOptions else {}
                            source = gdal.OpenEx(str(drawing), gdal.OF_VECTOR | gdal.OF_READONLY,
                                                 allowed_drivers=['DXF', 'CAD', 'DWG'], **options)
                            if source is not None: break
                        if source is None:
                            detail = gdal.GetLastErrorMsg() or '当前 CAD 驱动无法读取此图纸。'
                            if version and not isDxf:
                                detail = (f'{detail} 图纸版本 {self.describeVersion(version)}；'
                                          f'GDAL CAD 驱动仅覆盖 R2000 及部分更早版本。')
                            raise RuntimeError(detail)
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
                                handle = str(values.get('entityhandle') or '')
                                if handle and handle in curveGeometry:
                                    curve = ogr.CreateGeometryFromWkt(curveGeometry[handle])
                                    if curve is not None and not curve.IsEmpty(): geometry = curve
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
