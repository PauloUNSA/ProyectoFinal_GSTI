"""Importa huellas de edificios de Overture Maps como etiquetas automáticas.

Uso (con .venv-ml):
    python scripts/importar_huellas_overture.py
    python scripts/armar_dataset_yolo.py --celdas data/training/yolo_chullo/overture/celdas.geojson \
        --techos data/training/yolo_chullo/overture/techos.geojson --origen overture

Descarga solo el recuadro del GeoTIFF (unos pocos MB). Overture combina
huellas de Google Open Buildings, Microsoft ML Buildings y OpenStreetMap.
Sirven para entrenar sin anotación manual, pero nadie las revisó: faltan
techos y algunas abarcan un lote entero. Las celdas de este directorio se
marcan todas como completas; las anotaciones humanas siguen en
data/training/yolo_chullo/celdas.geojson y techos.geojson, sin tocarse.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
ANOTACION = BASE / "data/training/yolo_chullo"
ATRIBUCION = ("Huellas de edificios: Overture Maps Foundation (licencia ODbL), que integra © colaboradores de "
              "OpenStreetMap, Google Open Buildings y Microsoft ML Buildings Footprints.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--imagen", default=str(BASE / "data/imagery/chullo/chullo_rgb.tif"))
    parser.add_argument("--celdas", default=str(ANOTACION / "celdas.geojson"))
    parser.add_argument("--destino", default=str(ANOTACION / "overture"))
    parser.add_argument("--release", default=None, help="Versión de Overture; por defecto, la más reciente")
    parser.add_argument("--sin-limpiar", action="store_true", help="No descartar ni alinear huellas (backend/huellas.py)")
    args = parser.parse_args()

    import rasterio
    import shapely
    from overturemaps import core
    from rasterio.warp import transform_bounds
    from shapely.geometry import mapping

    with rasterio.open(args.imagen) as src:
        bbox = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        rgb, transform, crs = src.read([1, 2, 3]).transpose(1, 2, 0), src.transform, src.crs
    release = args.release or core.get_latest_release()
    tabla = core.record_batch_reader("building", bbox=bbox, release=release).read_all()
    filas = tabla.select([c for c in ("id", "geometry", "sources", "is_underground") if c in tabla.column_names]).to_pylist()

    features, fuentes = [], Counter()
    for fila in filas:
        if fila.get("is_underground"):
            continue
        geom = shapely.from_wkb(fila["geometry"])
        if geom.geom_type not in ("Polygon", "MultiPolygon") or geom.is_empty:
            continue
        fuente = ((fila.get("sources") or [{}])[0] or {}).get("dataset") or "desconocida"
        fuentes[fuente] += 1
        features.append({"type": "Feature", "geometry": mapping(geom),
                         "properties": {"origen": f"overture:{fuente}", "overture_id": fila["id"]}})

    limpieza = None
    if not args.sin_limpiar:
        from backend import huellas
        features, limpieza = huellas.preparar(rgb, transform, crs, features)
        print(f"Limpieza: {limpieza['descartes']} · corrimientos aplicados: "
              f"{[(r['fuente'], r['dx_px'], r['dy_px']) for r in limpieza['alineacion'] if r['aplicado']]}")
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "techos.geojson").write_text(json.dumps({"type": "FeatureCollection", "name": "techos_overture",
                                                       "features": features}, ensure_ascii=False), encoding="utf-8")
    celdas = json.loads(Path(args.celdas).read_text(encoding="utf-8-sig"))
    for f in celdas["features"]:
        f["properties"]["estado"] = "completa"
    (destino / "celdas.geojson").write_text(json.dumps(celdas, ensure_ascii=False, indent=1), encoding="utf-8")
    metadatos = {"fuente": "Overture Maps · tema buildings", "release": release, "bbox_wgs84": list(bbox),
                 "descargado_en": datetime.now(timezone.utc).isoformat(), "edificios": len(features),
                 "por_fuente": dict(fuentes), "licencia": "ODbL 1.0", "atribucion": ATRIBUCION,
                 "revision_humana": False, "limpieza": limpieza,
                 "advertencia": "Etiquetas automáticas: faltan techos y algunas huellas cubren un lote entero."}
    (destino / "metadatos.json").write_text(json.dumps(metadatos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(features)} huellas de Overture {release} {dict(fuentes)} -> {destino}")


if __name__ == "__main__":
    main()
