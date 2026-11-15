"""Convierte las celdas completas y sus techos en un dataset YOLO-seg.

Uso:
    python scripts/armar_dataset_yolo.py

Lee data/training/yolo_chullo/celdas.geojson y techos.geojson y escribe
data/training/yolo_chullo/dataset/ (images/, labels/, data.yaml, resumen.json).
"""
from pathlib import Path
import argparse
import json
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from backend.dataset_yolo import armar_dataset  # noqa: E402

ANOTACION = BASE / "data/training/yolo_chullo"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--imagen", default=str(BASE / "data/imagery/chullo/chullo_rgb.tif"))
    parser.add_argument("--celdas", default=str(ANOTACION / "celdas.geojson"))
    parser.add_argument("--techos", default=str(ANOTACION / "techos.geojson"))
    parser.add_argument("--destino", default=str(ANOTACION / "dataset"))
    parser.add_argument("--imgsz", type=int, default=640, help="Tamaño de entrada de la red (la celda se amplía)")
    parser.add_argument("--sin-desplazados", action="store_true", help="No crear recortes extra a media celda en train")
    args = parser.parse_args()
    try:
        resumen = armar_dataset(args.imagen, args.celdas, args.techos, args.destino, args.imgsz, not args.sin_desplazados)
    except ValueError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(resumen["splits"], ensure_ascii=False, indent=2))
    for aviso in resumen["avisos"]:
        print("AVISO:", aviso)
    print(f"Dataset listo: {Path(args.destino) / 'data.yaml'}")


if __name__ == "__main__":
    main()
