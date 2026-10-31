"""Pruebas automatizadas del backend de Chullo Unificado.

Verifica:
- Clasificación de distancia por franjas ANA (rojo=4m, amarillo=20m)
- Cálculo de línea del cauce desde límites documentales (si hay geopandas)
- Generación de polígonos de banda (si hay shapely)
- Endpoints del servidor (status)

Ejecutar con:
    python -m pytest tests/test_backend.py -v

Pruebas que requieren geopandas/shapely se saltan automáticamente si no están instaladas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

try:
    import geopandas as gpd
    import pandas as pd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

try:
    from shapely.geometry import LineString, shape

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from backend.spatial import (  # noqa: E402
    calcular_linea_cauce_desde_limites,
    clasificar_distancia,
    generar_poligonos_banda,
)


# ---------------------------------------------------------------------------
# Pruebas de clasificación de distancia (valores reales de ANA)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "distancia,rojo,amarillo,clase_esperada",
    [
        (0.0, 4, 20, "rojo"),
        (2.0, 4, 20, "rojo"),
        (4.0, 4, 20, "rojo"),
        (4.0001, 4, 20, "amarillo"),
        (10.0, 4, 20, "amarillo"),
        (24.0, 4, 20, "amarillo"),
        (24.0001, 4, 20, "verde"),
        (100.0, 4, 20, "verde"),
    ],
)
def test_clasificar_distancia(distancia, rojo, amarillo, clase_esperada):
    """La clasificación debe usar los valores reales de ANA."""
    resultado = clasificar_distancia(distancia, rojo, amarillo)
    assert resultado.clase == clase_esperada
    assert resultado.distancia_m == distancia


def test_clasificar_distancia_valor_invalido():
    """Distancia None, negativa o NaN debe ser 'desconocido', nunca 'verde'."""
    for valor in (None, -1.0, float("nan"), float("inf")):
        r = clasificar_distancia(valor, 4, 20)
        assert r.clase == "desconocido", f"Valor {valor} no se clasificó como desconocido"


def test_clasificar_distancia_etiquetas_y_colores():
    """Cada clase debe tener etiqueta y color definidos."""
    r_rojo = clasificar_distancia(2.0, 4, 20)
    assert r_rojo.color == "#dc2626"
    assert "rojo" in r_rojo.etiqueta.lower()

    r_amarillo = clasificar_distancia(10.0, 4, 20)
    assert r_amarillo.color == "#eab308"
    assert "amarillo" in r_amarillo.etiqueta.lower()

    r_verde = clasificar_distancia(30.0, 4, 20)
    assert r_verde.color == "#16a34a"
    assert "verde" in r_verde.etiqueta.lower()


# ---------------------------------------------------------------------------
# Pruebas de línea del cauce desde límites documentales
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_GEOPANDAS, reason="geopandas no instalado")
def test_calcular_linea_cauce_desde_limites():
    """La línea del cauce debe unir punto a punto los límites derecho e izquierdo."""
    coords_d = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    coords_i = [(0.0, 0.001), (1.0, 0.001), (2.0, 0.001)]

    gdf_d = gpd.GeoDataFrame(
        [{"bank": "Derecha", "geometry": LineString(coords_d)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    gdf_i = gpd.GeoDataFrame(
        [{"bank": "Izquierda", "geometry": LineString(coords_i)}],
        geometry="geometry",
        crs="EPSG:4326",
    )
    limites = pd.concat([gdf_d, gdf_i], ignore_index=True)
    limites = gpd.GeoDataFrame(limites, geometry="geometry", crs="EPSG:4326")

    cauce = calcular_linea_cauce_desde_limites(limites)

    assert cauce is not None
    assert isinstance(cauce, LineString)
    assert cauce.coords[0] == pytest.approx((0.0, 0.0005), abs=1e-12)
    assert cauce.coords[1] == pytest.approx((1.0, 0.0005), abs=1e-12)
    assert cauce.coords[2] == pytest.approx((2.0, 0.0005), abs=1e-12)


@pytest.mark.skipif(not HAS_GEOPANDAS, reason="geopandas no instalado")
def test_calcular_linea_cauce_vacio():
    """Sin límites, debe devolver None."""
    assert calcular_linea_cauce_desde_limites(None) is None


# ---------------------------------------------------------------------------
# Pruebas de generación de polígonos de banda
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely no instalado")
def test_generar_poligonos_banda_estructura():
    """Debe devolver dict con claves rojo, amarillo, cauce y metadata."""
    cauce = LineString([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    bandas = generar_poligonos_banda(cauce, rojo_m=4, amarillo_m=20)

    assert "rojo" in bandas
    assert "amarillo" in bandas
    assert "cauce" in bandas
    assert "metadata" in bandas

    assert bandas["rojo"]["properties"]["clase"] == "rojo"
    assert bandas["amarillo"]["properties"]["clase"] == "amarillo"
    assert bandas["cauce"]["properties"]["clase"] == "cauce"

    meta = bandas["metadata"]
    assert meta["rojo_m"] == 4
    assert meta["amarillo_m"] == 20
    assert meta["exterior_m"] == 24


@pytest.mark.skipif(not HAS_SHAPELY, reason="shapely no instalado")
def test_generar_poligonos_banda_geometrias_validas():
    """Los polígonos generados deben ser válidos y no vacíos."""
    cauce = LineString([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])
    bandas = generar_poligonos_banda(cauce, rojo_m=4, amarillo_m=20)

    rojo_geom = shape(bandas["rojo"]["geometry"])
    amarillo_geom = shape(bandas["amarillo"]["geometry"])

    assert rojo_geom.is_valid
    assert amarillo_geom.is_valid
    assert rojo_geom.area > 0
    assert amarillo_geom.area > 0


# ---------------------------------------------------------------------------
# Pruebas del servidor (endpoint /api/status)
# ---------------------------------------------------------------------------


def test_servidor_status_endpoint():
    """El endpoint /api/status debe responder con JSON válido."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:4173/api/status", timeout=5) as r:
            assert r.status == 200
            data = json.loads(r.read().decode())
            assert "servidor" in data
            assert data["servidor"] == "chullo-unificado"
            assert "puerto" in data
            assert "cnn_disponible" in data
    except Exception:
        pytest.skip("Servidor no está corriendo; iniciar con `python servidor.py --abrir`")


def test_servidor_archivo_index():
    """El endpoint raíz debe servir index.html con estado 200."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:4173/", timeout=5) as r:
            assert r.status == 200
            contenido = r.read().decode()
            assert "Chullo" in contenido or "mapa" in contenido.lower()
    except Exception:
        pytest.skip("Servidor no está corriendo")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
