"""CLI: generar GeoJSON de franjas de proximidad (roja/amarilla) desde el eje de la torrentera.

Uso:
    python scripts/generate_bands.py --rojo 25 --amarillo 25 --salida web/layers/bandas-proximidad.geojson
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from backend.spatial import (
    calcular_eje_desde_limites,
    generar_poligonos_banda,
)  # noqa: E402

try:
    import geopandas as gpd  # noqa: E402
except ImportError:
    gpd = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generar franjas de proximidad")
    parser.add_argument("--rojo", type=float, default=25, help="Límite rojo en metros")
    parser.add_argument("--amarillo", type=float, default=25, help="Ancho amarillo en metros")
    parser.add_argument(
        "--limites",
        default="web/layers/limites-faja-cayma.geojson",
        help="GeoJSON de límites de faja",
    )
    parser.add_argument(
        "--salida",
        default="web/layers/bandas-proximidad.geojson",
        help="GeoJSON de salida",
    )
    args = parser.parse_args()

    if gpd is None:
        print("geopandas no está instalado. Usa bands.js del visor para calcular franjas en el navegador.", file=sys.stderr)
        sys.exit(1)

    limites = gpd.read_file(args.limites)
    eje = calcular_eje_desde_limites(limites)
    if eje is None:
        print("No se pudo calcular el eje desde los límites de faja.", file=sys.stderr)
        sys.exit(1)

    bandas = generar_poligonos_banda(eje, args.rojo, args.amarillo)

    features = [
        bandas["rojo"],
        bandas["amarillo"],
        bandas["eje"],
    ]

    salida = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": bandas["metadata"],
    }

    salida_path = Path(args.salida)
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    salida_path.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Bandas guardadas en: {salida_path}")
    print(json.dumps(bandas["metadata"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
