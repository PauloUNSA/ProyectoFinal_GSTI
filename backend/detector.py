"""Detección de cubiertas con CNN: YOLO-seg entrenado o Mask R-CNN piloto.

Ejecuta la inferencia por mosaicos sobre un GeoTIFF del sector Chullo y
genera GeoJSON con los contornos detectados, listos para el visor. Ambos
modelos comparten la vectorización, la clasificación por franjas y la
supresión de duplicados; solo cambia la predicción de cada mosaico.

Requisitos opcionales (instalar solo si se usa el detector):
  torch, rasterio, shapely, pyproj y torchvision (Mask R-CNN) o
  ultralytics (YOLO)

Si no están instalados, la detección no está disponible y el visor sigue
funcionando con datos estáticos (puntos ANA, límites, franjas).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    import rasterio
    import torch
    from pyproj import Transformer
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union
    from rasterio.features import shapes

    DEPENDENCIAS_DISPONIBLES = True
except ImportError as exc:  # pragma: no cover - depende del entorno
    DEPENDENCIAS_DISPONIBLES = False
    _ERROR_IMPORT = str(exc)


from backend import modelos

LOCAL_MODEL_PATH = modelos.MASKRCNN_DIR / "weights.pth"
LOCAL_MODEL_SHA256 = modelos.MASKRCNN_SHA256
MODEL_ID = "chullo/maskrcnn_chullo_local_v1"
LIMITACION_MASKRCNN = "Modelo local piloto: F1 de instancias 0.249 en dos recortes; no garantiza separar viviendas."


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cargar_modelo(dispositivo: str = "auto"):
    """Carga Mask R-CNN con los pesos verificados."""
    if not DEPENDENCIAS_DISPONIBLES:
        raise ImportError(
            "Faltan dependencias para el detector CNN: " + _ERROR_IMPORT
        )

    from torchvision.models.detection import maskrcnn_resnet50_fpn

    pesos = LOCAL_MODEL_PATH
    if not pesos.is_file() or sha256_file(pesos) != LOCAL_MODEL_SHA256:
        raise ValueError("Faltan los pesos verificados models/chullo_local_v1/weights.pth o su SHA256 no coincide.")
    torch.set_num_threads(min(4, (torch.cuda.device_count() or 1) if dispositivo == "cuda" else 4))

    seleccionado = "cuda" if dispositivo == "auto" and torch.cuda.is_available() else dispositivo
    if seleccionado == "auto":
        seleccionado = "cpu"
    if seleccionado not in ("cpu", "cuda") or (seleccionado == "cuda" and not torch.cuda.is_available()):
        raise ValueError("Dispositivo no disponible. Usa cpu o auto.")

    modelo = maskrcnn_resnet50_fpn(
        weights=None,
        weights_backbone=None,
        num_classes=2,
        progress=False,
        image_mean=[0.485, 0.456, 0.406],
        image_std=[0.229, 0.224, 0.225],
    )

    estado = torch.load(pesos, map_location="cpu", weights_only=True)
    if isinstance(estado, dict) and "state_dict" in estado:
        estado = estado["state_dict"]
    elif isinstance(estado, dict) and "model" in estado:
        estado = estado["model"]
    estado = {k.removeprefix("module."): v for k, v in estado.items()}
    modelo.load_state_dict(estado, strict=True)
    modelo.eval()
    modelo.to(seleccionado)
    return modelo, seleccionado


def _predictor_maskrcnn(dispositivo: str, umbral: float):
    """Devuelve predecir(rgb uint8 (3,H,W)) -> (puntuaciones, máscaras bool (N,H,W))."""
    modelo, usado = cargar_modelo(dispositivo)

    def predecir(datos):
        alto, ancho = datos.shape[1:]
        tensor = torch.from_numpy(datos[:3].astype(np.float32) / 255.0).to(usado)
        with torch.inference_mode():
            prediccion = modelo([tensor])[0]
        puntuaciones = prediccion["scores"].detach().cpu().numpy()
        etiquetas = prediccion["labels"].detach().cpu().numpy()
        elegidos = np.flatnonzero((puntuaciones >= umbral) & (etiquetas == 1))
        mascaras = prediccion["masks"][elegidos, 0, :alto, :ancho].detach().cpu().numpy() >= 0.5
        return puntuaciones[elegidos], mascaras

    info = {"id": MODEL_ID, "sha256": LOCAL_MODEL_SHA256, "arquitectura": "Mask R-CNN ResNet50-FPN",
            "limitacion": LIMITACION_MASKRCNN}
    return predecir, usado, info


def _predictor_yolo(dispositivo: str, umbral: float):
    """YOLO-seg de Ultralytics con los pesos registrados por scripts/entrenar_yolo.py."""
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError("Falta ultralytics para el modelo YOLO: python -m pip install -r requirements-yolo.txt") from exc
    descripcion = modelos.describir("yolo")
    if descripcion["error"]:
        raise ValueError(descripcion["error"])
    pesos, manifest = descripcion["pesos"], descripcion["manifest"]
    if sha256_file(pesos) != manifest["sha256"]:
        raise ValueError(f"El SHA256 de {pesos.name} no coincide con su manifiesto.")
    if dispositivo == "cuda" and not torch.cuda.is_available():
        raise ValueError("Dispositivo no disponible. Usa cpu o auto.")
    usado = "cuda" if dispositivo in ("auto", "cuda") and torch.cuda.is_available() else "cpu"
    modelo = YOLO(str(pesos), task="segment")
    imgsz = int(manifest["imgsz"])

    def predecir(datos):
        alto, ancho = datos.shape[1:]
        # Ultralytics interpreta los arreglos numpy como BGR, igual que cv2 al entrenar.
        bgr = np.ascontiguousarray(datos[:3].transpose(1, 2, 0)[:, :, ::-1])
        r = modelo.predict(bgr, imgsz=imgsz, conf=umbral, retina_masks=True, verbose=False,
                           device=0 if usado == "cuda" else "cpu", max_det=300)[0]
        if r.masks is None or not len(r.boxes):
            return np.zeros(0, dtype=np.float32), np.zeros((0, alto, ancho), dtype=bool)
        # retina_masks devuelve las máscaras a la resolución original del mosaico.
        mascaras = r.masks.data.detach().cpu().numpy()[:, :alto, :ancho] > 0.5
        return r.boxes.conf.detach().cpu().numpy(), mascaras

    metricas = manifest.get("metricas_test") or {}
    limitacion = (f"Modelo YOLO entrenado en Chullo; en su prueba: precisión {metricas['precision']:.3f}, "
                  f"recuperación {metricas['recall']:.3f}, F1 {metricas['f1']:.3f}." if metricas else
                  "Modelo YOLO sin métricas de prueba registradas.")
    info = {"id": manifest["id"], "sha256": manifest["sha256"], "arquitectura": manifest.get("arquitectura", "YOLO-seg"),
            "limitacion": limitacion}
    return predecir, usado, info


MAX_MOSAICOS = 1024


def cargar_predictor(tipo: str | None, dispositivo: str, umbral: float):
    if modelos.resolver_tipo(tipo) == "yolo":
        return _predictor_yolo(dispositivo, umbral)
    return _predictor_maskrcnn(dispositivo, umbral)


def mascara_a_geometria(mascara_binaria, transform):
    """Convierte una máscara binaria a geometría Shapely preservando contornos."""
    piezas = [
        shape(item)
        for item, valor in shapes(
            mascara_binaria.astype("uint8"),
            mask=mascara_binaria.astype(bool),
            transform=transform,
        )
        if valor == 1
    ]
    if not piezas:
        from shapely.geometry import Polygon

        return Polygon()
    return unary_union(piezas)


def detectar_edificios(
    imagen_path: str | Path,
    salida_dir: str | Path,
    umbral: float | None = None,
    dispositivo: str = "auto",
    tamano_mosaico: int | None = None,
    solapamiento: int | None = None,
    area_minima_m2: float = 10.0,
    crs_analisis: str = "EPSG:32719",
    progreso=None,
    limites_path: str | Path | None = None,
    amarillo_m: float = 20,
    modelo: str | None = None,
) -> dict:
    """Ejecuta la detección de edificios sobre una imagen y guarda GeoJSON.

    Devuelve un manifiesto con conteos, parámetros y rutas de salida.
    """
    if not DEPENDENCIAS_DISPONIBLES:
        raise ImportError(
            "Detector CNN no disponible: " + _ERROR_IMPORT
        )

    from backend.raster import validar_imagen
    from backend.spatial import construir_zonas, evaluar_edificio
    from shapely.geometry import box, mapping

    tipo_modelo = modelos.resolver_tipo(modelo)
    if umbral is None:
        umbral = modelos.umbral_por_defecto(tipo_modelo)
    if not math.isfinite(umbral) or not 0 <= umbral <= 1:
        raise ValueError("El umbral debe estar entre 0 y 1.")
    # Cada modelo trae su mosaico: YOLO usa el tamaño de sus recortes de entrenamiento.
    mosaico_def, solape_def = modelos.parametros_mosaico(tipo_modelo)
    tamano_mosaico = tamano_mosaico or mosaico_def
    solapamiento = solape_def if solapamiento is None else solapamiento
    if tamano_mosaico < 32 or not 0 <= solapamiento < tamano_mosaico:
        raise ValueError("Mosaico o solapamiento inválidos.")
    if not math.isfinite(area_minima_m2) or area_minima_m2 < 0:
        raise ValueError("El área mínima debe ser positiva.")

    imagen_path = Path(imagen_path).resolve()
    salida_dir = Path(salida_dir).resolve()
    salida_dir.mkdir(parents=True, exist_ok=True)
    imagen_info = validar_imagen(imagen_path)
    limites_path = Path(limites_path or Path(__file__).resolve().parents[1] / "web/layers/limites-faja-cayma.geojson")
    zonas = construir_zonas(json.loads(limites_path.read_text(encoding="utf-8-sig")), amarillo_m, crs_analisis)
    iniciado = datetime.now(timezone.utc).isoformat()

    if progreso:
        progreso("Validando imagen GeoTIFF…", 0.02)

    with rasterio.open(imagen_path) as src:
        crs_nativo = src.crs
        transformador_metrico = Transformer.from_crs(crs_nativo, crs_analisis, always_xy=True)
        cobertura = _transformar_geometria(box(*src.bounds), transformador_metrico.transform)
        if not cobertura.intersects(zonas["exterior"]):
            raise ValueError("La imagen no cubre las franjas del sector Chullo.")

        filas = _inicios_mosaico(src.height, tamano_mosaico, solapamiento)
        columnas = _inicios_mosaico(src.width, tamano_mosaico, solapamiento)
        # Solo cuentan los mosaicos que tocan las franjas; el resto no se lee.
        ventanas = []
        limite_raster = rasterio.windows.Window(0, 0, src.width, src.height)
        for numero, (fila, col) in enumerate(((f, c) for f in filas for c in columnas), start=1):
            ventana = rasterio.windows.Window(col, fila, tamano_mosaico, tamano_mosaico).intersection(limite_raster)
            huella = box(*rasterio.windows.bounds(ventana, src.transform))
            if _transformar_geometria(huella, transformador_metrico.transform).intersects(zonas["exterior"]):
                ventanas.append((numero, ventana))
        total_mosaicos = len(ventanas)
        if total_mosaicos > MAX_MOSAICOS:
            raise ValueError(
                f"Las franjas requieren {total_mosaicos} mosaicos (máximo {MAX_MOSAICOS}). "
                "Recorta la imagen o usa mosaicos más grandes."
            )

        if progreso:
            progreso("Cargando modelo CNN…", 0.06)
        predecir, dispositivo_usado, modelo_info = cargar_predictor(tipo_modelo, dispositivo, umbral)

        candidatos = []
        mosaicos_procesados = 0

        for avance, (numero_mosaico, ventana) in enumerate(ventanas, start=1):
            datos = src.read([1, 2, 3], window=ventana)
            valido = (src.read_masks([1, 2, 3], window=ventana) > 0).all(axis=0)
            if src.count >= 4 and rasterio.enums.ColorInterp.alpha in src.colorinterp:
                alpha = src.colorinterp.index(rasterio.enums.ColorInterp.alpha) + 1
                valido &= src.read(alpha, window=ventana) > 0
            if not valido.any():
                if progreso:
                    progreso(
                        f"Mosaico {avance}/{total_mosaicos} sin datos.",
                        0.1 + 0.75 * avance / total_mosaicos,
                        mosaico=avance,
                        total=total_mosaicos,
                    )
                continue

            mosaicos_procesados += 1
            puntuaciones, mascaras = predecir(datos)

            for puntuacion, mascara in zip(puntuaciones, mascaras):
                binaria = mascara & valido
                if not binaria.any():
                    continue

                geometria = mascara_a_geometria(binaria, src.window_transform(ventana))
                if geometria.is_empty:
                    continue

                # Área en metros cuadrados
                geometria_metrica = _transformar_geometria(geometria, transformador_metrico.transform)
                area = geometria_metrica.area
                if area < area_minima_m2:
                    continue
                evaluacion = evaluar_edificio(geometria_metrica, zonas)
                if not evaluacion["dentro_banda"]:
                    continue

                candidatos.append({
                    "geometria": geometria,
                    "confianza": float(puntuacion),
                    "area_m2": float(area),
                    "mosaico": numero_mosaico,
                    "evaluacion": evaluacion,
                })

            if progreso:
                progreso(f"Mosaico {avance}/{total_mosaicos} · {len(candidatos)} candidatos en franjas", 0.1 + 0.75 * avance / total_mosaicos)

        if progreso:
            progreso("Vectorizando contornos…", 0.88)

    # Suprimir duplicados entre mosaicos solapados
    conservados = _suprimir_duplicados(candidatos)

    registros = []
    imagen_id = "img_" + sha256_file(imagen_path)[:16]
    ahora = datetime.now(timezone.utc).isoformat()
    source_path = imagen_path.with_suffix(".json")
    fuente_imagen = json.loads(source_path.read_text(encoding="utf-8")) if source_path.exists() else {}

    for item in conservados:
        identidad = hashlib.sha256(
            (imagen_id + str(item["geometria"].wkb)).encode()
        ).hexdigest()[:16]
        propiedades = {
            "building_id": "ai_" + identidad,
            "source_id": "cnn_building_inference",
            "observed_at": fuente_imagen.get("observed_at"),
            "inferred_at": ahora,
            "review_status": "Sin revisión manual · inferencia IA",
            "model_id": modelo_info["id"],
            "image_id": imagen_id,
            "confidence": item["confianza"],
            "area_m2": item["area_m2"],
            "tile_index": item["mosaico"],
            **item["evaluacion"],
        }
        a_wgs = Transformer.from_crs(crs_nativo, "EPSG:4326", always_xy=True)
        registros.append({"type": "Feature", "properties": propiedades,
                          "geometry": mapping(_transformar_geometria(item["geometria"], a_wgs.transform))})

    geojson_path = salida_dir / "buildings.geojson"
    geojson_path.write_text(json.dumps({"type": "FeatureCollection", "features": registros}, ensure_ascii=False), encoding="utf-8")

    manifiesto = {
        "schema_version": 1,
        "estado": "completado",
        "iniciado_en": iniciado,
        "completado_en": datetime.now(timezone.utc).isoformat(),
        "count": len(registros),
        "counts_by_class": {c: sum(f["properties"]["clase"] == c for f in registros) for c in ("rojo", "amarillo")},
        "modelo": modelo_info["id"],
        "model_sha256": modelo_info["sha256"],
        "zonas": {"geometria": "corredor_entre_limites", "amarillo_m": amarillo_m, "limites_sha256": sha256_file(limites_path)},
        "cobertura": imagen_info,
        "imagen_fuente": {k: fuente_imagen.get(k) for k in ("source", "service_url", "attribution", "observed_at", "acquired_at")},
        "mosaicos_procesados": mosaicos_procesados,
        "arquitectura": modelo_info["arquitectura"],
        "tamano_mosaico": tamano_mosaico,
        "solapamiento": solapamiento,
        "imagen": str(imagen_path),
        "dispositivo": dispositivo_usado,
        "umbral": umbral,
        "area_minima_m2": area_minima_m2,
        "crs_analisis": crs_analisis,
        "outputs": {"buildings": str(geojson_path)},
        "limitaciones": [
            "Detecciones automáticas sin revisión humana.",
            "La confianza no es una probabilidad calibrada de peligro.",
            "Pueden existir omisiones y falsos positivos.",
            modelo_info["limitacion"],
            "Solo se analiza la cobertura del GeoTIFF; no se evalúan franjas fuera de ella.",
        ],
    }

    manifiesto_path = salida_dir / "manifest.json"
    manifiesto_path.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if progreso:
        progreso(
            f"Detección finalizada: {len(registros)} edificios detectados.",
            1.0,
            count=len(registros),
        )

    return manifiesto


def _inicios_mosaico(longitud, tamano, solapamiento):
    inicios = list(range(0, max(1, longitud - tamano + 1), tamano - solapamiento))
    if not inicios or inicios[-1] + tamano < longitud:
        inicios.append(max(0, longitud - tamano))
    return sorted(set(inicios))


def _transformar_geometria(geom, funcion_transformar):
    from shapely import transform as transformar_shapely

    return transformar_shapely(geom, funcion_transformar, interleaved=False)


def _suprimir_duplicados(candidatos, umbral_iou: float = 0.35, umbral_contenimiento: float = 0.7):
    """Supresión no máxima geométrica entre mosaicos solapados."""
    ordenados = sorted(
        candidatos,
        key=lambda c: (-c["confianza"], -c["area_m2"]),
    )
    conservados = []
    for candidato in ordenados:
        geom = candidato["geometria"]
        duplicado = False
        for previo in conservados:
            otro = previo["geometria"]
            if not geom.intersects(otro):
                continue
            interseccion = geom.intersection(otro).area
            union = geom.area + otro.area - interseccion
            iou = interseccion / max(union, 1e-20)
            contencion = interseccion / max(min(geom.area, otro.area), 1e-20)
            if iou >= umbral_iou or contencion >= umbral_contenimiento:
                duplicado = True
                break
        if not duplicado:
            conservados.append(candidato)
    return conservados


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detección de edificios CNN")
    parser.add_argument("--imagen", required=True, help="Ruta al GeoTIFF RGB")
    parser.add_argument("--salida", default="outputs/detection", help="Directorio de salida")
    parser.add_argument("--umbral", type=float, default=None, help="Umbral de confianza (por defecto, el del modelo)")
    parser.add_argument("--dispositivo", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--modelo", default=None, choices=list(modelos.TIPOS))
    args = parser.parse_args()

    manifiesto = detectar_edificios(
        args.imagen,
        args.salida,
        umbral=args.umbral,
        dispositivo=args.dispositivo,
        modelo=args.modelo,
    )
    print(json.dumps(manifiesto, indent=2, ensure_ascii=False))
