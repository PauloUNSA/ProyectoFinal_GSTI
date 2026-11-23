"""Genera las mismas franjas que el mapa y el detector CNN."""
from pathlib import Path
import argparse
import json
import sys
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from backend.spatial import generar_poligonos_banda
from servidor import LIMITES_PATH, leer_bandas


def exportar_referencias_cayma(capas):
    """Recorta la visualización y conserva los archivos documentales originales."""
    from shapely.geometry import mapping, shape

    distrito = shape(json.loads((capas / "distrito-cayma.geojson").read_text(encoding="utf-8"))["geometry"])
    referencias = []
    for categoria, nombre in (
        ("hito", "hitos-ana.geojson"),
        ("limite", "limites-faja-cayma.geojson"),
        ("vertice", "vertices-limites-cayma.geojson"),
    ):
        capa = json.loads((capas / nombre).read_text(encoding="utf-8"))
        for feature in capa["features"]:
            geometria = shape(feature["geometry"]).intersection(distrito)
            if geometria.is_empty:
                continue
            referencias.append({
                **feature,
                "geometry": mapping(geometria),
                "properties": {**feature["properties"], "categoria": categoria},
            })
    destino = capas / "referencias-visor-cayma.geojson"
    destino.write_text(json.dumps({"type": "FeatureCollection", "features": referencias},
                                  ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rojo", type=float, default=4, help="Metadato documental; reconstrucción fija de 4 m por faja marginal")
    parser.add_argument("--amarillo", type=float, default=0)
    parser.add_argument("--limites", default=str(BASE_DIR/"web/layers/limites-faja-cayma.geojson"))
    parser.add_argument("--salida", default=str(BASE_DIR/"web/layers/bandas-proximidad.geojson"))
    args = parser.parse_args()
    if Path(args.limites).resolve() == LIMITES_PATH:
        salida = leer_bandas(args.amarillo)
        salida["metadata"]["rojo_m_documental"] = args.rojo
    else:
        bandas = generar_poligonos_banda(json.loads(Path(args.limites).read_text(encoding="utf-8-sig")), args.rojo, args.amarillo)
        salida = {"type": "FeatureCollection", "features": [bandas[c] for c in ("naranja", "rojo", "cauce") if bandas[c]["geometry"]["coordinates"]], "metadata": bandas["metadata"]}
    path = Path(args.salida)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    if path.resolve() == LIMITES_PATH.with_name("bandas-proximidad.geojson"):
        exportar_referencias_cayma(LIMITES_PATH.parent)
    print(f"Franjas guardadas en {path}")

if __name__ == "__main__":
    main()
