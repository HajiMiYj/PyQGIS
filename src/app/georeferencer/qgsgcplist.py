"""Read/write the QGIS GCP points format without modifying a partial load."""
import csv
import io
import math
import os
from pathlib import Path
import tempfile
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY
from qgis.analysis import QgsGcpPoint


class QgsGCPList(list):
    @staticmethod
    def loadGcps(filePath, defaultDestinationCrs):
        lines = Path(filePath).read_text(encoding='utf-8-sig').splitlines()
        crs = QgsCoordinateReferenceSystem(defaultDestinationCrs)
        if lines and lines[0].startswith('#CRS:'):
            value = lines.pop(0)[5:].strip()
            if value:
                crs = QgsCoordinateReferenceSystem(value)
                if not crs.isValid(): raise ValueError('控制点文件的 CRS 无效')
        if not lines: raise ValueError('控制点文件为空')
        reader = csv.reader(lines, delimiter=',' if ',' in lines[0] else '\t')
        header = next(reader)
        if [s.strip().lower() for s in header[:4]] != ['mapx', 'mapy', 'sourcex', 'sourcey']:
            raise ValueError('控制点表头应为 mapX,mapY,sourceX,sourceY')
        points = QgsGCPList()
        for number, row in enumerate(reader, 2):
            if not row: continue
            try:
                x, y, sx, sy = map(float, row[:4])
                if not all(math.isfinite(v) for v in (x, y, sx, sy)): raise ValueError()
                enabled = bool(int(row[4])) if len(row) >= 5 else True
            except (ValueError, IndexError): raise ValueError(f'控制点文件第 {number} 行无效') from None
            points.append(QgsGcpPoint(QgsPointXY(sx, sy), QgsPointXY(x, y), crs, enabled))
        return points, crs

    def saveGcps(self, filePath, targetCrs, context, residuals=()):
        buffer = io.StringIO()
        if targetCrs.isValid(): buffer.write('#CRS: ' + targetCrs.toWkt() + '\n')
        writer = csv.writer(buffer, lineterminator='\n')
        writer.writerow(('mapX', 'mapY', 'sourceX', 'sourceY', 'enable', 'dX', 'dY', 'residual'))
        for index, point in enumerate(self):
            destination = point.destinationPoint()
            if point.destinationPointCrs().isValid() and targetCrs.isValid() and point.destinationPointCrs() != targetCrs:
                destination = QgsCoordinateTransform(point.destinationPointCrs(), targetCrs, context).transform(destination)
            dx, dy = residuals[index] if index < len(residuals) else (0, 0)
            writer.writerow((destination.x(), destination.y(), point.sourcePoint().x(), point.sourcePoint().y(),
                             int(point.isEnabled()), dx, dy, math.hypot(dx, dy)))
        path = Path(filePath)
        fd, temporary = tempfile.mkstemp(prefix='.gcp-', suffix='.points', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream: stream.write(buffer.getvalue())
            os.replace(temporary, path)
        finally:
            if Path(temporary).exists(): Path(temporary).unlink()
