"""Análisis espacial: franjas de proximidad y distancias edificio-cauce.

Calcula zonas de proximidad (roja, amarilla, verde) desde el eje de la
torrentera y clasifica edificios detectados por su distancia mínima al cauce.

No evalúa peligro real ni permiso para construir. Son criterios ilustrativos
del proyecto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union


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
    "rojo": "Rojo · proximidad inmediata",
    "amarillo": "Amarillo · proximidad intermedia",
    "verde": "Verde · mayor distancia",
    "desconocido": "Sin evaluación",
}


def clasificar_distancia(
    distancia_m: Optional[float],
    rojo_m: float,
    amarillo_m: float,
) -> FranjaProximidad:
    """Clasifica un edificio por su distancia al eje de la torrentera.

    - rojo: distancia <= rojo_m
    - amarillo: rojo_m < distancia <= rojo_m + amarillo_m
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


def calcular_eje_desde_limites(
    limites_gdf: gpd.GeoDataFrame,
) -> Optional[LineString]:
    """Calcula un eje aproximado de la torrentera como la línea media entre
    los límites exteriores documentados de ambas márgenes.

    Espera que limites_gdf tenga geometrías LineString y una columna 'bank'
    con valores 'Derecha' e 'Izquierda'.
    """
    if limites_gdf is None or len(limites_gdf) == 0:
        return None

    derechas = limites_gdf[limites_gdf.get("bank", pd.Series([""])) == "Derecha"]
    izquierdas = limites_gdf[limites_gdf.get("bank", pd.Series([""])) == "Izquierda"]

    if len(derechas) == 0 or len(izquierdas) == 0:
        return None

    # Tomar la línea más larga de cada margen como referencia
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

    ejes_coords = []
    for i in range(n):
        lon = (coords_d[i][0] + coords_i[i][0]) / 2.0
        lat = (coords_d[i][1] + coords_i[i][1]) / 2.0
        ejes_coords.append((lon, lat))

    return LineString(ejes_coords)


def generar_poligonos_banda(
    eje: LineString,
    rojo_m: float,
    amarillo_m: float,
    crs_metrico: str = "EPSG:32719",
) -> dict:
    """Genera polígonos de las zonas roja y amarilla como buffers alrededor
    del eje, transformados a WGS84 para Leaflet.

    Devuelve un dict con claves 'rojo', 'amarillo', 'eje' con GeoJSON-like
    dicts y metadatos.
    """
    from pyproj import Transformer

    transformador_a_metric = Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    transformador_a_wgs84 = Transformer.from_crs(crs_metrico, "EPSG:4326", always_xy=True)

    # Reproyectar eje a CRS metrico
    coords_metric = [
        transformador_a_metric.transform(lon, lat) for lon, lat in eje.coords
    ]
    eje_metrico = LineString(coords_metric)

    # Buffers en metros
    rojo_buffer = eje_metrico.buffer(rojo_m)
    amarillo_buffer = eje_metrico.buffer(rojo_m + amarillo_m)

    # Zona amarilla pura = exterior menos interior (aproximación)
    amarillo_puro = amarillo_buffer.difference(rojo_buffer)

    def a_wgs84(geom):
        coords_wgs = [
            transformador_a_wgs84.transform(x, y) for x, y in geom.exterior.coords
        ]
        return {"type": "Polygon", "coordinates": [coords_wgs]}

    rojo_geojson = {"type": "Feature", "geometry": a_wgs84(rojo_buffer), "properties": {"clase": "rojo"}}
    amarillo_geojson = {
        "type": "Feature",
        "geometry": a_wgs84(amarillo_puro),
        "properties": {"clase": "amarillo"},
    }
    eje_geojson = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": list(eje.coords)},
        "properties": {"clase": "eje"},
    }

    return {
        "rojo": rojo_geojson,
        "amarillo": amarillo_geojson,
        "eje": eje_geojson,
        "metadata": {
            "rojo_m": rojo_m,
            "amarillo_m": amarillo_m,
            "exterior_m": rojo_m + amarillo_m,
            "crs": crs_metrico,
        },
    }


# pandas import local para evitar dependencia si no se usa calcular_eje
import pandas as pd  # noqa: E402

__all__ = [
    "FranjaProximidad",
    "clasificar_distancia",
    "calcular_eje_desde_limites",
    "generar_poligonos_banda",
    "COLORES",
    "ETIQUETAS",
]
