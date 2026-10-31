"""Validación ligera del raster, sin cargar PyTorch ni el modelo."""
from pathlib import Path


def validar_imagen(path):
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"No se encuentra la imagen: {path.name}.")
    with rasterio.open(path) as src:
        if src.driver != "GTiff" or src.crs is None:
            raise ValueError("La imagen debe ser un GeoTIFF georreferenciado; un PNG renombrado como .tif no tiene coordenadas.")
        if src.count < 3 or any(d != "uint8" for d in src.dtypes[:3]):
            raise ValueError("La imagen debe tener tres bandas RGB uint8 (0–255).")
        if src.transform.is_identity or abs(src.transform.determinant) < 1e-15:
            raise ValueError("La imagen no tiene una transformación geográfica válida.")
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        if not np.isfinite(bounds).all() or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
            raise ValueError("La extensión geográfica de la imagen no es válida.")
        return {"path": str(path), "crs": str(src.crs), "width": src.width, "height": src.height, "bounds_wgs84": list(bounds)}
