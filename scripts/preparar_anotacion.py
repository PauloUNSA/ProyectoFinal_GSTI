"""Crea las capas para anotar techos en QGIS sobre la imagen del corredor.

Genera en data/training/yolo_chullo/:
  celdas.geojson  celdas de 128 m que tocan las franjas, con split y estado
  techos.geojson  borrador con las detecciones Mask R-CNN guardadas

Nunca sobrescribe anotaciones existentes salvo con --forzar.
"""
from pathlib import Path
import argparse
import json
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.dataset_yolo import borrador_desde_detecciones, celdas_a_geojson, generar_celdas  # noqa: E402
from backend.spatial import construir_zonas  # noqa: E402

DESTINO = BASE / "data/training/yolo_chullo"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--imagen", default=str(BASE / "data/imagery/chullo/chullo_rgb.tif"))
    parser.add_argument("--detecciones", default=str(BASE / "web/outputs/detection/buildings.geojson"),
                        help="GeoJSON usado como borrador; vacío para empezar sin borrador")
    parser.add_argument("--tamano", type=int, default=256, help="Lado de la celda en píxeles (256 px = 128 m)")
    parser.add_argument("--amarillo", type=float, default=20)
    parser.add_argument("--destino", default=str(DESTINO))
    parser.add_argument("--forzar", action="store_true", help="Reemplaza celdas.geojson y techos.geojson existentes")
    args = parser.parse_args()

    import rasterio
    destino = Path(args.destino)
    celdas_path, techos_path = destino / "celdas.geojson", destino / "techos.geojson"
    existentes = [p.name for p in (celdas_path, techos_path) if p.exists()]
    if existentes and not args.forzar:
        parser.exit(1, f"Ya existen {', '.join(existentes)} en {destino}. No se tocan para no perder anotaciones; usa --forzar.\n")

    limites = json.loads((BASE / "web/layers/limites-faja-cayma.geojson").read_text(encoding="utf-8-sig"))
    zonas = construir_zonas(limites, args.amarillo)
    with rasterio.open(args.imagen) as src:
        celdas = generar_celdas(src, zonas["exterior"], zonas["cauce"], zonas["crs"], args.tamano)
    detecciones = {"features": []}
    if args.detecciones:
        detecciones = json.loads(Path(args.detecciones).read_text(encoding="utf-8"))
    borrador, conteo = borrador_desde_detecciones(detecciones, celdas)

    destino.mkdir(parents=True, exist_ok=True)
    celdas_path.write_text(json.dumps(celdas_a_geojson(celdas, args.tamano, conteo), ensure_ascii=False, indent=1), encoding="utf-8")
    techos_path.write_text(json.dumps(borrador, ensure_ascii=False), encoding="utf-8")
    por_split = {s: sum(c["split"] == s for c in celdas) for s in ("train", "val", "test")}
    print(f"{len(celdas)} celdas de {args.tamano} px ({por_split}) -> {celdas_path}")
    print(f"{len(borrador['features'])} techos de borrador -> {techos_path}")
    print("Siguiente paso: abre ambas capas en QGIS sobre chullo_rgb.tif (ver docs/ENTRENAMIENTO_YOLO.md).")


if __name__ == "__main__":
    main()
