"""Convierte la muestra de RAMP en un dataset YOLO-seg a la escala del proyecto.

Uso (después de scripts/descargar_ramp.py):
    python scripts/armar_dataset_ramp.py

Los recortes de RAMP vienen a 0.3–0.45 m/px. Se remuestrean a 0.5 m/px, la
resolución de la imagen de Arequipa, y se rellenan con gris hasta 256 px:
así un techo ocupa los mismos píxeles que en las celdas de Chullo y la red
lo ve al mismo tamaño al entrenar con imgsz 640. 90 % train y 10 % val.
Escribe data/training/ramp_dataset/ (no se versiona).
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
import random
import shutil
import sys

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
RES_OBJETIVO = 0.5
LADO = 256


def resolucion_m(src):
    if src.crs.is_geographic:
        lat = (src.bounds.top + src.bounds.bottom) / 2
        return (abs(src.transform.a) * 111_320 * math.cos(math.radians(lat)) + abs(src.transform.e) * 110_574) / 2
    return (abs(src.transform.a) + abs(src.transform.e)) / 2


def convertir(tif, geojson, destino_img, destino_lbl, nombre):
    import rasterio
    from PIL import Image
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely import transform as transformar
    from backend.dataset_yolo import poligono_a_linea_yolo
    with rasterio.open(tif) as src:
        rgb = src.read([1, 2, 3]).transpose(1, 2, 0)
        escala = resolucion_m(src) / RES_OBJETIVO
        a, b, c, d, e, f = (~src.transform)[:6]
        a_crs = Transformer.from_crs(4326, src.crs, always_xy=True).transform
    ancho, alto = max(1, round(rgb.shape[1] * escala)), max(1, round(rgb.shape[0] * escala))
    if ancho > LADO or alto > LADO:
        return None  # resolución más gruesa que 0.5 m: no se amplía
    lienzo = np.full((LADO, LADO, 3), 114, dtype=np.uint8)
    lienzo[:alto, :ancho] = np.asarray(Image.fromarray(rgb).resize((ancho, alto), Image.BILINEAR))
    lineas = []
    for feat in json.loads(Path(geojson).read_text(encoding="utf-8")).get("features", []):
        if not feat.get("geometry"):
            continue
        geom = transformar(shape(feat["geometry"]), a_crs, interleaved=False)
        px = transformar(geom, lambda xy: np.column_stack(((a * xy[:, 0] + b * xy[:, 1] + c) * escala,
                                                            (d * xy[:, 0] + e * xy[:, 1] + f) * escala)))
        for parte in getattr(px, "geoms", [px]):
            if parte.geom_type == "Polygon":
                # Se recorta al área con imagen; el relleno gris queda como fondo neutro.
                from shapely.geometry import box
                recorte = parte.intersection(box(0, 0, ancho, alto))
                for p in getattr(recorte, "geoms", [recorte]):
                    if p.geom_type == "Polygon":
                        lineas += poligono_a_linea_yolo(p, LADO, LADO)
    Image.fromarray(lienzo).save(destino_img / f"{nombre}.png")
    (destino_lbl / f"{nombre}.txt").write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
    return len(lineas)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origen", default=str(BASE / "data/externos/ramp"))
    parser.add_argument("--destino", default=str(BASE / "data/training/ramp_dataset"))
    args = parser.parse_args()
    destino = Path(args.destino)
    if destino.exists():
        if not (destino / "data.yaml").is_file():
            parser.exit(1, f"{destino} existe y no parece un dataset generado.\n")
        shutil.rmtree(destino)
    for split in ("train", "val"):
        (destino / "images" / split).mkdir(parents=True)
        (destino / "labels" / split).mkdir(parents=True)
    resumen = {"res_m": RES_OBJETIVO, "lado_px": LADO, "regiones": {}}
    for region in sorted(p for p in Path(args.origen).iterdir() if p.is_dir()):
        chips = sorted(p.stem for p in (region / "source").glob("*.tif"))
        rng = random.Random(42)
        stats = {"train": [0, 0], "val": [0, 0], "omitidos": 0}
        for chip in chips:
            split = "val" if rng.random() < 0.1 else "train"
            n = convertir(region / "source" / f"{chip}.tif", region / "labels" / f"{chip}.geojson",
                          destino / "images" / split, destino / "labels" / split, f"{region.name}_{chip[:8]}")
            if n is None:
                stats["omitidos"] += 1
                continue
            stats[split][0] += 1
            stats[split][1] += n
        resumen["regiones"][region.name] = stats
        print(f"{region.name}: train {stats['train']} val {stats['val']} (recortes, techos) · omitidos {stats['omitidos']}", flush=True)
    (destino / "data.yaml").write_text(f"path: {destino.resolve().as_posix()}\ntrain: images/train\nval: images/val\n"
                                       "names:\n  0: techo\n", encoding="utf-8")
    (destino / "resumen.json").write_text(json.dumps(resumen, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
