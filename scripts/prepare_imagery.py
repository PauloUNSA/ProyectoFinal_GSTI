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
    capas = BASE / "web/layers"
    limites = json.loads((capas / "limites-faja-cayma.geojson").read_text(encoding="utf-8-sig"))
    huella = json.loads((capas / "huella-huaico-chullo-a7270.geojson").read_text(encoding="utf-8"))
    distrito = json.loads((capas / "distrito-cayma.geojson").read_text(encoding="utf-8"))
    zonas = construir_zonas(limites, huella_huaico=huella, distrito=distrito)
    x0, y0, x1, y1 = zonas["exterior"].bounds
    res = 0.5
    x0, y0 = math.floor((x0-64)/res)*res, math.floor((y0-64)/res)*res
    x1, y1 = math.ceil((x1+64)/res)*res, math.ceil((y1+64)/res)*res
    width, height = round((x1-x0)/res), round((y1-y0)/res)
    datos = np.zeros((3, height, width), dtype="uint8")
    cobertura_valida = np.zeros((height, width), dtype="uint8")
    exports = []
    for fila in range(0, height, 3000):
        alto = min(3000, height-fila)
        top, bottom = y1-fila*res, y1-(fila+alto)*res
        # Pedir un borde adicional evita huecos de reproyección en las uniones.
        borde = 16
        extra = borde * res
        params = {
            "f": "json", "bbox": f"{x0-extra},{bottom-extra},{x1+extra},{top+extra}",
            "bboxSR": 32719, "imageSR": 32719,
            "size": f"{width+2*borde},{alto+2*borde}", "format": "png32", "transparent": "true",
        }
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
        rgba = np.asarray(Image.open(BytesIO(imagen.content)).convert("RGBA")).transpose(2, 0, 1)
        origen = from_bounds(ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"], rgba.shape[2], rgba.shape[1])
        destino = from_origin(x0, top, res, res)
        for banda in range(3):
            reproject(rgba[banda], datos[banda, fila:fila+alto], src_transform=origen, src_crs="EPSG:32719",
                      dst_transform=destino, dst_crs="EPSG:32719", resampling=Resampling.bilinear)
        reproject(rgba[3], cobertura_valida[fila:fila+alto], src_transform=origen, src_crs="EPSG:32719",
                  dst_transform=destino, dst_crs="EPSG:32719", resampling=Resampling.nearest)
        exports.append({"params": params, "extent": ext, "width": info["width"], "height": info["height"],
                        "sha256_response_image": hashlib.sha256(imagen.content).hexdigest()})
        print(f"Captura {len(exports)}: filas {fila}–{fila+alto}/{height}", flush=True)
    from rasterio.features import geometry_mask
    from shapely.geometry import mapping

    transformacion = from_origin(x0, y1, res, res)
    area_analisis = geometry_mask([mapping(zonas["exterior"])], out_shape=(height, width),
                                 transform=transformacion, invert=True, all_touched=True)
    sin_cobertura = np.count_nonzero(area_analisis & (cobertura_valida == 0))
    if sin_cobertura:
        raise ValueError(f"La imagen contiene {sin_cobertura} píxeles sin cobertura dentro del área de análisis.")
    print(f"Cobertura comprobada: {np.count_nonzero(area_analisis)} píxeles de las zonas.", flush=True)
    destino = BASE / "data/imagery/chullo/chullo_rgb.tif"
    temporal = destino.with_suffix(".tmp.tif")
    with rasterio.open(temporal, "w", driver="GTiff", width=width, height=height, count=3, dtype="uint8",
                       crs="EPSG:32719", transform=from_origin(x0,y1,res,res), compress="deflate", predictor=2, tiled=True) as dst:
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
                "ambito": "Tramo Chullo en Cayma", "width": width, "height": height, "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}
    destino.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(destino, flush=True)

if __name__ == "__main__":
    preparar()
