"""Celdas de anotación y conversión de techos georreferenciados a YOLO-seg.

Flujo:
1. `generar_celdas` divide el GeoTIFF en celdas cuadradas (256 px = 128 m a
   0.5 m/px) que tocan las franjas roja o amarilla y les asigna un split
   estable por bloques a lo largo del cauce.
2. Una persona dibuja en QGIS todos los techos de las celdas que elige y
   marca esas celdas con estado = "completa".
3. `armar_dataset` recorta cada celda completa como PNG y escribe sus
   polígonos normalizados en el formato de Ultralytics.

Solo se usan celdas completas: un techo sin dibujar dentro de un recorte
enseñaría al modelo que ese techo es fondo.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ESTADOS_COMPLETOS = {"completa", "completo"}
SPLITS = ("train", "val", "test")
# Bloques de 3 celdas consecutivas en el cauce: 3 de cada 5 bloques a train.
CICLO_SPLITS = ("train", "train", "train", "val", "test")
BLOQUE_CELDAS = 3


def crs_de_geojson(data: dict) -> str:
    """GeoJSON estándar es WGS84; QGIS puede guardar otro CRS en `crs`."""
    nombre = (data.get("crs") or {}).get("properties", {}).get("name", "")
    if not nombre or nombre.endswith("CRS84") or nombre.endswith("4326"):
        return "EPSG:4326"
    if "EPSG" in nombre:
        return "EPSG:" + nombre.replace("::", ":").split(":")[-1]
    return nombre


def _transformador(origen, destino):
    from pyproj import Transformer
    from shapely import transform as transformar
    fn = Transformer.from_crs(origen, destino, always_xy=True).transform
    return lambda geom: transformar(geom, fn, interleaved=False)


def hash_geometria(geom_wgs84) -> str:
    """Huella estable a ~1 cm para saber si un borrador se editó."""
    from shapely import set_precision
    return hashlib.sha256(set_precision(geom_wgs84, 1e-7).normalize().wkb).hexdigest()[:16]


def generar_celdas(src, exterior_m, cauce_m, crs_metrico="EPSG:32719", tamano_px=256):
    """Celdas alineadas a píxeles, completas dentro del raster y que tocan la zona."""
    from rasterio.windows import Window, bounds
    from shapely.geometry import box
    a_metros = _transformador(src.crs, crs_metrico)
    a_wgs = _transformador(src.crs, "EPSG:4326")
    nx, ny = src.width // tamano_px, src.height // tamano_px
    off_x, off_y = (src.width - nx * tamano_px) // 2, (src.height - ny * tamano_px) // 2
    celdas = []
    for j in range(ny):
        for i in range(nx):
            col, fila = off_x + i * tamano_px, off_y + j * tamano_px
            huella = box(*bounds(Window(col, fila, tamano_px, tamano_px), src.transform))
            metrica = a_metros(huella)
            if not metrica.intersects(exterior_m):
                continue
            celdas.append({"col_off": col, "row_off": fila, "huella": huella, "wgs84": a_wgs(huella),
                           "posicion_cauce_m": float(cauce_m.project(metrica.centroid))})
    celdas.sort(key=lambda c: (c["posicion_cauce_m"], c["row_off"], c["col_off"]))
    for orden, celda in enumerate(celdas):
        celda["id"] = f"c{orden:03d}"
        celda["orden"] = orden
        celda["split"] = CICLO_SPLITS[(orden // BLOQUE_CELDAS) % len(CICLO_SPLITS)]
    return celdas


def poligono_a_linea_yolo(geom_px, ancho, alto, area_minima_px=8.0, clase=0):
    """Recorta a la celda y devuelve líneas `clase x1 y1 ...` normalizadas."""
    from shapely.geometry import box
    recorte = geom_px.intersection(box(0, 0, ancho, alto))
    partes = getattr(recorte, "geoms", [recorte])
    lineas = []
    for parte in partes:
        if parte.geom_type != "Polygon" or parte.is_empty or parte.area < area_minima_px:
            continue
        # YOLO-seg admite un solo anillo por instancia; se usa el exterior.
        coords = list(parte.exterior.coords)[:-1]
        if len(coords) < 3:
            continue
        valores = []
        for x, y in coords:
            valores += [min(max(x / ancho, 0.0), 1.0), min(max(y / alto, 0.0), 1.0)]
        lineas.append(f"{clase} " + " ".join(f"{v:.6f}" for v in valores))
    return lineas


def leer_techos(path, crs_raster):
    """Polígonos de techos en el CRS del raster, con su huella de borrador."""
    from shapely.geometry import shape
    from shapely import make_valid
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    crs = crs_de_geojson(data)
    a_raster = _transformador(crs, crs_raster)
    a_wgs = _transformador(crs, "EPSG:4326")
    techos = []
    for f in data.get("features", []):
        if not f.get("geometry"):
            continue
        geom = shape(f["geometry"])
        if not geom.is_valid:
            geom = make_valid(geom)
        props = f.get("properties") or {}
        sin_modificar = bool(props.get("borrador_hash")) and hash_geometria(a_wgs(shape(f["geometry"]))) == props["borrador_hash"]
        for parte in getattr(geom, "geoms", [geom]):
            if parte.geom_type == "Polygon" and not parte.is_empty:
                techos.append({"geom": a_raster(parte), "sin_modificar": sin_modificar})
    return techos


def leer_celdas(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    crs = crs_de_geojson(data)
    from shapely.geometry import shape
    a_wgs = _transformador(crs, "EPSG:4326")
    celdas = []
    for f in data.get("features", []):
        p = f.get("properties") or {}
        faltan = [k for k in ("id", "col_off", "row_off", "tamano_px", "split") if p.get(k) is None]
        if faltan:
            raise ValueError(f"Una celda no tiene {', '.join(faltan)}; regenera celdas.geojson sin borrar esas columnas.")
        if p["split"] not in SPLITS:
            raise ValueError(f"Celda {p['id']}: split debe ser train, val o test.")
        celdas.append({**p, "col_off": int(p["col_off"]), "row_off": int(p["row_off"]), "tamano_px": int(p["tamano_px"]),
                       "completa": str(p.get("estado") or "").strip().lower() in ESTADOS_COMPLETOS,
                       "wgs84": a_wgs(shape(f["geometry"]))})
    return celdas


def _escribir_recorte(src, col, fila, tam, techos, indice, destino_img, destino_lbl, nombre):
    import numpy as np
    from PIL import Image
    from rasterio.windows import Window, bounds
    from shapely.geometry import box
    from shapely import transform as transformar
    ventana = Window(col, fila, tam, tam)
    huella = box(*bounds(ventana, src.transform))
    a, b, c, d, e, f = (~src.window_transform(ventana))[:6]

    def a_pixeles(xy):
        return np.column_stack((a * xy[:, 0] + b * xy[:, 1] + c, d * xy[:, 0] + e * xy[:, 1] + f))

    lineas, sin_modificar = [], 0
    for k in indice.query(huella, predicate="intersects"):
        techo = techos[k]
        px = transformar(techo["geom"], a_pixeles)
        nuevas = poligono_a_linea_yolo(px, tam, tam)
        lineas += nuevas
        sin_modificar += bool(nuevas) and techo["sin_modificar"]
    rgb = src.read([1, 2, 3], window=ventana).transpose(1, 2, 0)
    Image.fromarray(rgb).save(destino_img / f"{nombre}.png")
    (destino_lbl / f"{nombre}.txt").write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
    return len(lineas), sin_modificar


def armar_dataset(imagen, celdas_path, techos_path, destino, imgsz=640, desplazados=True):
    """Escribe images/, labels/, data.yaml y resumen.json en `destino`."""
    import shutil
    import rasterio
    from shapely import STRtree
    destino = Path(destino)
    if destino.exists():
        if not (destino / "data.yaml").is_file():
            raise ValueError(f"{destino} existe y no parece un dataset generado; elige otra carpeta.")
        shutil.rmtree(destino)
    celdas = leer_celdas(celdas_path)
    completas = [c for c in celdas if c["completa"]]
    if not any(c["split"] == "train" for c in completas):
        raise ValueError("No hay celdas train con estado = completa en celdas.geojson.")
    tamanos = {c["tamano_px"] for c in celdas}
    if len(tamanos) != 1:
        raise ValueError("Todas las celdas deben tener el mismo tamano_px.")
    tam = tamanos.pop()
    resumen = {"imagen": str(Path(imagen).name), "tile_px": tam, "imgsz": imgsz, "splits": {}, "avisos": []}
    with rasterio.open(imagen) as src:
        resumen["resolucion_m"] = abs(src.transform.a)
        resumen["imagen_sha256"] = _sha256(imagen)
        a_wgs = _transformador(src.crs, "EPSG:4326")
        techos = leer_techos(techos_path, src.crs)
        indice = STRtree([t["geom"] for t in techos])
        from rasterio.windows import Window, bounds
        from shapely.geometry import box
        for c in completas:
            # La ventana en píxeles debe caer sobre la misma celda dibujada en el mapa.
            centro = a_wgs(box(*bounds(Window(c["col_off"], c["row_off"], tam, tam), src.transform))).centroid
            if centro.distance(c["wgs84"].centroid) > 2e-5:  # ≈ 2 m
                raise ValueError(f"La celda {c['id']} no coincide con {Path(imagen).name}; ¿se generó con otra imagen?")
        posiciones = {(c["col_off"], c["row_off"]): c for c in completas}
        for split in SPLITS:
            img_dir, lbl_dir = destino / "images" / split, destino / "labels" / split
            img_dir.mkdir(parents=True), lbl_dir.mkdir(parents=True)
            stats = {"celdas": 0, "recortes": 0, "techos": 0, "recortes_vacios": 0, "techos_borrador_sin_modificar": 0}
            for c in (c for c in completas if c["split"] == split):
                n, sin_mod = _escribir_recorte(src, c["col_off"], c["row_off"], tam, techos, indice, img_dir, lbl_dir, c["id"])
                stats["celdas"] += 1
                stats["recortes"] += 1
                stats["techos"] += n
                stats["recortes_vacios"] += n == 0
                stats["techos_borrador_sin_modificar"] += sin_mod
                if split != "train" or not desplazados:
                    continue
                # Recortes a media celda: solo si todas las celdas que cubren son train y completas.
                medio = tam // 2
                for dx, dy in ((medio, 0), (0, medio), (medio, medio)):
                    col, fila = c["col_off"] + dx, c["row_off"] + dy
                    cubren = {(c["col_off"] + a * tam, c["row_off"] + b * tam)
                              for a in range(2 if dx else 1) for b in range(2 if dy else 1)}
                    if all(p in posiciones and posiciones[p]["split"] == "train" for p in cubren):
                        n, _ = _escribir_recorte(src, col, fila, tam, techos, indice, img_dir, lbl_dir, f"{c['id']}_d{dx}_{dy}")
                        stats["recortes"] += 1
                        stats["instancias_desplazadas"] = stats.get("instancias_desplazadas", 0) + n
            resumen["splits"][split] = stats
    for split in ("val", "test"):
        if not resumen["splits"][split]["celdas"]:
            resumen["avisos"].append(f"No hay celdas {split} completas: las métricas de {split} no serán fiables.")
    total = sum(s["techos"] for s in resumen["splits"].values())
    sin_mod = sum(s["techos_borrador_sin_modificar"] for s in resumen["splits"].values())
    if total and sin_mod / total > 0.5:
        resumen["avisos"].append(f"{sin_mod} de {total} techos son del borrador Mask R-CNN sin editar; revisa que sean correctos.")
    (destino / "data.yaml").write_text(
        f"path: {destino.resolve().as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: techo\n", encoding="utf-8")
    (destino / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            digest.update(bloque)
    return digest.hexdigest()


def celdas_a_geojson(celdas, tamano_px, conteo_borrador):
    from shapely.geometry import mapping
    return {"type": "FeatureCollection", "name": "celdas_anotacion", "features": [
        {"type": "Feature", "geometry": mapping(c["wgs84"]), "properties": {
            "id": c["id"], "estado": "pendiente", "split": c["split"], "orden": c["orden"],
            "techos_borrador": conteo_borrador.get(c["id"], 0),
            "col_off": c["col_off"], "row_off": c["row_off"], "tamano_px": tamano_px}}
        for c in celdas]}


def borrador_desde_detecciones(detecciones, celdas):
    """Copia las detecciones como punto de partida, con una huella para saber si se editaron."""
    from shapely.geometry import mapping, shape
    from shapely import STRtree
    indice = STRtree([c["wgs84"] for c in celdas])
    features, conteo = [], {}
    for f in detecciones.get("features", []):
        geom = shape(f["geometry"])
        tocadas = indice.query(geom, predicate="intersects")
        if not len(tocadas):
            continue
        for k in tocadas:
            conteo[celdas[k]["id"]] = conteo.get(celdas[k]["id"], 0) + 1
        features.append({"type": "Feature", "geometry": mapping(geom), "properties": {
            "origen": "borrador_maskrcnn", "borrador_hash": hash_geometria(geom),
            "confianza_borrador": round(float(f["properties"].get("confidence", math.nan)), 3)}})
    return {"type": "FeatureCollection", "name": "techos", "features": features}, conteo
