"""Detección de edificios con CNN (Mask R-CNN ResNet50-FPN).

Ejecuta la inferencia sobre una imagen GeoTIFF del sector Chullo y genera
GeoJSON con los contornos de edificios detectados, listos para visualizar
en el visor unificado.

Requisitos opcionales (instalar solo si se usa el detector):
  torch, torchvision, rasterio, geopandas, shapely, pyproj, requests

Si no están instalados, la detección no está disponible y el visor sigue
funcionando con datos estáticos (puntos ANA, límites, franjas).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import numpy as np
    import rasterio
    import torch
    import torchvision
    from pyproj import Transformer
    from shapely.geometry import Polygon, shape
    from shapely.ops import unary_union
    from rasterio.features import shapes

    DEPENDENCIAS_DISPONIBLES = True
except ImportError as exc:  # pragma: no cover - depende del entorno
    DEPENDENCIAS_DISPONIBLES = False
    _ERROR_IMPORT = str(exc)


MODEL_URL = (
    "https://huggingface.co/giswqs/geoai/resolve/"
    "43b6aa04156d7d9d2b90fe321096f15f03353cd2/building_footprints_usa.pth"
)
MODEL_SHA256 = "3aea5d0da7803be31ff4e2e1e5ac747f15cab2a13d6bb1a9319b6a6ba8bc7bca"
MODEL_BYTES = 176225905
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "building_footprints_usa.pth"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asegurar_modelo(progreso=None) -> Path:
    """Descarga y verifica el checkpoint preentrenado si no existe localmente."""
    path = MODEL_PATH
    if path.exists():
        if path.stat().st_size == MODEL_BYTES and sha256_file(path) == MODEL_SHA256:
            return path
        path.unlink(missing_ok=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(".download")

    if progreso:
        progreso("Descargando pesos preentrenados del modelo CNN (176 MB)…", 0.02)

    import requests

    with requests.get(MODEL_URL, stream=True, timeout=(30, 300)) as respuesta:
        respuesta.raise_for_status()
        with temporal.open("wb") as salida:
            for fragmento in respuesta.iter_content(1024 * 1024):
                salida.write(fragmento)

    if temporal.stat().st_size != MODEL_BYTES or sha256_file(temporal) != MODEL_SHA256:
        temporal.unlink(missing_ok=True)
        raise ValueError("Los pesos descargados no coinciden con el SHA256 esperado.")

    temporal.replace(path)
    return path


def cargar_modelo(dispositivo: str = "auto"):
    """Carga Mask R-CNN con los pesos verificados."""
    if not DEPENDENCIAS_DISPONIBLES:
        raise ImportError(
            "Faltan dependencias para el detector CNN: " + _ERROR_IMPORT
        )

    from torchvision.models.detection import maskrcnn_resnet50_fpn

    pesos = asegurar_modelo()
    torch.set_num_threads(min(4, (torch.cuda.device_count() or 1) if dispositivo == "cuda" else 4))

    seleccionado = "cuda" if dispositivo == "auto" and torch.cuda.is_available() else dispositivo
    if seleccionado == "auto":
        seleccionado = "cpu"

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
    return unary_union(pieces)


def detectar_edificios(
    imagen_path: str | Path,
    salida_dir: str | Path,
    umbral: float = 0.5,
    dispositivo: str = "auto",
    tamano_mosaico: int = 512,
    solapamiento: int = 128,
    area_minima_m2: float = 10.0,
    crs_analisis: str = "EPSG:32719",
    progreso=None,
) -> dict:
    """Ejecuta la detección de edificios sobre una imagen y guarda GeoJSON.

    Devuelve un manifiesto con conteos, parámetros y rutas de salida.
    """
    if not DEPENDENCIAS_DISPONIBLES:
        raise ImportError(
            "Detector CNN no disponible: " + _ERROR_IMPORT
        )

    import torch

    imagen_path = Path(imagen_path).resolve()
    salida_dir = Path(salida_dir).resolve()
    salida_dir.mkdir(parents=True, exist_ok=True)

    if progreso:
        progreso("Validando imagen GeoTIFF…", 0.02)

    with rasterio.open(imagen_path) as src:
        crs_nativo = src.crs
        transformador_metrico = Transformer.from_crs(crs_nativo, crs_analisis, always_xy=True)

        filas = _inicios_mosaico(src.height, tamano_mosaico, solapamiento)
        columnas = _inicios_mosaico(src.width, tamano_mosaico, solapamiento)
        total_mosaicos = len(filas) * len(columnas)

        if total_mosaicos > 256:
            raise ValueError(
                f"La imagen requiere {total_mosaicos} mosaicos (máximo 256). "
                "Recórtala antes de analizar."
            )

        if progreso:
            progreso("Cargando modelo CNN…", 0.06)

        modelo, dispositivo_usado = cargar_modelo(dispositivo)

        candidatos = []
        numero_mosaico = 0

        for fila in filas:
            for col in columnas:
                numero_mosaico += 1
                ventana = rasterio.windows.Window(col, fila, tamano_mosaico, tamano_mosaico)
                ventana = ventana.intersection(
                    rasterio.windows.Window(0, 0, src.width, src.height)
                )

                datos = src.read(window=ventana)
                valido = src.read_masks(window=ventana) > 0
                if not valido.any():
                    if progreso:
                        progreso(
                            f"Mosaico {numero_mosaico}/{total_mosaicos} sin datos.",
                            0.1 + 0.75 * numero_mosaico / total_mosaicos,
                            mosaico=numero_mosaico,
                            total=total_mosaicos,
                        )
                    continue

                # Normalizar a tensor RGB [0,1]
                tensor = torch.from_numpy(datos[:3].astype(np.float32) / 255.0).to(dispositivo_usado)

                with torch.inference_mode():
                    prediccion = modelo([tensor])[0]

                puntuaciones = prediccion["scores"].detach().cpu().numpy()
                etiquetas = prediccion["labels"].detach().cpu().numpy()
                elegidos = np.flatnonzero((puntuaciones >= umbral) & (etiquetas == 1))

                mascaras = prediccion["masks"][elegidos, 0, : ventana.height, : ventana.width].detach().cpu().numpy()

                for puntuacion, mascara in zip(puntuaciones[elegidos], mascaras):
                    binaria = (mascara >= 0.5) & valido
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

                    candidatos.append({
                        "geometria": geometria,
                        "confianza": float(puntuacion),
                        "area_m2": float(area),
                        "mosaico": numero_mosaico,
                    })

                del prediccion, tensor

        if progreso:
            progreso("Vectorizando contornos…", 0.88)

    # Suprimir duplicados entre mosaicos solapados
    conservados = _suprimir_duplicados(candidatos)

    # Generar GeoDataFrame
    import geopandas as gpd

    registros = []
    imagen_id = "img_" + hashlib.sha256(imagen_path.read_bytes()[: 1024 * 1024]).hexdigest()[:16]
    ahora = datetime.now(timezone.utc).isoformat()

    for item in conservados:
        identidad = hashlib.sha256(
            (imagen_id + str(item["geometria"].wkb)).encode()
        ).hexdigest()[:16]
        registros.append({
            "building_id": "ai_" + identidad,
            "source_id": "cnn_building_inference",
            "observed_at": ahora,
            "review_status": "Sin revisión manual · inferencia IA",
            "model_id": "giswqs/geoai/building_footprints_usa",
            "image_id": imagen_id,
            "confidence": item["confianza"],
            "area_m2": item["area_m2"],
            "tile_index": item["mosaico"],
            "geometry": item["geometria"],
        })

    gdf = gpd.GeoDataFrame(
        registros,
        geometry="geometry",
        crs=crs_nativo,
    ).to_crs("EPSG:4326")

    geojson_path = salida_dir / "buildings.geojson"
    gdf.to_file(geojson_path, driver="GeoJSON")

    manifiesto = {
        "schema_version": 1,
        "estado": "completado",
        "iniciado_en": ahora,
        "completado_en": datetime.now(timezone.utc).isoformat(),
        "count": len(gdf),
        "modelo": "giswqs/geoai/building_footprints_usa",
        "arquitectura": "Mask R-CNN ResNet50-FPN",
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
        ],
    }

    manifiesto_path = salida_dir / "manifest.json"
    manifiesto_path.write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if progreso:
        progreso(
            f"Detección finalizada: {len(gdf)} edificios detectados.",
            1.0,
            count=len(gdf),
        )

    return manifiesto


def _inicios_mosaico(longitud, tamano, solapamiento):
    inicios = list(range(0, max(1, longitud - tamano + 1), tamano - solapamiento))
    if not inicios or inicios[-1] + tamano < longitud:
        inicios.append(max(0, longitud - tamano))
    return sorted(set(inicios))


def _transformar_geometria(geom, funcion_transformar):
    from shapely.ops import transform as transformar_shapely

    return transformar_shapely(funcion_transformar, geom)


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
    parser.add_argument("--umbral", type=float, default=0.5, help="Umbral de confianza")
    parser.add_argument("--dispositivo", default="auto", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()

    manifiesto = detectar_edificios(
        args.imagen,
        args.salida,
        umbral=args.umbral,
        dispositivo=args.dispositivo,
    )
    print(json.dumps(manifiesto, indent=2, ensure_ascii=False))
