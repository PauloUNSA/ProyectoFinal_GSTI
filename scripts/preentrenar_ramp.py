"""Preentrena YOLO-seg con techos de RAMP antes de afinarlo en Arequipa.

Uso (con .venv-ml, después de scripts/armar_dataset_ramp.py):
    python scripts/preentrenar_ramp.py
    python scripts/entrenar_yolo.py --base data/training/ramp_runs/preentrenado.pt

El modelo base de Ultralytics viene de fotos comunes (COCO). Pasar antes por
~4 000 recortes aéreos con techos dibujados por personas le enseña la forma
de un techo visto desde arriba; luego el afinado en Arequipa ajusta el
estilo local. Escribe data/training/ramp_runs/preentrenado.pt (no se versiona).
Los datos de RAMP son CC BY-NC 4.0: el modelo resultante es de uso no comercial.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import shutil

BASE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default=str(BASE / "data/training/ramp_dataset"))
    parser.add_argument("--base", default="yolo26s-seg.pt")
    parser.add_argument("--epocas", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--lote", type=int, default=16)
    parser.add_argument("--runs", default=str(BASE / "data/training/ramp_runs"))
    args = parser.parse_args()

    import torch
    from ultralytics import YOLO
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S")
    modelo = YOLO(args.base)
    modelo.train(data=str(Path(args.dataset) / "data.yaml"), imgsz=args.imgsz, epochs=args.epocas, patience=20,
                 batch=args.lote, device=0 if torch.cuda.is_available() else "cpu", project=str(Path(args.runs).resolve()),
                 name=nombre, seed=42, workers=4, plots=True, verbose=False, cache="ram",
                 degrees=15.0, flipud=0.5, fliplr=0.5, scale=0.3, translate=0.1, hsv_h=0.015, hsv_s=0.5, hsv_v=0.3)
    salida = Path(args.runs) / "preentrenado.pt"
    shutil.copyfile(modelo.trainer.best, salida)
    resultado = YOLO(str(salida)).val(data=str(Path(args.dataset) / "data.yaml"), split="val", imgsz=args.imgsz,
                                      plots=False, verbose=False, project=str(Path(args.runs).resolve()), name=nombre + "_val")
    resumen = {"pesos": str(salida), "base": args.base, "epocas": args.epocas, "run": nombre,
               "val_mascaras": {"precision": float(resultado.seg.mp), "recall": float(resultado.seg.mr),
                                "map50": float(resultado.seg.map50)},
               "licencia": "Datos RAMP CC BY-NC 4.0 (DevGlobal/OMS): uso no comercial con atribución."}
    (Path(args.runs) / "preentrenado.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
