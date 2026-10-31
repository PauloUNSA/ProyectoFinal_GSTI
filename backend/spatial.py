"""Análisis espacial: línea del cauce, franjas de proximidad y distancias
edificio-cauce.

La línea del cauce se obtiene UNIENDO los dos límites documentales de ANA
(margen derecha e izquierda) punto a punto, calculando el punto medio entre
ambas márgenes en cada vértice. Esto produce una línea continua que representa
el cauce de la torrentera, no un eje aproximado arbitrario.

Las franjas de proximidad usan valores reales de los documentos ANA:
- Rojo: 0 a 4 m (ancho de faja documental por margen, RD 1610-2018)
- Amarillo: 4 m a 4 + amarilloM (franja de seguridad adicional)
- Verde: más allá del límite exterior

No evalúa peligro real ni permiso para construir. Son criterios basados en
los documentos ANA, no criterios ilustrativos inventados.

Dependencias opcionales:
- geopandas, pandas: solo para calcular_linea_cauce_desde_limites
- shapely, pyproj: solo para generar_poligonos_banda
- numpy: requerido para clasificar_distancia
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class FranjaProximidad:
    """Resultado del análisis de proximidad para un edificio."""

    building_id: str
    distancia_m: Optional[float]
    clase: str  # "rojo", "amarillo", "verde", "desconocido"
    etiqueta: str
    color: str
    dentro_banda: bool


COLORES = {
    "rojo": "#dc2626",
    "amarillo": "#eab308",
    "verde": "#16a34a",
    "desconocido": "#66788b",
}

ETIQUETAS = {
    "rojo": "Rojo · dentro faja documental ANA",
    "amarillo": "Amarillo · franja de seguridad",
    "verde": "Verde · fuera de franjas ANA",
    "desconocido": "Sin evaluación",
}


def clasificar_distancia(
    distancia_m: Optional[float],
    rojo_m: float,
    amarillo_m: float,
) -> FranjaProximidad:
    """Clasifica un edificio por su distancia a la línea del cauce.

    - rojo: distancia <= rojo_m   (faja documental, 4 m por margen según ANA)
    - amarillo: rojo_m < distancia <= rojo_m + amarillo_m  (franja de seguridad)
    - verde: distancia > rojo_m + amarillo_m
    - desconocido: distancia no válida
    """
    exterior = rojo_m + amarillo_m

    if distancia_m is None or not np.isfinite(distancia_m) or distancia_m < 0:
        return FranjaProximidad(
            building_id="",
            distancia_m=None,
            clase="desconocido",
            etiqueta=ETIQUETAS["desconocido"],
            color=COLORES["desconocido"],
            dentro_banda=False,
        )

    if distancia_m <= rojo_m:
        clase = "rojo"
    elif distancia_m <= exterior:
        clase = "amarillo"
    else:
        clase = "verde"

    return FranjaProximidad(
        building_id="",
        distancia_m=float(distancia_m),
        clase=clase,
        etiqueta=ETIQUETAS[clase],
        color=COLORES[clase],
        dentro_banda=clase in ("rojo", "amarillo"),
    )


def calcular_linea_cauce_desde_limites(limites_gdf):
    """Calcula la línea del cauce UNIENDO los dos límites documentales de ANA.

    Para cada vértice i, toma el punto medio entre el vértice i del margen
    derecho y el vértice i del margen izquierdo. Los puntos medios se conectan
    en orden para formar una línea continua que representa el cauce de la
    torrentera.

    Requiere geopandas y shapely. Devuelve None si no están instalados o si
    los límites no son válidos.

    Parámetros:
        limites_gdf: GeoDataFrame con geometrías LineString y columna 'bank'
                     con valores 'Derecha' e 'Izquierda'.

    Retorna:
        shapely.geometry.LineString con la línea del cauce, o None.
    """
    try:
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import LineString, MultiLineString
    except ImportError:
        return None

    if limites_gdf is None or len(limites_gdf) == 0:
        return None

    try:
        derechas = limites_gdf[limites_gdf.get("bank", pd.Series([""])) == "Derecha"]
        izquierdas = limites_gdf[limites_gdf.get("bank", pd.Series([""])) == "Izquierda"]
    except Exception:
        return None

    if len(derechas) == 0 or len(izquierdas) == 0:
        return None

    linea_d = derechas.geometry.iloc[0]
    linea_i = izquierdas.geometry.iloc[0]

    if not isinstance(linea_d, (LineString, MultiLineString)) or not isinstance(
        linea_i, (LineString, MultiLineString)
    ):
        return None

    if isinstance(linea_d, MultiLineString):
        linea_d = max(linea_d.geoms, key=lambda g: g.length)
    if isinstance(linea_i, MultiLineString):
        linea_i = max(linea_i.geoms, key=lambda g: g.length)

    coords_d = list(linea_d.coords)
    coords_i = list(linea_i.coords)

    n = min(len(coords_d), len(coords_i))
    if n < 2:
        return None

    cauce_coords = []
    for i in range(n):
        lon = (coords_d[i][0] + coords_i[i][0]) / 2.0
        lat = (coords_d[i][1] + coords_i[i][1]) / 2.0
        cauce_coords.append((lon, lat))

    # Cerrar la línea uniendo el último con el primero (polígono aproximado del cauce)
    if len(cauce_coords) > 2:
        cauce_coords.append(cauce_coords[0])

    return LineString(cauce_coords)


def generar_poligonos_banda(
    cauce,
    rojo_m: float,
    amarillo_m: float,
    crs_metrico: str = "EPSG:32719",
):
    """Genera polígonos de las zonas roja y amarilla como buffers alrededor
    de la línea del cauce, transformados a WGS84 para Leaflet.

    - Rojo: buffer de rojo_m metros (faja documental, 4 m por margen según ANA)
    - Amarillo: buffer de rojo_m + amarillo_m menos el buffer rojo (franja de seguridad)

    Requiere shapely y pyproj. Devuelve None si no están instalados.

    Parámetros:
        cauce: shapely.geometry.LineString de la línea del cauce.
        rojo_m: ancho de la faja documental en metros (por defecto 4).
        amarillo_m: ancho de la franja de seguridad adicional en metros.
        crs_metrico: CRS proyectado para calcular buffers en metros.

    Retorna:
        dict con claves 'rojo', 'amarillo', 'cauce' (GeoJSON-like) y 'metadata'.
    """
    try:
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        from pyproj import Transformer
    except ImportError:
        return None

    if cauce is None:
        return None

    transformador_a_metric = Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    transformador_a_wgs84 = Transformer.from_crs(crs_metrico, "EPSG:4326", always_xy=True)

    coords_metric = [
        transformador_a_metric.transform(lon, lat) for lon, lat in cauce.coords
    ]
    cauce_metrico = LineString(coords_metric)

    rojo_buffer = cauce_metrico.buffer(rojo_m)
    exterior_buffer = cauce_metrico.buffer(rojo_m + amarillo_m)
    amarillo_puro = exterior_buffer.difference(rojo_buffer)

    def a_wgs84(geom):
        coords_wgs = [
            transformador_a_wgs84.transform(x, y) for x, y in geom.exterior.coords
        ]
        return {"type": "Polygon", "coordinates": [coords_wgs]}

    rojo_geojson = {
        "type": "Feature",
        "geometry": a_wgs84(rojo_buffer),
        "properties": {"clase": "rojo"},
    }
    amarillo_geojson = {
        "type": "Feature",
        "geometry": a_wgs84(amarillo_puro),
        "properties": {"clase": "amarillo"},
    }
    cauce_geojson = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": list(cauce.coords)},
        "properties": {"clase": "cauce"},
    }

    return {
        "rojo": rojo_geojson,
        "amarillo": amarillo_geojson,
        "cauce": cauce_geojson,
        "metadata": {
            "rojo_m": rojo_m,
            "amarillo_m": amarillo_m,
            "exterior_m": rojo_m + amarillo_m,
            "crs": crs_metrico,
            "fuente": "Límites documentales ANA Cayma (Tabla 02, planos pp. 40-44)",
        },
    }


__all__ = [
    "FranjaProximidad",
    "clasificar_distancia",
    "calcular_linea_cauce_desde_limites",
    "generar_poligonos_banda",
    "COLORES",
    "ETIQUETAS",
]
