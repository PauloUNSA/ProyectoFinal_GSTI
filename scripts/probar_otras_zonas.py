"""Prueba los detectores fuera de la torrentera: otras ciudades, Arequipa y Lima.

Uso (con .venv-ml):
    python scripts/probar_otras_zonas.py
    python scripts/probar_otras_zonas.py --zonas lima_comas el_alto

Para cada zona de config/zonas_prueba.json descarga un recorte de Esri World
Imagery (256 m alrededor del centro, 0.5 m/px, UTM local) y las huellas de
Overture del mismo lugar. Mide Mask R-CNN y YOLO en la celda central de
128 m —la misma escala del entrenamiento— contra esas huellas, que no
tienen revisión humana: miden acuerdo con Overture, no exactitud.

Las descargas se guardan en data/evaluacion/otras_zonas/cache y se reutilizan.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import argparse
import json
import math
import sys

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))
SERVICE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
RES = 0.5
CELDA = 256      # px de la celda evaluada (128 m)
CONTEXTO = 512   # px descargados: Mask R-CNN se aplica con contexto, como en producción
GRUPOS = {"fuera_peru": "Fuera de Perú", "arequipa": "Arequipa (fuera de la torrentera)", "lima": "Lima"}


def epsg_utm(lat, lon):
    zona = int((lon + 180) // 6) + 1
    return (32700 if lat < 0 else 32600) + zona


def descargar_imagen(zona, cache):
    """Recorte RGB de CONTEXTO px en UTM local; usa la extensión que devuelve ArcGIS."""
    import requests
    from PIL import Image
    from pyproj import Transformer
    png, meta_path = cache / f"{zona['id']}.png", cache / f"{zona['id']}.json"
    if png.exists() and meta_path.exists():
        return np.asarray(Image.open(png).convert("RGB")), json.loads(meta_path.read_text(encoding="utf-8"))
    epsg = epsg_utm(zona["lat"], zona["lon"])
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(zona["lon"], zona["lat"])
    medio = CONTEXTO * RES / 2
    x0, y0 = math.floor(x - medio), math.floor(y - medio)
    x1, y1 = x0 + CONTEXTO * RES, y0 + CONTEXTO * RES
    params = {"f": "json", "bbox": f"{x0},{y0},{x1},{y1}", "bboxSR": epsg, "imageSR": epsg,
              "size": f"{CONTEXTO},{CONTEXTO}", "format": "png24", "transparent": "false"}
    info = requests.get(SERVICE + "/export", params=params, timeout=120).json()
    if "error" in info:
        raise ValueError(f"{zona['id']}: {info['error']}")
    ext = info["extent"]
    wkid = ext["spatialReference"].get("latestWkid", ext["spatialReference"].get("wkid"))
    if wkid != epsg or (info["width"], info["height"]) != (CONTEXTO, CONTEXTO):
        raise ValueError(f"{zona['id']}: ArcGIS devolvió otra rejilla ({wkid}, {info['width']}×{info['height']}).")
    imagen = requests.get(info["href"], timeout=120)
    imagen.raise_for_status()
    rgb = np.asarray(Image.open(BytesIO(imagen.content)).convert("RGB"))
    meta = {"epsg": epsg, "extent": [ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"]],
            "fuente": "Esri World Imagery", "atribucion": "Esri, Vantor, Earthstar Geographics, and the GIS User Community"}
    Image.fromarray(rgb).save(png)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return rgb, meta


def descargar_huellas(zona, meta, cache, release):
    """Huellas de Overture que tocan el recorte, en GeoJSON WGS84."""
    import shapely
    from overturemaps import core
    from pyproj import Transformer
    from shapely.geometry import mapping
    path = cache / f"{zona['id']}_overture.geojson"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    a_wgs = Transformer.from_crs(meta["epsg"], 4326, always_xy=True).transform
    x0, y0, x1, y1 = meta["extent"]
    (lon0, lat0), (lon1, lat1) = a_wgs(x0, y0), a_wgs(x1, y1)
    lector = core.record_batch_reader("building", bbox=(min(lon0, lon1), min(lat0, lat1), max(lon0, lon1), max(lat0, lat1)),
                                      release=release)
    filas = lector.read_all().select(["id", "geometry", "sources"]).to_pylist() if lector is not None else []
    features = []
    for fila in filas:
        geom = shapely.from_wkb(fila["geometry"])
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            fuente = ((fila.get("sources") or [{}])[0] or {}).get("dataset") or "desconocida"
            features.append({"type": "Feature", "geometry": mapping(geom), "properties": {"origen": f"overture:{fuente}"}})
    data = {"type": "FeatureCollection", "release": release, "features": features}
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def referencias(huellas, meta):
    """Máscaras de huellas en la celda central (mismo mínimo de 8 px que el entrenamiento)."""
    from pyproj import Transformer
    from rasterio.features import rasterize
    from rasterio.transform import from_origin
    from shapely.geometry import shape
    from shapely import transform as transformar
    a_utm = Transformer.from_crs(4326, meta["epsg"], always_xy=True).transform
    margen = (CONTEXTO - CELDA) // 2
    x0, _, _, y1 = meta["extent"]
    transform = from_origin(x0 + margen * RES, y1 - margen * RES, RES, RES)
    mascaras = []
    for f in huellas["features"]:
        geom = transformar(shape(f["geometry"]), a_utm, interleaved=False)
        for parte in getattr(geom, "geoms", [geom]):
            m = rasterize([(parte, 1)], out_shape=(CELDA, CELDA), transform=transform, dtype="uint8").astype(bool)
            if m.sum() >= 8:
                mascaras.append(m)
    return mascaras


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zonas", nargs="*", help="Ids de config/zonas_prueba.json; por defecto, todas")
    parser.add_argument("--config", default=str(BASE / "config/zonas_prueba.json"))
    parser.add_argument("--destino", default=str(BASE / "data/evaluacion/otras_zonas"))
    parser.add_argument("--release", default=None, help="Versión de Overture; por defecto, la más reciente")
    parser.add_argument("--dispositivo", default="auto", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()

    from PIL import Image, ImageDraw
    from overturemaps import core
    from backend import modelos
    from backend.detector import _predictor_maskrcnn, _predictor_yolo
    from comparar_modelos import COLORES, emparejar, fuentes, metricas, metricas_area, panel, pixeles_area

    zonas = json.loads(Path(args.config).read_text(encoding="utf-8"))["zonas"]
    if args.zonas:
        zonas = [z for z in zonas if z["id"] in set(args.zonas)]
    destino = Path(args.destino)
    cache = destino / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    release = args.release or core.get_latest_release()

    predictores = {"Mask R-CNN piloto": _predictor_maskrcnn(args.dispositivo, 0.5)}
    if not modelos.describir("yolo")["error"]:
        predictores["YOLO"] = _predictor_yolo(args.dispositivo, modelos.umbral_por_defecto("yolo"))
    grande, chica = fuentes()
    margen = (CONTEXTO - CELDA) // 2
    resultados, miniaturas = [], []

    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import Point, box
    with rasterio.open(BASE / "data/imagery/chullo/chullo_rgb.tif") as src:
        torrentera = box(*transform_bounds(src.crs, "EPSG:4326", *src.bounds))
    for zona in zonas:
        # 0.0025° ≈ 270 m: la zona y su contexto deben quedar fuera de la imagen de entrenamiento.
        if Point(zona["lon"], zona["lat"]).buffer(0.0025).intersects(torrentera):
            parser.exit(1, f"La zona {zona['id']} se superpone a la imagen de la torrentera; elige otro punto.\n")

    for zona in zonas:
        rgb, meta = descargar_imagen(zona, cache)
        huellas = descargar_huellas(zona, meta, cache, release)
        celda = rgb[margen:margen + CELDA, margen:margen + CELDA]
        refs = referencias(huellas, meta)
        fila = {"id": zona["id"], "nombre": zona["nombre"], "grupo": zona["grupo"], "referencias": len(refs), "modelos": {}}
        paneles = [(panel(celda, [], []), zona["nombre"], f"{meta['epsg']} · 128 × 128 m"),
                   (panel(celda, refs, [COLORES["referencia"]] * len(refs)), "Referencia Overture (sin revisión)", f"{len(refs)} huellas")]
        for nombre, (predecir, _, _) in predictores.items():
            if nombre.startswith("Mask"):
                puntuaciones, mascaras = predecir(np.ascontiguousarray(rgb.transpose(2, 0, 1)))
                mascaras = [m[margen:margen + CELDA, margen:margen + CELDA] for m in mascaras]
            else:
                puntuaciones, mascaras = predecir(np.ascontiguousarray(celda.transpose(2, 0, 1)))
            pares = [(s, m) for s, m in zip(puntuaciones, mascaras) if m.sum() >= 8]
            mascaras = [m for _, m in pares]
            aciertos_p, aciertos_r = emparejar(mascaras, refs)
            px = pixeles_area(mascaras, refs, CELDA)
            m = {**metricas(len(mascaras), len(refs), len(aciertos_p)), **metricas_area(*px),
                 "px_inter": px[0], "px_pred": px[1], "px_ref": px[2]}
            fila["modelos"][nombre] = m
            omitidas = [r for j, r in enumerate(refs) if j not in aciertos_r]
            colores = [COLORES["acierto"] if i in aciertos_p else COLORES["falso"] for i in range(len(mascaras))]
            img = panel(celda, mascaras + omitidas, colores + [COLORES["omitido"]] * len(omitidas))
            paneles.append((img, nombre, f"F1 techos {m['f1']:.2f} · F1 área {m['f1_area']:.2f} · aciertos {m['aciertos']} · falsos {m['falsos_positivos']}"))
            if nombre == "YOLO":
                miniaturas.append((img, zona, m, fila["modelos"]["Mask R-CNN piloto"]))
        resultados.append(fila)
        ancho = CELDA * 3
        lienzo = Image.new("RGB", (len(paneles) * (ancho + 10) + 10, ancho + 90), "white")
        dibujo = ImageDraw.Draw(lienzo)
        for k, (img, titulo, sub) in enumerate(paneles):
            x = 10 + k * (ancho + 10)
            lienzo.paste(img.convert("RGB"), (x, 80))
            dibujo.text((x, 12), titulo, font=grande, fill=(36, 52, 45))
            dibujo.text((x, 46), sub, font=chica, fill=(83, 98, 89))
        lienzo.save(destino / f"{zona['id']}.png")
        resumen_zona = " · ".join(f"{n}: F1 {v['f1']:.2f} / área {v['f1_area']:.2f}" for n, v in fila["modelos"].items())
        print(f"{zona['nombre']:<42} {len(refs):>3} huellas · {resumen_zona}", flush=True)

    # Totales por grupo, sumando aciertos y no promediando F1.
    por_grupo = {}
    for grupo in GRUPOS:
        filas = [r for r in resultados if r["grupo"] == grupo]
        if not filas:
            continue
        por_grupo[grupo] = {}
        for nombre in predictores:
            pred = sum(r["modelos"][nombre]["aciertos"] + r["modelos"][nombre]["falsos_positivos"] for r in filas)
            ref = sum(r["referencias"] for r in filas)
            area = metricas_area(*(sum(r["modelos"][nombre][k] for r in filas) for k in ("px_inter", "px_pred", "px_ref")))
            por_grupo[grupo][nombre] = {**metricas(pred, ref, sum(r["modelos"][nombre]["aciertos"] for r in filas)), **area}
    (destino / "resumen.json").write_text(json.dumps({"overture_release": release, "zonas": resultados, "por_grupo": por_grupo},
                                                     ensure_ascii=False, indent=2), encoding="utf-8")
    for grupo, valores in por_grupo.items():
        print(f"{GRUPOS[grupo]}: " + " · ".join(f"{n} F1 {v['f1']:.2f} (P {v['precision']:.2f}, R {v['recall']:.2f}) · F1 área {v['f1_area']:.2f}"
                                                  for n, v in valores.items()))

    if miniaturas:
        lado, columnas = 384, 5
        filas_m = math.ceil(len(miniaturas) / columnas)
        mosaico = Image.new("RGB", (columnas * (lado + 10) + 10, filas_m * (lado + 70) + 10), "white")
        dibujo = ImageDraw.Draw(mosaico)
        for k, (img, zona, my, mm) in enumerate(miniaturas):
            x, y = 10 + (k % columnas) * (lado + 10), 10 + (k // columnas) * (lado + 70)
            mosaico.paste(img.convert("RGB").resize((lado, lado)), (x, y + 60))
            dibujo.text((x, y), zona["nombre"][:34], font=chica, fill=(36, 52, 45))
            dibujo.text((x, y + 26), f"YOLO {my['f1']:.2f} / área {my['f1_area']:.2f} · Mask {mm['f1']:.2f} / {mm['f1_area']:.2f}",
                        font=chica, fill=(83, 98, 89))
        mosaico.save(destino / "mosaico_yolo.png")
    print(f"Figuras en {destino}")


if __name__ == "__main__":
    main()
