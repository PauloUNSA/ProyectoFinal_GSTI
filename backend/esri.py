"""Descarga de recortes de Esri World Imagery en UTM, con la extensión que devuelve ArcGIS."""
from __future__ import annotations

from io import BytesIO
import math

import numpy as np

SERVICE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
ATRIBUCION = "Esri, Vantor, Earthstar Geographics, and the GIS User Community"


def epsg_utm(lat, lon):
    zona = int((lon + 180) // 6) + 1
    return (32700 if lat < 0 else 32600) + zona


def exportar(lat, lon, lado_px, res_m=0.5):
    """RGB (lado_px, lado_px, 3) centrado en (lat, lon) y metadatos con epsg y extensión."""
    import requests
    from PIL import Image
    from pyproj import Transformer
    epsg = epsg_utm(lat, lon)
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    medio = lado_px * res_m / 2
    x0, y0 = math.floor(x - medio), math.floor(y - medio)
    x1, y1 = x0 + lado_px * res_m, y0 + lado_px * res_m
    params = {"f": "json", "bbox": f"{x0},{y0},{x1},{y1}", "bboxSR": epsg, "imageSR": epsg,
              "size": f"{lado_px},{lado_px}", "format": "png24", "transparent": "false"}
    info = requests.get(SERVICE + "/export", params=params, timeout=180).json()
    if "error" in info:
        raise ValueError(info["error"])
    ext = info["extent"]
    wkid = ext["spatialReference"].get("latestWkid", ext["spatialReference"].get("wkid"))
    if wkid != epsg or (info["width"], info["height"]) != (lado_px, lado_px):
        raise ValueError(f"ArcGIS devolvió otra rejilla ({wkid}, {info['width']}×{info['height']}).")
    imagen = requests.get(info["href"], timeout=180)
    imagen.raise_for_status()
    rgb = np.asarray(Image.open(BytesIO(imagen.content)).convert("RGB"))
    return rgb, {"epsg": epsg, "extent": [ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"]],
                 "fuente": "Esri World Imagery", "service_url": SERVICE, "atribucion": ATRIBUCION}


def guardar_geotiff(path, rgb, meta):
    import rasterio
    from rasterio.transform import from_bounds
    alto, ancho = rgb.shape[:2]
    with rasterio.open(path, "w", driver="GTiff", width=ancho, height=alto, count=3, dtype="uint8",
                       crs=f"EPSG:{meta['epsg']}", transform=from_bounds(*meta["extent"], ancho, alto),
                       compress="deflate", tiled=True) as dst:
        dst.write(rgb.transpose(2, 0, 1))
        dst.update_tags(attribution=ATRIBUCION, source_url=SERVICE)
