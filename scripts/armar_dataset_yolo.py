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
    parser.add_argument("--origen", default="anotacion_humana", choices=["anotacion_humana", "overture"],
                        help="De dónde vienen los techos; queda registrado en el modelo")
    parser.add_argument("--bloques-arequipa", action="store_true",
                        help="Suma los bloques de data/training/yolo_arequipa (scripts/ampliar_arequipa.py)")
    parser.add_argument("--sin-desplazados", action="store_true", help="No crear recortes extra a media celda en train")
    args = parser.parse_args()
    extras = []
    if args.bloques_arequipa:
        bloques = json.loads((BASE / "config/bloques_arequipa.json").read_text(encoding="utf-8"))["bloques"]
        for b in bloques:
            carpeta = BASE / "data/training/yolo_arequipa" / b["id"]
            if not (carpeta / "celdas.geojson").exists():
                parser.exit(1, f"Falta {carpeta}; ejecuta antes scripts/ampliar_arequipa.py\n")
            # Hay celdas de sobra: sin recortes desplazados para no inflar el entrenamiento.
            extras.append({"imagen": BASE / f"data/imagery/arequipa_bloques/{b['id']}.tif", "celdas": carpeta / "celdas.geojson",
                           "techos": carpeta / "techos.geojson", "desplazados": False})
    try:
        resumen = armar_dataset(args.imagen, args.celdas, args.techos, args.destino, args.imgsz, not args.sin_desplazados,
                                args.origen, extras)
    except ValueError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(resumen["splits"], ensure_ascii=False, indent=2))
    for aviso in resumen["avisos"]:
        print("AVISO:", aviso)
    print(f"Dataset listo: {Path(args.destino) / 'data.yaml'}")


if __name__ == "__main__":
    main()
