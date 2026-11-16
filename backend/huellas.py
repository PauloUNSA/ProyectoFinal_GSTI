"""Limpieza y alineación de huellas automáticas (Overture) antes de entrenar.

Las huellas de Google, Microsoft y OpenStreetMap se dibujaron sobre otras
imágenes: pueden llegar desplazadas unos metros respecto a Esri y algunas
cubren lotes o manzanas enteras. Con techos de 15–30 px, ambos defectos
enseñan al modelo contornos equivocados.

- `limpiar`: descarta polígonos diminutos y marca los enormes (lotes, manzanas o
  naves industriales) para ignorarlos: el dataset pinta su área de gris, así no
  cuentan ni como techo ni como fondo.
- `estimar_desplazamiento`: busca, para cada fuente, el
  corrimiento entero en píxeles que más hace coincidir los bordes de las
  huellas con los bordes de la imagen (gradiente de luminancia).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

AREA_MIN_M2 = 6.0
AREA_MAX_M2 = 1500.0
MAX_DESPLAZAMIENTO_PX = 8      # ±4 m a 0.5 m/px
MIN_HUELLAS_ALINEAR = 25
GANANCIA_MINIMA = 1.04         # el mejor corrimiento debe superar al nulo en ≥ 4 %


def limpiar(geoms_m, area_min=AREA_MIN_M2, area_max=AREA_MAX_M2):
    """Índices conservados y conteo de descartes por motivo (geometrías en metros)."""
    conservados, descartes = [], {"diminuta": 0, "lote_o_manzana": 0}
    for i, g in enumerate(geoms_m):
        if g.area < area_min:
            descartes["diminuta"] += 1
        elif g.area > area_max:
            descartes["lote_o_manzana"] += 1
        else:
            conservados.append(i)
    return conservados, descartes


def gradiente(rgb):
    """Magnitud del gradiente de luminancia, suavizada 3×3."""
    gris = rgb[..., :3].astype(np.float32).mean(-1)
    pad = np.pad(gris, 1, mode="edge")
    suave = sum(pad[dy:dy + gris.shape[0], dx:dx + gris.shape[1]] for dy in range(3) for dx in range(3)) / 9
    gy, gx = np.gradient(suave)
    return np.hypot(gx, gy)


def bordes(geoms_px, alto, ancho):
    """Máscara de los contornos de los polígonos (coordenadas ya en píxeles)."""
    from rasterio.features import rasterize
    lineas = [g.boundary for g in geoms_px if not g.is_empty]
    if not lineas:
        return np.zeros((alto, ancho), bool)
    return rasterize([(l, 1) for l in lineas], out_shape=(alto, ancho), all_touched=True, dtype="uint8").astype(bool)


def estimar_desplazamiento(grad, borde, maximo=MAX_DESPLAZAMIENTO_PX):
    """(dx, dy, ganancia): corrimiento de las huellas que maximiza el gradiente bajo sus bordes."""
    ys, xs = np.nonzero(borde)
    if not len(ys):
        return 0, 0, 1.0
    alto, ancho = grad.shape
    puntajes = {}
    for dy in range(-maximo, maximo + 1):
        for dx in range(-maximo, maximo + 1):
            y, x = ys + dy, xs + dx
            ok = (y >= 0) & (y < alto) & (x >= 0) & (x < ancho)
            puntajes[(dx, dy)] = grad[y[ok], x[ok]].mean() if ok.any() else 0.0
    (dx, dy), mejor = max(puntajes.items(), key=lambda kv: kv[1])
    cero = puntajes[(0, 0)] or 1e-9
    return dx, dy, float(mejor / cero)


def alinear(rgb, transform, geoms_m, fuentes, ventana_px=None):
    """Desplaza las huellas por fuente y ventana. Devuelve geometrías nuevas y el registro de corrimientos.

    `geoms_m` está en el CRS del raster (metros) y `transform` es su afín. Por defecto se
    estima un solo corrimiento por fuente para toda la imagen: por ventanas pequeñas las
    sombras y la altura de los edificios lo vuelven inestable.
    """
    from shapely import affinity, transform as transformar
    a, b, c, d, e, f = (~transform)[:6]

    def a_px(xy):
        return np.column_stack((a * xy[:, 0] + b * xy[:, 1] + c, d * xy[:, 0] + e * xy[:, 1] + f))

    grad = gradiente(rgb)
    alto, ancho = grad.shape
    ventana_px = ventana_px or max(alto, ancho)
    grupos = defaultdict(list)
    for i, g in enumerate(geoms_m):
        cx, cy = a_px(np.array([[g.centroid.x, g.centroid.y]]))[0]
        clave = (fuentes[i], int(min(max(cy, 0), alto - 1)) // ventana_px, int(min(max(cx, 0), ancho - 1)) // ventana_px)
        grupos[clave].append(i)
    nuevas, registro = list(geoms_m), []
    for (fuente, fila, col), indices in sorted(grupos.items()):
        if len(indices) < MIN_HUELLAS_ALINEAR:
            registro.append({"fuente": fuente, "ventana": [fila, col], "huellas": len(indices), "dx_px": 0, "dy_px": 0,
                             "ganancia": None, "aplicado": False, "motivo": "pocas huellas"})
            continue
        y0, x0 = fila * ventana_px, col * ventana_px
        sub = grad[y0:y0 + ventana_px, x0:x0 + ventana_px]
        px = [transformar(geoms_m[i], lambda xy: a_px(xy) - [x0, y0]) for i in indices]
        dx, dy, ganancia = estimar_desplazamiento(sub, bordes(px, *sub.shape))
        # Un máximo en el borde de la búsqueda suele ser una coincidencia espuria con calles o sombras.
        en_borde = MAX_DESPLAZAMIENTO_PX in (abs(dx), abs(dy))
        aplicado = (dx, dy) != (0, 0) and ganancia >= GANANCIA_MINIMA and not en_borde
        if aplicado:
            # Un píxel a la derecha es +x en el mapa; uno hacia abajo es −y (norte arriba).
            mx, my = dx * transform.a, dy * transform.e
            for i in indices:
                nuevas[i] = affinity.translate(geoms_m[i], mx, my)
        registro.append({"fuente": fuente, "ventana": [fila, col], "huellas": len(indices), "dx_px": dx, "dy_px": dy,
                         "ganancia": round(ganancia, 3), "aplicado": aplicado,
                         **({"motivo": "máximo en el borde de la búsqueda"} if en_borde else {})})
    return nuevas, registro


def descargar_overture(bbox_wgs84, release=None):
    """Huellas de Overture (tema buildings) que tocan el recuadro, como features GeoJSON WGS84."""
    import shapely
    from overturemaps import core
    from shapely.geometry import mapping
    release = release or core.get_latest_release()
    lector = core.record_batch_reader("building", bbox=tuple(bbox_wgs84), release=release)
    filas = lector.read_all().select(["id", "geometry", "sources", "is_underground"]).to_pylist() if lector is not None else []
    features = []
    for fila in filas:
        if fila.get("is_underground"):
            continue
        geom = shapely.from_wkb(fila["geometry"])
        if geom.geom_type in ("Polygon", "MultiPolygon") and not geom.is_empty:
            fuente = ((fila.get("sources") or [{}])[0] or {}).get("dataset") or "desconocida"
            features.append({"type": "Feature", "geometry": mapping(geom),
                             "properties": {"origen": f"overture:{fuente}", "overture_id": fila["id"]}})
    return features, release


def preparar(rgb, transform, crs, features_wgs84):
    """Limpia y alinea features GeoJSON (WGS84); devuelve features WGS84 y un resumen."""
    from pyproj import Transformer
    from shapely.geometry import mapping, shape
    from shapely import transform as transformar
    a_m = Transformer.from_crs(4326, crs, always_xy=True).transform
    a_wgs = Transformer.from_crs(crs, 4326, always_xy=True).transform
    geoms, fuentes, props = [], [], []
    for f in features_wgs84:
        g = transformar(shape(f["geometry"]), a_m, interleaved=False)
        for parte in getattr(g, "geoms", [g]):
            if parte.geom_type == "Polygon" and not parte.is_empty:
                geoms.append(parte)
                origen = (f.get("properties") or {}).get("origen", "desconocida")
                fuentes.append(origen)
                props.append(f.get("properties") or {})
    conservados, descartes = limpiar(geoms)
    grandes = {i for i, g in enumerate(geoms) if g.area > AREA_MAX_M2}
    props = [{**p, "ignorar": True} if i in grandes else p for i, p in enumerate(props)]
    indices = sorted(set(conservados) | grandes)
    geoms = [geoms[i] for i in indices]
    fuentes = [fuentes[i] for i in indices]
    props = [props[i] for i in indices]
    alineadas, registro = alinear(rgb, transform, geoms, fuentes)
    salida = [{"type": "Feature", "geometry": mapping(transformar(g, a_wgs, interleaved=False)), "properties": p}
              for g, p in zip(alineadas, props)]
    descartes = {"diminuta": descartes["diminuta"], "ignorada_grande": descartes["lote_o_manzana"]}
    return salida, {"entrada": len(features_wgs84), "conservadas": len(salida), "descartes": descartes,
                    "alineacion": registro}
