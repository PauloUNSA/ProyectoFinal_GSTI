"""CLI: ejecutar detección de edificios con CNN sobre una imagen GeoTIFF.

Uso (PowerShell):
    python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida outputs/detection --umbral 0.5

Requisitos: torch, torchvision, rasterio, geopandas, shapely, pyproj, requests.
Si no están instalados, usa el visor sin detección (datos estáticos).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permitir importar backend.detector desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from backend.detector import detectar_edificios  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Detección de edificios con CNN (Mask R-CNN)")
    parser.add_argument("--imagen", required=True, help="Ruta al GeoTIFF RGB del sector")
    parser.add_argument("--salida", default="outputs/detection", help="Directorio de salida")
    parser.add_argument("--umbral", type=float, default=0.5, help="Umbral de confianza (0-1)")
    parser.add_argument(
        "--dispositivo",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Dispositivo para inferencia",
    )
    parser.add_argument(
        "--tamano-mosaico",
        type=int,
        default=512,
        help="Tamaño de mosaico en píxeles (256-1024)",
    )
    parser.add_argument(
        "--solapamiento",
        type=int,
        default=128,
        help="Solapamiento entre mosaicos (< 50% del tamaño)",
    )
    parser.add_argument(
        "--area-minima",
        type=float,
        default=10.0,
        help="Área mínima en m² para conservar una detección",
    )
    args = parser.parse_args()

    imagen = Path(args.imagen)
    if not imagen.exists():
        print(f"ERROR: No se encuentra la imagen: {imagen}", file=sys.stderr)
        sys.exit(1)

    def progreso(mensaje: str, valor: float, **kwargs):
        print(f"[{(valor*100):5.1f}%] {mensaje}")

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
        )
        print("\nDetección completada.")
        print(json.dumps(manifiesto, indent=2, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
