"""Georeference to new files, with native GCP fits and cancelable GDAL warps."""
import os
from pathlib import Path
import tempfile
from osgeo import gdal
from qgis.core import QgsVectorFileWriter, QgsFeedback, QgsCoordinateTransform, QgsProviderRegistry
from qgis.analysis import QgsVectorWarper
from .qgsgeoreftransform import QgsGeorefTransform


class QgsImageWarper:
    @staticmethod
    def rasterParameters(points, settings, context, coords, transform):
        method = settings['method']
        kinds = QgsGeorefTransform.Method
        kwargs = dict(format='GTiff', dstSRS=settings['crs'].toWkt(), resampleAlg=settings['resampling'],
                      creationOptions=['COMPRESS=' + settings['compression'], 'BIGTIFF=IF_SAFER'])
        if settings['resolution']: kwargs.update(xRes=settings['resolution'][0], yRes=settings['resolution'][1])
        if settings['zero']: kwargs.update(srcNodata=0, dstAlpha=True)
        gcps = []
        if method in (kinds.Linear, kinds.Helmert):
            return kwargs, gcps, transform.geoTransform()
        orders = {kinds.PolynomialOrder1: 1, kinds.PolynomialOrder2: 2, kinds.PolynomialOrder3: 3}
        if method == kinds.ThinPlateSpline:
            kwargs.update(tps=True, transformerOptions=['SRC_METHOD=GCP_TPS'])
        elif method in orders:
            kwargs.update(polynomialOrder=orders[method], transformerOptions=['SRC_METHOD=GCP_POLYNOMIAL'])
        else: raise ValueError('栅格投影变换尚未移植，请选择多项式、TPS、线性或 Helmert')
        for point in points:
            if not point.isEnabled(): continue
            pixel = coords.toColumnLine(point.sourcePoint())
            target = point.destinationPoint()
            if point.destinationPointCrs().isValid() and point.destinationPointCrs() != settings['crs']:
                target = QgsCoordinateTransform(point.destinationPointCrs(), settings['crs'], context).transform(target)
            gcps.append((target.x(), target.y(), 0.0, pixel.x(), -pixel.y()))
        return kwargs, gcps, None

    @staticmethod
    def warpRaster(path, output, points, settings, context, coords, transform, progress=None):
        kwargs, gcps, affine = QgsImageWarper.rasterParameters(points, settings, context, coords, transform)
        destination = Path(output)
        if destination.exists(): raise FileExistsError('输出文件已存在，请选择新文件名')
        fd, temporary = tempfile.mkstemp(prefix='.georef-', suffix='.tif', dir=destination.parent)
        os.close(fd)
        source = result = None
        canceled = False
        def callback(value, message, userData):
            nonlocal canceled
            if progress and progress(value*100) is False: canceled = True
            return 0 if canceled else 1
        try:
            with gdal.ExceptionMgr():
                source = gdal.Translate('', str(path), format='VRT')
                if affine:
                    source.SetGCPs([], '')
                    source.SetGeoTransform(affine)
                    source.SetProjection(settings['crs'].toWkt())
                else: source.SetGCPs([gdal.GCP(*values) for values in gcps], settings['crs'].toWkt())
                result = gdal.Warp(temporary, source, callback=callback, **kwargs)
                if canceled: raise InterruptedError('已取消配准')
                if result is None: raise RuntimeError('GDAL 未生成结果')
                result.FlushCache()
                result = source = None
                if destination.exists(): raise FileExistsError('输出文件已被创建，请选择新文件名')
                os.rename(temporary, destination)
            return str(destination)
        except RuntimeError:
            if canceled: raise InterruptedError('已取消配准') from None
            raise
        finally:
            result = source = None
            for suffix in ('', '.aux.xml'):
                file = Path(temporary + suffix)
                if file.exists(): file.unlink()

    @staticmethod
    def warpVector(layer, output, points, settings, context, progress=None):
        destination = Path(output)
        if destination.exists(): raise FileExistsError('输出文件已存在，请选择新文件名')
        fd, temporary = tempfile.mkstemp(prefix='.georef-', suffix='.gpkg', dir=destination.parent)
        os.close(fd)
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName, options.layerName = 'GPKG', 'georeferenced'
        writer = None
        feedback = QgsFeedback()
        def advance(value):
            if progress and progress(value) is False: feedback.cancel()
        feedback.progressChanged.connect(advance)
        total = max(1, layer.featureCount())
        feedback.processedCountChanged.connect(lambda count: advance(100*count/total))
        try:
            advance(0)
            writer = QgsVectorFileWriter.create(temporary, layer.fields(), layer.wkbType(), settings['crs'], context, options)
            if writer.hasError() != QgsVectorFileWriter.NoError: raise ValueError(writer.errorMessage())
            warper = QgsVectorWarper(settings['method'], [point for point in points if point.isEnabled()], settings['crs'])
            if not warper.transformFeatures(layer.getFeatures(), writer, context, feedback):
                if feedback.isCanceled(): raise InterruptedError('已取消配准')
                raise ValueError(warper.error())
            if feedback.isCanceled(): raise InterruptedError('已取消配准')
            writer = None
            if destination.exists(): raise FileExistsError('输出文件已被创建，请选择新文件名')
            os.rename(temporary, destination)
            return str(destination)
        finally:
            writer = None
            for suffix in ('', '-wal', '-shm'):
                file = Path(temporary + suffix)
                if file.exists(): file.unlink()

    @staticmethod
    def generateGDALogr2ogrCommand(layer, output, points, settings, context):
        """Standalone GDAL Python equivalent of the native ogr2ogr command."""
        kinds = QgsGeorefTransform.Method
        orders = {kinds.PolynomialOrder1: 1, kinds.PolynomialOrder2: 2, kinds.PolynomialOrder3: 3}
        method = settings['method']
        if method not in orders and method != kinds.ThinPlateSpline:
            raise ValueError('GDAL 矢量脚本支持一至三阶多项式及 TPS；其他方法请直接执行配准')
        if layer.providerType() != 'ogr':
            raise ValueError('此数据提供者不能由 GDAL 直接读取，请先导出到 GeoPackage')
        parts = QgsProviderRegistry.instance().decodeUri('ogr', layer.source())
        source = parts.get('path')
        if not source: raise ValueError('无法解析 GDAL 源数据路径')
        arguments = []
        for point in points:
            if not point.isEnabled(): continue
            destination = point.destinationPoint()
            if point.destinationPointCrs().isValid() and point.destinationPointCrs() != settings['crs']:
                destination = QgsCoordinateTransform(point.destinationPointCrs(), settings['crs'], context).transform(destination)
            arguments.extend(['-gcp', repr(point.sourcePoint().x()), repr(point.sourcePoint().y()),
                              repr(destination.x()), repr(destination.y())])
        arguments.extend(['-order', str(orders[method])] if method in orders else ['-tps'])
        # GCP targets are already expressed in the target CRS: assign that CRS,
        # without projecting the fitted coordinates a second time.
        options = dict(format='GPKG', layerName='georeferenced', dstSRS=settings['crs'].toWkt(), reproject=False)
        if parts.get('layerName'): options['layers'] = [parts['layerName']]
        subset = layer.subsetString()
        if subset:
            if subset.lstrip().lower().startswith('select '):
                options.pop('layers', None)
                options['SQLStatement'] = subset
            else: options['where'] = subset
        return ('# Run using OSGeo4W Python.\nfrom pathlib import Path\nimport tempfile\nimport os\n'
                'from osgeo import gdal\ngdal.UseExceptions()\n'
                f'output = Path({str(output)!r})\n'
                'if output.exists(): raise FileExistsError(output)\n'
                f'source = gdal.OpenEx({source!r}, gdal.OF_VECTOR | gdal.OF_READONLY)\n'
                'if source is None: raise RuntimeError("Cannot open source")\n'
                f'options = {options!r}\n' +
                (f'options["layers"] = [source.GetLayerByIndex({int(parts.get("layerId") or 0)}).GetName()]\n'
                 if 'layers' not in options and 'SQLStatement' not in options else '') +
                f'arguments = {arguments!r}\n'
                'with tempfile.TemporaryDirectory(prefix=".georef-", dir=output.parent) as directory:\n'
                '    temporary = Path(directory) / "result.gpkg"\n'
                '    result = gdal.VectorTranslate(str(temporary), source, options=gdal.VectorTranslateOptions(options=arguments, **options))\n'
                '    if result is None: raise RuntimeError("Vector warp failed")\n'
                '    result.FlushCache()\n    result = source = None\n'
                '    if output.exists(): raise FileExistsError(output)\n'
                '    os.rename(temporary, output)\n')

    @staticmethod
    def generateGDALScript(path, output, points, settings, context, coords, transform):
        kwargs, gcps, affine = QgsImageWarper.rasterParameters(points, settings, context, coords, transform)
        return ('# Run using OSGeo4W Python. Generated by the QGIS Python georeferencer.\n'
                'from pathlib import Path\nimport tempfile\nimport os\nfrom osgeo import gdal\ngdal.UseExceptions()\n'
                f'output = Path({str(output)!r})\n'
                'if output.exists(): raise FileExistsError(output)\n'
                f'source = gdal.Translate("", {str(path)!r}, format="VRT")\n' +
                (f'source.SetGCPs([], "")\nsource.SetGeoTransform({affine!r})\nsource.SetProjection({settings["crs"].toWkt()!r})\n' if affine else
                 f'source.SetGCPs([gdal.GCP(*v) for v in {gcps!r}], {settings["crs"].toWkt()!r})\n') +
                f'options = {kwargs!r}\n'
                'with tempfile.TemporaryDirectory(prefix=".georef-", dir=output.parent) as directory:\n'
                '    temporary = Path(directory) / "result.tif"\n'
                '    result = gdal.Warp(str(temporary), source, **options)\n'
                '    if result is None: raise RuntimeError("Warp failed")\n'
                '    result.FlushCache()\n    result = source = None\n'
                '    if output.exists(): raise FileExistsError(output)\n'
                '    os.rename(temporary, output)\n')
