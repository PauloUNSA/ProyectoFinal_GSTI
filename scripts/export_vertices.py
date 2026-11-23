"""Expone como puntos los vértices ya digitalizados, sin alterar coordenadas."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def exportar():
    origen = BASE / "web/layers/limites-faja-cayma.geojson"
    limites = json.loads(origen.read_text(encoding="utf-8"))
    features = []
    for linea in limites["features"]:
        p = linea["properties"]
        for i, coord in enumerate(linea["geometry"]["coordinates"], 1):
            features.append({
                "type": "Feature",
                "id": f'{linea["id"]}-vertex-{i}',
                "geometry": {"type": "Point", "coordinates": coord},
                "properties": {
                    "bank": p["bank"], "position": i,
                    "total": len(linea["geometry"]["coordinates"]),
                    "source_page": p["source_page"], "source": p["source"],
                    "role": "documentary_outer_limit_vertex",
                    "notice": "Posición en línea digitalizada; no es un código oficial ni medición de campo.",
                },
            })
    resultado = {
        "type": "FeatureCollection", "features": features,
        "metadata": {
            "source": "limites-faja-cayma.geojson",
            "count": len(features), "crs": "EPSG:4326",
            "notice": "Copia exacta de los vértices existentes; no incorpora una delimitación nueva.",
        },
    }
    destino = BASE / "web/layers/vertices-limites-cayma.geojson"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(features)} vértices exportados a {destino}")


if __name__ == "__main__":
    exportar()
