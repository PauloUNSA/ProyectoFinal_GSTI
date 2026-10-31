"""Franjas y clasificación geométrica, compartidas por el visor y la CNN.

El rojo ocupa el corredor entre los dos límites documentales. El amarillo
es su ampliación exterior en metros UTM, excluyendo el corredor rojo.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

COLORES = {"rojo": "#dc2626", "amarillo": "#eab308", "verde": "#16a34a", "desconocido": "#66788b"}
ETIQUETAS = {
    "rojo": "Rojo · entre límites documentales ANA",
    "amarillo": "Amarillo · franja exterior",
    "verde": "Verde · fuera de franjas",
    "desconocido": "Sin evaluación",
}

@dataclass(frozen=True)
class FranjaProximidad:
    building_id: str
    distancia_m: Optional[float]
    clase: str
    etiqueta: str
    color: str
    dentro_banda: bool


def clasificar_distancia(distancia_m, rojo_m, amarillo_m):
    """Clasificador escalar legado; la CNN usa intersecciones de polígonos."""
    if distancia_m is None or not math.isfinite(distancia_m) or distancia_m < 0:
        return FranjaProximidad("", None, "desconocido", ETIQUETAS["desconocido"], COLORES["desconocido"], False)
    clase = "rojo" if distancia_m <= rojo_m else "amarillo" if distancia_m <= rojo_m + amarillo_m else "verde"
    return FranjaProximidad("", float(distancia_m), clase, ETIQUETAS[clase], COLORES[clase], clase != "verde")


def _margenes(limites):
    """Obtiene ambas líneas en WGS84, orientadas en el mismo sentido."""
    from shapely.geometry import LineString
    if hasattr(limites, "to_crs"):
        limites = limites.to_crs("EPSG:4326").__geo_interface__
    features = limites.get("features", [])
    coords = {}
    for bank in ("Derecha", "Izquierda"):
        feature = next((f for f in features if f.get("properties", {}).get("bank") == bank), None)
        if not feature or feature["geometry"]["type"] != "LineString":
            raise ValueError("Se requieren los límites Derecha e Izquierda como LineString.")
        coords[bank] = feature["geometry"]["coordinates"]
        if len(coords[bank]) < 2:
            raise ValueError("Cada límite necesita al menos dos vértices.")
    d, i = coords["Derecha"], coords["Izquierda"]
    distancia = lambda a, b: (a[0]-b[0])**2 + (a[1]-b[1])**2
    if distancia(d[0], i[-1]) + distancia(d[-1], i[0]) < distancia(d[0], i[0]) + distancia(d[-1], i[-1]):
        i = list(reversed(i))
    return LineString(d), LineString(i)


def calcular_linea_cauce_desde_limites(limites):
    """Referencia central abierta: nunca conecta el final con el inicio."""
    from shapely.geometry import LineString
    if limites is None or (hasattr(limites, "empty") and limites.empty):
        return None
    d, i = _margenes(limites)
    if len(d.coords) == len(i.coords):
        pares = zip(d.coords, i.coords)
    else:
        n = max(len(d.coords), len(i.coords))
        pares = ((d.interpolate(k/(n-1), normalized=True).coords[0], i.interpolate(k/(n-1), normalized=True).coords[0]) for k in range(n))
    return LineString([((a[0]+b[0])/2, (a[1]+b[1])/2) for a, b in pares])


def construir_zonas(limites, amarillo_m=20, crs_metrico="EPSG:32719"):
    from pyproj import Transformer
    from shapely.geometry import Polygon
    from shapely import transform as _transform
    def transform(fn, geom):
        return _transform(geom, fn, interleaved=False)
    from shapely import make_valid
    if not math.isfinite(amarillo_m) or not 0 <= amarillo_m <= 500:
        raise ValueError("El ancho amarillo debe estar entre 0 y 500 metros.")
    d, i = _margenes(limites)
    a_m = Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True).transform
    a_wgs = Transformer.from_crs(crs_metrico, "EPSG:4326", always_xy=True).transform
    d_m, i_m = transform(a_m, d), transform(a_m, i)
    rojo = Polygon(list(d_m.coords) + list(reversed(i_m.coords)))
    if not rojo.is_valid:
        rojo = make_valid(rojo)
    if rojo.geom_type not in ("Polygon", "MultiPolygon") or rojo.is_empty:
        raise ValueError("Los límites no forman un corredor poligonal válido.")
    exterior = rojo.buffer(amarillo_m, join_style=2, mitre_limit=3) if amarillo_m else rojo
    return {
        "rojo": rojo,
        "amarillo": exterior.difference(rojo),
        "exterior": exterior,
        "cauce": transform(a_m, calcular_linea_cauce_desde_limites(limites)),
        "a_wgs": a_wgs,
        "a_m": a_m,
        "amarillo_m": amarillo_m,
        "crs": crs_metrico,
    }


def generar_poligonos_banda(limites, rojo_m=4, amarillo_m=20, crs_metrico="EPSG:32719"):
    """GeoJSON íntegro: conserva anillos interiores y geometrías múltiples.

    rojo_m se conserva como metadato documental; el ancho real del corredor
    lo fijan las líneas azul y morada, no un buffer constante desde el eje.
    """
    from shapely.geometry import mapping
    from shapely import transform as _transform
    def transform(fn, geom):
        return _transform(geom, fn, interleaved=False)
    zonas = construir_zonas(limites, amarillo_m, crs_metrico)
    salida = {}
    for clase in ("amarillo", "rojo", "cauce"):
        salida[clase] = {
            "type": "Feature",
            "geometry": mapping(transform(zonas["a_wgs"], zonas[clase])),
            "properties": {
                "clase": clase,
                "etiqueta": ETIQUETAS.get(clase, "Referencia central del cauce"),
                "color": COLORES.get(clase, "#07838a"),
            },
        }
    salida["metadata"] = {
        "geometria": "corredor_entre_limites",
        "rojo_m_documental": rojo_m,
        "amarillo_m": amarillo_m,
        "crs": crs_metrico,
        "medicion": "Amarillo desde el borde del corredor; rojo entre ambos límites documentales.",
    }
    return salida


def evaluar_edificio(geometria_metrica, zonas):
    """Da prioridad al rojo cuando cualquier parte del contorno lo toca."""
    if geometria_metrica.intersects(zonas["rojo"]):
        clase = "rojo"
    elif geometria_metrica.intersects(zonas["exterior"]):
        clase = "amarillo"
    else:
        clase = "verde"
    return {
        "clase": clase,
        "etiqueta": ETIQUETAS[clase],
        "color": COLORES[clase],
        "dentro_banda": clase in ("rojo", "amarillo"),
        "distance_m": float(geometria_metrica.distance(zonas["rojo"])),
        "distance_axis_m": float(geometria_metrica.distance(zonas["cauce"])),
    }
