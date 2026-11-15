"""CLI: ejecutar deteccion de edificios con CNN sobre una imagen GeoTIFF.

Uso (PowerShell):
    python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida outputs/detection --umbral 0.5

Requisitos: torch, rasterio, shapely, pyproj y torchvision (Mask R-CNN) o ultralytics (YOLO).
Si no estan instalados, usa el visor sin deteccion (datos estaticos).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permitir importar backend.detector desde la raiz del proyecto
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from backend.detector import detectar_edificios  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Deteccion de cubiertas con CNN (YOLO-seg o Mask R-CNN)")
    parser.add_argument("--imagen", required=True, help="Ruta al GeoTIFF RGB del sector")
    parser.add_argument("--salida", default="outputs/detection", help="Directorio de salida")
    parser.add_argument("--umbral", type=float, default=None, help="Umbral de confianza (0-1); por defecto, el del modelo")
    parser.add_argument("--modelo", default=None, choices=["auto", "yolo", "maskrcnn"],
                        help="Modelo; por defecto CHULLO_MODELO o auto (YOLO si está entrenado)")
    parser.add_argument("--amarillo", type=float, default=20, help="Ancho exterior desde los límites documentales (m)")
    parser.add_argument(
        "--dispositivo",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Dispositivo para inferencia",
    )
    parser.add_argument(
        "--tamano-mosaico",
        type=int,
        default=None,
        help="Tamano de mosaico en pixeles; por defecto, el del modelo",
    )
    parser.add_argument(
        "--solapamiento",
        type=int,
        default=None,
        help="Solapamiento entre mosaicos; por defecto, un cuarto del mosaico",
    )
    parser.add_argument(
        "--area-minima",
        type=float,
        default=10.0,
        help="Area minima en m2 para conservar una deteccion",
    )
    args = parser.parse_args()

    imagen = Path(args.imagen)
    if not imagen.exists():
        print(f"ERROR: No se encuentra la imagen: {imagen}", file=sys.stderr)
        sys.exit(1)

    def progreso(mensaje: str, valor: float, **kwargs):
        print(f"[{(valor * 100):5.1f}%] {mensaje}", flush=True)

    try:
        manifiesto = detectar_edificios(
            imagen,
            args.salida,
            umbral=args.umbral,
            dispositivo=args.dispositivo,
            tamano_mosaico=args.tamano_mosaico,
            solapamiento=args.solapamiento,
            area_minima_m2=args.area_minima,
            progreso=progreso,
            amarillo_m=args.amarillo,
            modelo=args.modelo,
        )
        print("\nDeteccion completada.")
        print(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
