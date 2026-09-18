"""Georeference to new files, with native GCP fits and cancelable GDAL warps."""
import math
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
        elif method == kinds.Projective:
            # GDAL's Python bindings expose no custom GDALTransformerFunc hook
            # (WarpOptions has no transformer/transformers argument in 3.9), so a
            # projective warp cannot be expressed as a gdal.Warp call. It is
            # resampled directly instead; see warpRasterProjective().
            return kwargs, None, None
        else: raise ValueError('不支持的栅格变换方法')
        for point in points:
            if not point.isEnabled(): continue
            pixel = coords.toColumnLine(point.sourcePoint())
            target = point.destinationPoint()
            if point.destinationPointCrs().isValid() and point.destinationPointCrs() != settings['crs']:
                target = QgsCoordinateTransform(point.destinationPointCrs(), settings['crs'], context).transform(target)
            gcps.append((target.x(), target.y(), 0.0, pixel.x(), -pixel.y()))
        return kwargs, gcps, None

    @staticmethod
    def gcpPixelPairs(points, settings, context, coords):
        """Enabled GCPs as (source column, source row, destination x, destination y).

        Columns and rows use GDAL's corner-based pixel/line convention, matching
        what QgsRasterChangeCoords::toColumnLine() returns (its y axis points up,
        hence the negation).
        """
        pairs = []
        for point in points:
            if not point.isEnabled(): continue
            pixel = coords.toColumnLine(point.sourcePoint())
            target = point.destinationPoint()
            if point.destinationPointCrs().isValid() and point.destinationPointCrs() != settings['crs']:
                target = QgsCoordinateTransform(point.destinationPointCrs(), settings['crs'], context).transform(target)
            pairs.append((pixel.x(), -pixel.y(), target.x(), target.y()))
        return pairs

    @staticmethod
    def projectiveHomography(pairs):
        """Direct linear transform of the source-pixel to destination-map homography.

        Equivalent to the fit QgsProjectiveGcpTransformer performs for the same
        GCPs, which is what the georeferencer residual table shows.
        """
        import numpy as np
        if len(pairs) < 4: raise ValueError('投影变换至少需要 4 个启用的控制点')
        rows = []
        for column, row, x, y in pairs:
            rows.append([column, row, 1.0, 0.0, 0.0, 0.0, -x * column, -x * row, -x])
            rows.append([0.0, 0.0, 0.0, column, row, 1.0, -y * column, -y * row, -y])
        _, singular, transpose = np.linalg.svd(np.array(rows, dtype=np.float64))
        if singular[-1] > 1e-8 * max(singular[0], 1e-30):
            raise ValueError('控制点退化，无法拟合投影变换')
        homography = transpose[-1].reshape(3, 3)
        if abs(homography[2, 2]) < 1e-12: raise ValueError('控制点退化，无法拟合投影变换')
        return homography / homography[2, 2]

    @staticmethod
    def resamplingKernel(name):
        """(tap radius, weight function) for the native resampling names."""
        import numpy as np
        if name == 'near':
            return 0, None
        if name == 'bilinear':
            return 1, lambda t: np.maximum(0.0, 1.0 - np.abs(t))
        if name == 'lanczos':
            def lanczos(t):
                t = np.abs(t)
                return np.where(t < 3.0, np.sinc(t) * np.sinc(t / 3.0), 0.0)
            return 3, lanczos
        # Catmull-Rom for "cubic", the B-spline style a = -1 form for "cubicspline",
        # matching GDAL's corresponding resamplers.
        a = -0.5 if name == 'cubic' else -1.0

        def keys(t):
            t = np.abs(t)
            return np.where(t <= 1.0, ((a + 2.0) * t - (a + 3.0)) * t * t + 1.0,
                            np.where(t < 2.0, (((t - 5.0) * t + 8.0) * t - 4.0) * a, 0.0))
        return 2, keys

    @staticmethod
    def projectiveGrid(pairs, settings, width, height):
        """Destination extent, pixel size and size for the fitted homography."""
        import numpy as np
        homography = QgsImageWarper.projectiveHomography(pairs)
        # homography maps source pixel -> destination map (the DLT fit direction),
        # its inverse maps destination map -> source pixel for the resampling pass.
        inverse = np.linalg.inv(homography)

        def project(columns, rows):
            x, y = QgsImageWarper.projectiveTransform(homography, np.asarray(columns), np.asarray(rows))
            return x, y

        # The projective image of the raster is not a rectangle, so sample the
        # whole boundary rather than only the corners.
        step = np.linspace(0.0, 1.0, 65)
        columns = np.concatenate([step * width, step * width, np.zeros_like(step), np.full_like(step, float(width))])
        rows = np.concatenate([np.zeros_like(step), np.full_like(step, float(height)), step * height, step * height])
        x, y = project(columns, rows)
        if not (np.isfinite(x).all() and np.isfinite(y).all()):
            raise ValueError('投影变换产生了无效坐标，请检查控制点')
        minX, maxX, minY, maxY = float(x.min()), float(x.max()), float(y.min()), float(y.max())
        if maxX <= minX or maxY <= minY: raise ValueError('投影变换输出范围为空')

        if settings['resolution']:
            resX, resY = settings['resolution']
        else:
            centreX, centreY = QgsImageWarper.projectiveTransform(homography, np.array([width / 2.0]), np.array([height / 2.0]))
            edgeX, edgeY = QgsImageWarper.projectiveTransform(homography, np.array([width / 2.0 + 1.0, width / 2.0]), np.array([height / 2.0, height / 2.0 + 1.0]))
            resX = math.hypot(edgeX[0] - centreX[0], edgeY[0] - centreY[0])
            resY = math.hypot(edgeX[1] - centreX[0], edgeY[1] - centreY[0])
            if not (resX > 0 and resY > 0): raise ValueError('控制点退化，无法确定输出分辨率')
        outWidth = QgsImageWarper.pixelCount(maxX - minX, resX)
        outHeight = QgsImageWarper.pixelCount(maxY - minY, resY)
        return homography, inverse, (minX, maxY, resX, resY), outWidth, outHeight

    @staticmethod
    def pixelCount(span, resolution):
        """Output pixel count, snapping values that are a rounding error off a whole pixel.

        Without the snap, an extent of exactly 20 units at resolution 2 comes out as
        20.000000000004 and ceil() adds a spurious column, unlike gdalwarp.
        """
        count = span / resolution
        nearest = round(count)
        if abs(count - nearest) < 1e-6 * max(1.0, abs(count)):
            count = float(nearest)
        return max(1, int(math.ceil(count)))

    @staticmethod
    def projectiveTransform(homography, columns, rows):
        """Apply a 3x3 homography to pixel coordinates."""
        import numpy as np
        denominator = homography[2, 0] * columns + homography[2, 1] * rows + homography[2, 2]
        x = (homography[0, 0] * columns + homography[0, 1] * rows + homography[0, 2]) / denominator
        y = (homography[1, 0] * columns + homography[1, 1] * rows + homography[1, 2]) / denominator
        return np.array([x, y])

    @staticmethod
    def warpRasterProjective(path, output, points, settings, context, coords, progress=None):
        """Projective raster warping, resampled here because GDAL cannot be hooked.

        Destination pixel centres are mapped back through the inverse homography
        and sampled with the requested separable kernel (the same kernels GDAL
        uses for near/bilinear/cubic/cubicspline/lanczos). Work happens in row
        strips so the coordinate arrays stay bounded for large rasters.
        """
        import numpy as np
        pairs = QgsImageWarper.gcpPixelPairs(points, settings, context, coords)
        homography, inverse, grid, outWidth, outHeight = QgsImageWarper.projectiveGrid(
            pairs, settings, *QgsImageWarper.rasterSize(path))
        originX, originY, resX, resY = grid
        radius, weight = QgsImageWarper.resamplingKernel(settings['resampling'])

        destination = Path(output)
        if destination.exists(): raise FileExistsError('输出文件已存在，请选择新文件名')
        source = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
        if source is None: raise ValueError(gdal.GetLastErrorMsg() or '无法读取栅格')
        width, height, bandCount = source.RasterXSize, source.RasterYSize, source.RasterCount
        sourceBand = source.GetRasterBand(1)
        dataType = sourceBand.DataType
        nodata = settings['zero']
        options = ['COMPRESS=' + settings['compression'], 'BIGTIFF=IF_SAFER']
        fd, temporary = tempfile.mkstemp(prefix='.georef-', suffix='.tif', dir=destination.parent)
        os.close(fd)
        Path(temporary).unlink()
        target = None
        canceled = False
        try:
            with gdal.ExceptionMgr():
                target = gdal.GetDriverByName('GTiff').Create(
                    temporary, outWidth, outHeight, bandCount, dataType, options=options)
                if target is None: raise RuntimeError(gdal.GetLastErrorMsg() or '无法创建输出栅格')
                target.SetGeoTransform((originX, resX, 0.0, originY, 0.0, -resY))
                target.SetProjection(settings['crs'].toWkt())
                # dstAlpha: a separate 8-bit alpha band, as gdalwarp produces.
                if nodata: target.AddBand(gdal.GDT_Byte)

                destinationColumns = originX + (np.arange(outWidth) + 0.5) * resX
                stripRows = max(1, min(outHeight, int(2_000_000 // max(1, outWidth))))
                for start in range(0, outHeight, stripRows):
                    stop = min(outHeight, start + stripRows)
                    if progress is not None and progress(96.0 * start / outHeight) is False:
                        canceled = True
                        break
                    rows = originY - (np.arange(start, stop) + 0.5) * resY
                    columns, lines = QgsImageWarper.inverseProjective(inverse, destinationColumns, rows)
                    # Pixel centres sit at half-integer pixel/line coordinates.
                    baseColumn = np.floor(columns - 0.5)
                    baseLine = np.floor(lines - 0.5)
                    fractionColumn = (columns - 0.5) - baseColumn
                    fractionLine = (lines - 0.5) - baseLine
                    if radius == 0:
                        # Nearest neighbour: pick the pixel whose centre is closest.
                        nearestColumn = np.clip(np.rint(columns - 0.5), 0, width - 1).astype(np.intp)
                        nearestLine = np.clip(np.rint(lines - 0.5), 0, height - 1).astype(np.intp)
                        offsets = [0]
                        columnWeights = lineWeights = None
                    else:
                        offsets = list(range(-radius + 1, radius + 1))
                        columnWeights = [weight(fractionColumn - offset) for offset in offsets]
                        lineWeights = [weight(fractionLine - offset) for offset in offsets]
                    for band in range(1, bandCount + 1):
                        values = source.GetRasterBand(band).ReadAsArray().astype(np.float32)
                        if nodata: values = np.where(values != 0, values, np.nan)
                        total = np.zeros((stop - start, outWidth), dtype=np.float32)
                        weightSum = np.zeros((stop - start, outWidth), dtype=np.float32)
                        for lineTap, offset in enumerate(offsets):
                            if radius == 0:
                                lineIndex, lineWeight = nearestLine, None
                            else:
                                lineIndex = np.clip(baseLine + offset, 0, height - 1)
                                lineWeight = lineWeights[lineTap][:, None]
                            for columnTap, columnOffset in enumerate(offsets):
                                if radius == 0:
                                    sample = values[nearestLine, nearestColumn]
                                    tapWeight = None
                                else:
                                    columnIndex = np.clip(baseColumn + columnOffset, 0, width - 1)
                                    sample = values[lineIndex, columnIndex]
                                    tapWeight = lineWeight * columnWeights[columnTap][None, :]
                                if nodata:
                                    valid = ~np.isnan(sample)
                                    total += np.where(valid, sample * (tapWeight if tapWeight is not None else 1.0), 0.0)
                                    weightSum += np.where(valid, tapWeight if tapWeight is not None else 1.0, 0.0)
                                else:
                                    total += sample * (tapWeight if tapWeight is not None else 1.0)
                        if nodata:
                            with np.errstate(invalid='ignore', divide='ignore'):
                                blended = np.where(weightSum > 0, total / weightSum, 0.0)
                        else:
                            blended = total
                        target.GetRasterBand(band).WriteArray(
                            QgsImageWarper.castToDataType(blended, dataType), 0, start)
                        if nodata:
                            # dstAlpha: opaque wherever at least one valid sample
                            # contributed, transparent where the source had nodata.
                            target.GetRasterBand(bandCount + 1).WriteArray(
                                np.where(weightSum > 0, 255, 0).astype(np.uint8), 0, start)
                if canceled: raise InterruptedError('已取消配准')
                target.FlushCache()
                target = source = None
                if destination.exists(): raise FileExistsError('输出文件已被创建，请选择新文件名')
                os.rename(temporary, destination)
            return str(destination)
        except RuntimeError:
            if canceled: raise InterruptedError('已取消配准') from None
            raise
        finally:
            target = source = None
            for suffix in ('', '.aux.xml'):
                file = Path(temporary + suffix)
                if file.exists(): file.unlink()

    @staticmethod
    def castToDataType(values, dataType):
        """Round and clamp resampled samples into the source band's data type."""
        import numpy as np
        numpyType = {gdal.GDT_Byte: np.uint8, gdal.GDT_UInt16: np.uint16, gdal.GDT_Int16: np.int16,
                     gdal.GDT_UInt32: np.uint32, gdal.GDT_Int32: np.int32, gdal.GDT_Float32: np.float32,
                     gdal.GDT_Float64: np.float64}.get(dataType, np.float32)
        if np.issubdtype(numpyType, np.integer):
            limits = np.iinfo(numpyType)
            return np.clip(np.rint(values), limits.min, limits.max).astype(numpyType)
        return values.astype(numpyType)

    @staticmethod
    def rasterSize(path):
        source = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY)
        if source is None: raise ValueError(gdal.GetLastErrorMsg() or '无法读取栅格')
        size = (source.RasterXSize, source.RasterYSize)
        source = None
        return size

    @staticmethod
    def inverseProjective(inverse, columns, rows):
        """Map destination map coordinates back to source pixel coordinates."""
        import numpy as np
        gridColumns, gridRows = np.meshgrid(columns, rows)
        denominator = inverse[2, 0] * gridColumns + inverse[2, 1] * gridRows + inverse[2, 2]
        sourceColumn = (inverse[0, 0] * gridColumns + inverse[0, 1] * gridRows + inverse[0, 2]) / denominator
        sourceLine = (inverse[1, 0] * gridColumns + inverse[1, 1] * gridRows + inverse[1, 2]) / denominator
        return sourceColumn, sourceLine

    @staticmethod
    def warpRaster(path, output, points, settings, context, coords, transform, progress=None):
        kwargs, gcps, affine = QgsImageWarper.rasterParameters(points, settings, context, coords, transform)
        if gcps is None and affine is None:
            return QgsImageWarper.warpRasterProjective(path, output, points, settings, context, coords, progress)
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
