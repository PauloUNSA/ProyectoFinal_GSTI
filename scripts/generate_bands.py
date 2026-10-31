"""Genera las mismas franjas que el mapa y el detector CNN."""
from pathlib import Path
import argparse
import json
import sys
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from backend.spatial import generar_poligonos_banda


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rojo", type=float, default=4, help="Metadato documental; el corredor se fija por ambos límites")
    parser.add_argument("--amarillo", type=float, default=20)
    parser.add_argument("--limites", default=str(BASE_DIR/"web/layers/limites-faja-cayma.geojson"))
    parser.add_argument("--salida", default=str(BASE_DIR/"web/layers/bandas-proximidad.geojson"))
    args = parser.parse_args()
    bandas = generar_poligonos_banda(json.loads(Path(args.limites).read_text(encoding="utf-8-sig")), args.rojo, args.amarillo)
    salida = {"type": "FeatureCollection", "features": [bandas[c] for c in ("amarillo", "rojo", "cauce") if bandas[c]["geometry"]["coordinates"]], "metadata": bandas["metadata"]}
    path = Path(args.salida)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Franjas guardadas en {path}")

if __name__ == "__main__":
    main()
