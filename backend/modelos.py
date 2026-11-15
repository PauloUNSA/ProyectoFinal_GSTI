"""Registro de modelos de detección, sin importar PyTorch ni Ultralytics.

`auto` usa el modelo YOLO entrenado si su manifiesto existe y, si no, el
Mask R-CNN piloto. El servidor y la CLI leen la preferencia de
CHULLO_MODELO (auto | yolo | maskrcnn).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MASKRCNN_DIR = BASE_DIR / "models/chullo_local_v1"
MASKRCNN_SHA256 = "dcc985d4b57ec6ab0c6dbc36bf48f8b6433bfe61e9d89faf2445bb7b05d5f61c"
TIPOS = ("auto", "yolo", "maskrcnn")


def yolo_dir() -> Path:
    return Path(os.getenv("CHULLO_YOLO_DIR", BASE_DIR / "models/yolo_chullo_v1"))


def manifiesto_yolo() -> dict | None:
    path = yolo_dir() / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolver_tipo(tipo: str | None = None) -> str:
    tipo = (tipo or os.getenv("CHULLO_MODELO", "auto")).lower()
    if tipo not in TIPOS:
        raise ValueError(f"Modelo desconocido: {tipo}. Usa auto, yolo o maskrcnn.")
    if tipo == "auto":
        return "yolo" if manifiesto_yolo() else "maskrcnn"
    return tipo


def umbral_por_defecto(tipo: str) -> float:
    """YOLO usa la confianza de F1 máximo en val; Mask R-CNN, 0.5."""
    if tipo == "yolo":
        umbral = (manifiesto_yolo() or {}).get("umbral_recomendado")
        if umbral:
            return float(umbral)
    return 0.5


def parametros_mosaico(tipo: str) -> tuple[int, int]:
    """Tamaño y solapamiento de inferencia: YOLO repite el recorte de entrenamiento."""
    if tipo == "yolo":
        tile = int((manifiesto_yolo() or {}).get("tile_px", 256))
        return tile, tile // 4
    return 512, 128


def describir(tipo: str | None = None) -> dict:
    """Datos del modelo elegido y por qué no estaría disponible."""
    tipo = resolver_tipo(tipo)
    if tipo == "yolo":
        manifest = manifiesto_yolo()
        if not manifest:
            return {"tipo": "yolo", "nombre": "YOLO-seg Chullo", "error": f"No existe {yolo_dir() / 'manifest.json'}.",
                    "dependencias": ["numpy", "rasterio", "torch", "ultralytics", "shapely", "pyproj"]}
        pesos = yolo_dir() / manifest["filename"]
        return {"tipo": "yolo", "id": manifest["id"], "nombre": manifest.get("title", "YOLO-seg Chullo"),
                "pesos": pesos, "sha256": manifest["sha256"], "manifest": manifest,
                "error": None if pesos.is_file() else f"Faltan los pesos {pesos.name}.",
                "dependencias": ["numpy", "rasterio", "torch", "ultralytics", "shapely", "pyproj"]}
    pesos = MASKRCNN_DIR / "weights.pth"
    return {"tipo": "maskrcnn", "id": "chullo/maskrcnn_chullo_local_v1", "nombre": "Mask R-CNN · Chullo local v1 (piloto)",
            "pesos": pesos, "sha256": MASKRCNN_SHA256,
            "error": None if pesos.is_file() else "Falta el modelo local Chullo.",
            "dependencias": ["numpy", "rasterio", "torch", "torchvision", "shapely", "pyproj"]}
