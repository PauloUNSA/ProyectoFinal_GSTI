"""Amplía el entrenamiento con bloques de otros distritos de Arequipa.

Uso (con .venv-ml):
    python scripts/ampliar_arequipa.py

Por cada bloque de config/bloques_arequipa.json descarga 1 × 1 km de Esri
World Imagery (0.5 m/px, EPSG:32719), las huellas de Overture del mismo
recuadro, las limpia y alinea (backend/huellas.py) y genera celdas de 128 m
marcadas como completas. Escribe:
  data/imagery/arequipa_bloques/<id>.tif         (no se versiona)
  data/training/yolo_arequipa/<id>/celdas.geojson, techos.geojson
  data/training/yolo_arequipa/metadatos.json

Ningún bloque puede tocar la imagen de la torrentera ni las zonas de prueba.
Las descargas existentes se reutilizan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
LADO_PX = 2000
SEPARACION_GRADOS = 0.003  # ≈ 330 m de distancia mínima a la torrentera y a las zonas de prueba


def huella_bloque(lat, lon, lado_m):
    from shapely.geometry import box
    medio_lat = lado_m / 2 / 111_320
    medio_lon = medio_lat / max(0.2, abs(__import__("math").cos(__import__("math").radians(lat))))
    return box(lon - medio_lon, lat - medio_lat, lon + medio_lon, lat + medio_lat)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(BASE / "config/bloques_arequipa.json"))
    parser.add_argument("--bloques", nargs="*", help="Ids a procesar; por defecto, todos")
    parser.add_argument("--release", default=None)
    args = parser.parse_args()

    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import LineString, box
    from backend import esri, huellas
    from backend.dataset_yolo import celdas_a_geojson, generar_celdas

    bloques = json.loads(Path(args.config).read_text(encoding="utf-8"))["bloques"]
    if args.bloques:
        bloques = [b for b in bloques if b["id"] in set(args.bloques)]
    with rasterio.open(BASE / "data/imagery/chullo/chullo_rgb.tif") as src:
        prohibidas = [box(*transform_bounds(src.crs, "EPSG:4326", *src.bounds))]
    for z in json.loads((BASE / "config/zonas_prueba.json").read_text(encoding="utf-8"))["zonas"]:
        prohibidas.append(huella_bloque(z["lat"], z["lon"], 256))
    for b in bloques:
        huella = huella_bloque(b["lat"], b["lon"], LADO_PX * 0.5)
        if any(huella.buffer(SEPARACION_GRADOS).intersects(p) for p in prohibidas):
            parser.exit(1, f"El bloque {b['id']} está a menos de ~330 m de la torrentera o de una zona de prueba.\n")

    dir_img = BASE / "data/imagery/arequipa_bloques"
    dir_ann = BASE / "data/training/yolo_arequipa"
    dir_img.mkdir(parents=True, exist_ok=True)
    meta_path = dir_ann / "metadatos.json"
    registro = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"bloques": {}}
    for b in bloques:
        tif = dir_img / f"{b['id']}.tif"
        if not tif.exists():
            rgb, meta = esri.exportar(b["lat"], b["lon"], LADO_PX)
            esri.guardar_geotiff(tif, rgb, meta)
        with rasterio.open(tif) as src:
            rgb = src.read([1, 2, 3]).transpose(1, 2, 0)
            bbox = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
            features, release = huellas.descargar_overture(bbox, args.release)
            limpias, limpieza = huellas.preparar(rgb, src.transform, src.crs, features)
            # Todo el bloque es zona de interés; la línea solo ordena las celdas.
            x0, y0, x1, y1 = src.bounds
            celdas = generar_celdas(src, box(x0, y0, x1, y1), LineString([(x0, y1), (x1, y0)]), str(src.crs), 256)
        for c in celdas:
            c["split"] = b["split"]
            c["id"] = f"{b['id']}_{c['id']}"
        destino = dir_ann / b["id"]
        destino.mkdir(parents=True, exist_ok=True)
        geo = celdas_a_geojson(celdas, 256, {})
        for f in geo["features"]:
            f["properties"]["estado"] = "completa"
        (destino / "celdas.geojson").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
        (destino / "techos.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": limpias}, ensure_ascii=False),
                                                encoding="utf-8")
        registro["bloques"][b["id"]] = {**b, "imagen": str(tif.relative_to(BASE)), "celdas": len(celdas),
                                        "huellas": len(limpias), "overture_release": release, "limpieza": limpieza,
                                        "procesado_en": datetime.now(timezone.utc).isoformat()}
        aplicados = [(r["fuente"][9:], r["dx_px"], r["dy_px"]) for r in limpieza["alineacion"] if r["aplicado"]]
        print(f"{b['nombre']:<34} {len(celdas)} celdas · {len(limpias)} huellas · corrimientos {aplicados}", flush=True)
    registro["licencias"] = {"imagen": esri.ATRIBUCION, "huellas": "Overture Maps (ODbL): Google Open Buildings, Microsoft, OpenStreetMap"}
    meta_path.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
