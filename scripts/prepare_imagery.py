"""Prepara una captura georreferenciada del corredor ANA desde World Imagery.

Exporta únicamente la extensión local del visor. Usa el extent y CRS que
responde ArcGIS, sin asignar coordenadas a una captura de pantalla.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hashlib
import json
import math
from datetime import datetime, timezone
from io import BytesIO
import numpy as np
import requests
import rasterio
from rasterio.transform import from_bounds, from_origin
from rasterio.warp import reproject, Resampling
from PIL import Image
from backend.spatial import construir_zonas

BASE = Path(__file__).resolve().parents[1]
SERVICE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"


def preparar():
    zonas = construir_zonas(json.loads((BASE / "web/layers/limites-faja-cayma.geojson").read_text()), 20)
    x0, y0, x1, y1 = zonas["exterior"].bounds
    res = 0.5
    x0, y0 = math.floor((x0-64)/res)*res, math.floor((y0-64)/res)*res
    x1, y1 = math.ceil((x1+64)/res)*res, math.ceil((y1+64)/res)*res
    width, height = round((x1-x0)/res), round((y1-y0)/res)
    datos = np.zeros((3, height, width), dtype="uint8")
    exports = []
    for fila in range(0, height, 3000):
        alto = min(3000, height-fila)
        top, bottom = y1-fila*res, y1-(fila+alto)*res
        params = {"f": "json", "bbox": f"{x0},{bottom},{x1},{top}", "bboxSR": 32719, "imageSR": 32719,
                  "size": f"{width},{alto}", "format": "png24", "transparent": "false"}
        respuesta = requests.get(SERVICE+"/export", params=params, timeout=120)
        respuesta.raise_for_status()
        info = respuesta.json()
        if "error" in info:
            raise ValueError(info["error"])
        ext = info["extent"]
        wkid = ext["spatialReference"].get("latestWkid", ext["spatialReference"].get("wkid"))
        if wkid != 32719:
            raise ValueError(f"CRS inesperado: {wkid}")
        imagen = requests.get(info["href"], timeout=120)
        imagen.raise_for_status()
        rgb = np.asarray(Image.open(BytesIO(imagen.content)).convert("RGB")).transpose(2,0,1)
        origen = from_bounds(ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"], rgb.shape[2], rgb.shape[1])
        for banda in range(3):
            reproject(rgb[banda], datos[banda, fila:fila+alto], src_transform=origen, src_crs="EPSG:32719",
                      dst_transform=from_origin(x0, top, res, res), dst_crs="EPSG:32719", resampling=Resampling.bilinear)
        exports.append({"params": params, "extent": ext, "width": info["width"], "height": info["height"],
                        "sha256_response_image": hashlib.sha256(imagen.content).hexdigest()})
        print(f"Captura {len(exports)}: filas {fila}–{fila+alto}/{height}", flush=True)
    destino = BASE / "data/imagery/chullo/chullo_rgb.tif"
    temporal = destino.with_suffix(".tmp.tif")
    with rasterio.open(temporal, "w", driver="GTiff", width=width, height=height, count=3, dtype="uint8",
                       crs="EPSG:32719", transform=from_origin(x0,y1,res,res), compress="deflate", tiled=True) as dst:
        dst.write(datos)
        dst.colorinterp = (rasterio.enums.ColorInterp.red, rasterio.enums.ColorInterp.green, rasterio.enums.ColorInterp.blue)
        dst.update_tags(attribution="Esri, Vantor, Earthstar Geographics, and the GIS User Community", source_url=SERVICE)
    temporal.replace(destino)
    manifest = {"source": "Esri World Imagery", "service_url": SERVICE, "acquired_at": datetime.now(timezone.utc).isoformat(),
                "observed_at": None, "observed_at_note": "La fecha de captura no se infiere de la fecha de descarga.",
                "attribution": "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
                "terms_url": "https://goto.arcgisonline.com/maps/World_Imagery", "exports": exports,
                "crs": "EPSG:32719", "bounds": [x0,y0,x1,y1], "resolution_m": res,
                "resolution_note": "Paso de la rejilla exportada; no certifica resolución nativa ni precisión posicional.",
                "width": width, "height": height, "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}
    destino.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destino, flush=True)

if __name__ == "__main__":
    preparar()
