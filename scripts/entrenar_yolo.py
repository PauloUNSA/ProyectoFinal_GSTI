"""Entrena YOLO-seg con el dataset de Chullo y registra el modelo para el visor.

Uso (con el entorno .venv-ml):
    python scripts/entrenar_yolo.py
    python scripts/entrenar_yolo.py --base yolo26m-seg.pt --epocas 200

Selecciona la mejor época con val, evalúa una sola vez en test y escribe
models/yolo_chullo_v1/{weights.pt,manifest.json}. Desde ese momento el
servidor usa YOLO automáticamente (CHULLO_MODELO=auto).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
DATASET = BASE / "data/training/yolo_chullo/dataset"
RUNS = BASE / "data/training/yolo_chullo/runs"
DESTINO = BASE / "models/yolo_chullo_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


def metricas(resultado) -> dict:
    """Precisión y recuperación de máscaras en la confianza de F1 máximo."""
    import numpy as np
    seg = resultado.seg
    f1 = np.asarray(seg.f1_curve).mean(0) if len(seg.f1_curve) else np.zeros(1)
    k = int(f1.argmax())
    p, r = float(seg.mp), float(seg.mr)
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "map50": float(seg.map50), "map50_95": float(seg.map),
            "confianza_f1_max": float(np.asarray(seg.px)[k]) if len(f1) > 1 else None,
            "medida": "Máscaras de instancia (Ultralytics val); P y R en la confianza de F1 máximo."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--base", default="yolo26s-seg.pt", help="Pesos iniciales: yolo26n/s/m-seg.pt o yolo11s-seg.pt")
    parser.add_argument("--epocas", type=int, default=150)
    parser.add_argument("--paciencia", type=int, default=40, help="Épocas sin mejora en val antes de parar")
    parser.add_argument("--lote", type=int, default=8)
    parser.add_argument("--dispositivo", default="auto", help="auto, cpu o índice de GPU (0)")
    parser.add_argument("--destino", default=str(DESTINO))
    parser.add_argument("--runs", default=str(RUNS))
    parser.add_argument("--reemplazar", action="store_true", help="Sobrescribe un modelo ya registrado en --destino")
    args = parser.parse_args()

    import torch
    import ultralytics
    from ultralytics import YOLO

    dataset = Path(args.dataset)
    resumen = json.loads((dataset / "resumen.json").read_text(encoding="utf-8"))
    if not resumen["splits"]["val"]["recortes"]:
        parser.exit(1, "ERROR: el dataset no tiene recortes val. Marca como completas algunas celdas val.\n")
    destino = Path(args.destino)
    if (destino / "manifest.json").exists() and not args.reemplazar:
        parser.exit(1, f"ERROR: ya hay un modelo en {destino}. Usa --reemplazar o --destino.\n")
    dispositivo = (0 if torch.cuda.is_available() else "cpu") if args.dispositivo == "auto" else args.dispositivo
    nombre = datetime.now().strftime("%Y%m%d_%H%M%S")
    imgsz = int(resumen["imgsz"])

    modelo = YOLO(args.base)
    modelo.train(
        data=str(dataset / "data.yaml"), imgsz=imgsz, epochs=args.epocas, patience=args.paciencia,
        batch=args.lote, device=dispositivo, project=str(Path(args.runs).resolve()), name=nombre,
        seed=42, deterministic=True, workers=2, plots=True, verbose=False,
        # Vista cenital: los techos no tienen "arriba"; giros y volteos son válidos.
        degrees=15.0, flipud=0.5, fliplr=0.5, scale=0.3, translate=0.1,
        hsv_h=0.015, hsv_s=0.5, hsv_v=0.3, mosaic=1.0, close_mosaic=10,
    )
    mejor = Path(modelo.trainer.best)
    entrenado = YOLO(str(mejor))
    val = metricas(entrenado.val(data=str(dataset / "data.yaml"), split="val", imgsz=imgsz, device=dispositivo,
                                 plots=False, verbose=False, project=str(Path(args.runs).resolve()), name=nombre + "_val"))
    test = None
    if resumen["splits"]["test"]["recortes"]:
        # Una sola evaluación en test, después de elegir la época con val.
        test = metricas(entrenado.val(data=str(dataset / "data.yaml"), split="test", imgsz=imgsz, device=dispositivo,
                                      plots=False, verbose=False, project=str(Path(args.runs).resolve()), name=nombre + "_test"))

    destino.mkdir(parents=True, exist_ok=True)
    pesos = destino / "weights.pt"
    shutil.copyfile(mejor, pesos)
    manifest = {
        "schema_version": 1,
        "id": "chullo/yolo_seg_chullo_v1",
        "title": f"YOLO-seg Chullo ({Path(args.base).stem})",
        "arquitectura": f"Ultralytics {Path(args.base).stem}",
        "base_model": args.base,
        "filename": pesos.name,
        "sha256": sha256(pesos),
        "size_bytes": pesos.stat().st_size,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "tile_px": resumen["tile_px"],
        "imgsz": imgsz,
        "resolucion_m": resumen["resolucion_m"],
        "imagen_sha256": resumen["imagen_sha256"],
        # Un modelo inmaduro puede dar un F1 máximo con confianza casi nula; se acota.
        "umbral_recomendado": round(min(max(val["confianza_f1_max"], 0.1), 0.9), 3) if val["confianza_f1_max"] else None,
        "metricas_val": val,
        "metricas_test": test,
        "dataset": resumen,
        "entrenamiento": {"epocas": args.epocas, "paciencia": args.paciencia, "lote": args.lote,
                          "run": str((Path(args.runs) / nombre).relative_to(BASE)) if Path(args.runs).resolve().is_relative_to(BASE) else str(Path(args.runs) / nombre),
                          "ultralytics": ultralytics.__version__, "torch": torch.__version__,
                          "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
        "licencia": "Ultralytics YOLO y sus pesos: AGPL-3.0 (https://www.ultralytics.com/license).",
        "imagen_fuente": "Esri World Imagery; se conservan su atribución y condiciones de uso.",
        "limitaciones": [
            "Detecta cubiertas visibles; no confirma viviendas, uso residencial, peligro ni permiso para construir.",
            "Las métricas valen para las celdas anotadas de esta imagen; no garantizan otras fechas o zonas.",
            "Celdas vecinas pueden compartir techos en el borde: val y test no son totalmente independientes.",
        ],
    }
    (destino / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"val": val, "test": test}, ensure_ascii=False, indent=2))
    print(f"Modelo registrado en {destino}. Umbral recomendado: {manifest['umbral_recomendado']}")


if __name__ == "__main__":
    main()
