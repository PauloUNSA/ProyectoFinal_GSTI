"""Cauce/riberas y dos fajas marginales, compartidos por visor y detector.

Reconstrucción aproximada: 4 m hacia dentro de cada límite exterior ANA.
El residual central no sustituye una delimitación interior medida en campo.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

COLORES = {"rojo": "#dc2626", "naranja": "#f97316", "amarillo": "#eab308", "verde": "#16a34a", "desconocido": "#66788b"}
ETIQUETAS = {
    "rojo": "Rojo · cauce y riberas (aproximado)",
    "naranja": "Naranja · faja marginal (aproximada)",
    "amarillo": "Amarillo · alcance simulado de huaicos (aproximado)",
    "verde": "Fuera del ámbito · sin evaluación de seguridad",
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


def construir_zonas(limites, amarillo_m=0, crs_metrico="EPSG:32719", huella_huaico=None, distrito=None):
    from pyproj import Transformer
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union
    from shapely import transform as _transform
    def transform(fn, geom):
        return _transform(geom, fn, interleaved=False)
    from shapely import make_valid
    if not math.isfinite(amarillo_m) or amarillo_m != 0:
        raise ValueError("El alcance de huaicos procede de INGEMMET: amarillo_m debe ser 0.")
    d, i = _margenes(limites)
    a_m = Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True).transform
    a_wgs = Transformer.from_crs(crs_metrico, "EPSG:4326", always_xy=True).transform
    d_m, i_m = transform(a_m, d), transform(a_m, i)
    rojo = Polygon(list(d_m.coords) + list(reversed(i_m.coords)))
    if not rojo.is_valid:
        rojo = make_valid(rojo)
    if rojo.geom_type not in ("Polygon", "MultiPolygon") or rojo.is_empty:
        raise ValueError("Los límites no forman un corredor poligonal válido.")
    corredor = rojo
    # Recortar buffers de las dos líneas laterales al corredor: nunca ampliar
    # fuera de los límites ni retraer artificialmente los extremos del tramo.
    derecha = d_m.buffer(4, join_style=1).intersection(corredor)
    izquierda = i_m.buffer(4, join_style=1).intersection(corredor)
    naranja = derecha.union(izquierda)
    rojo = corredor.difference(naranja)
    amarillo = Polygon()
    if huella_huaico is not None:
        piezas = [shape(feature["geometry"]) for feature in huella_huaico["features"]]
        if not piezas or any(g.geom_type not in ("Polygon", "MultiPolygon") or not g.is_valid or g.is_empty for g in piezas):
            raise ValueError("La huella de huaicos debe contener polígonos válidos.")
        # Las fronteras compartidas siguen clasificándose primero como cauce o faja.
        amarillo = transform(a_m, unary_union(piezas)).difference(corredor)
    cauce = transform(a_m, calcular_linea_cauce_desde_limites(limites))
    if distrito is not None:
        ambito = transform(a_m, shape(distrito["geometry"]))
        rojo = rojo.intersection(ambito)
        derecha = derecha.intersection(ambito)
        izquierda = izquierda.intersection(ambito)
        naranja = naranja.intersection(ambito)
        corredor = corredor.intersection(ambito)
        amarillo = amarillo.intersection(ambito)
        cauce = cauce.intersection(ambito)
    exterior = corredor.union(amarillo)
    return {
        "rojo": rojo,
        "naranja": naranja,
        "amarillo": amarillo,
        "faja_derecha": derecha,
        "faja_izquierda": izquierda,
        "corredor": corredor,
        "exterior": exterior,
        "cauce": cauce,
        "a_wgs": a_wgs,
        "a_m": a_m,
        "amarillo_m": amarillo_m,
        "crs": crs_metrico,
    }


def generar_poligonos_banda(limites, rojo_m=4, amarillo_m=0, crs_metrico="EPSG:32719", huella_huaico=None, distrito=None):
    """GeoJSON íntegro: conserva anillos interiores y geometrías múltiples.

    Los límites exteriores son documentales. La separación interior usa 4 m
    de distancia a cada línea lateral y es una reconstrucción aproximada.
    """
    from shapely.geometry import mapping
    from shapely import transform as _transform
    def transform(fn, geom):
        return _transform(geom, fn, interleaved=False)
    zonas = construir_zonas(limites, amarillo_m, crs_metrico, huella_huaico, distrito)
    salida = {}
    clases = ("naranja", "rojo", "cauce")
    if huella_huaico is not None:
        clases += ("amarillo",)
    for clase in clases:
        salida[clase] = {
            "type": "Feature",
            "geometry": mapping(transform(zonas["a_wgs"], zonas[clase])),
            "properties": {
                "clase": clase,
                "etiqueta": ETIQUETAS.get(clase, "Referencia central geométrica · no es un levantamiento del cauce"),
                "color": COLORES.get(clase, "#07838a"),
            },
        }
    salida["metadata"] = {
        "geometria": "cauce_fajas_reconstruccion_4m",
        "faja_m_por_margen": 4,
        "separacion_interior": "aproximada; sin coordenadas interiores oficiales",
        "rojo_m_documental": rojo_m,
        "amarillo_m": amarillo_m,
        "crs": crs_metrico,
        "distrito": distrito["properties"]["nombre"] if distrito else None,
        "medicion": "4 m hacia dentro desde cada límite exterior, recortados al corredor documental.",
        "buffer_join": "round",
        "red_scope": "Cauce y riberas aproximados: residual al descontar ambas fajas laterales reconstruidas.",
        "orange_scope": "Dos fajas marginales aproximadas de 4 m hacia dentro de los límites exteriores.",
        "outside_scope": "Sin evaluación; no implica seguridad ni autorización de edificar.",
    }
    return salida


def evaluar_edificio(geometria_metrica, zonas):
    """Da prioridad al rojo cuando cualquier parte del contorno lo toca."""
    if geometria_metrica.intersects(zonas["rojo"]):
        clase = "rojo"
    elif geometria_metrica.intersects(zonas["naranja"]):
        clase = "naranja"
    elif geometria_metrica.intersects(zonas["amarillo"]):
        clase = "amarillo"
    else:
        clase = "verde"
    return {
        "clase": clase,
        "etiqueta": ETIQUETAS[clase],
        "color": COLORES[clase],
        "dentro_banda": clase in ("rojo", "naranja", "amarillo"),
        "distance_m": float(geometria_metrica.distance(zonas["rojo"])),
        "distance_axis_m": float(geometria_metrica.distance(zonas["cauce"])),
        "geometry_status": "reconstruccion_aproximada",
    }
