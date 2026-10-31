# Cómo funciona el GeoTIFF en el detector CNN (basado en gsti-teo)

## Problema actual en chullo-unificado

Las imágenes `prueba.png`, `prueba2.png`, `aqp.png` son **PNG sin georreferenciación**. El detector CNN (`scripts/run_detection.py` + `backend/detector.py`) requiere un **GeoTIFF con coordenadas geográficas** (CRS + transform affine). Sin eso, rasterio abre el archivo pero no sabe dónde está en el mapa, y el detector falla con `Invalid projection` o `Dataset has no geotransform`.

Por eso el servidor devuelve HTTP 200 con `count: 0` (maneja el error gracefulmente), pero nunca detecta edificios.

## Cómo lo hace gsti-teo (proyecto 2)

El proyecto `gsti-teo` (`C:\Users\paulo_xxg0vy8\Documents\Codex\2026-10-21\necesito-que-en-base-a-esto\outputs\gsti-teo`) tiene un pipeline completo que sí funciona con imágenes reales de satélite:

### 1. Georreferenciación de la imagen (obligatorio)

Script: `scripts/georeference_capture.py`

Toma una imagen sin coordenadas + un CSV de puntos de control (columna, fila, latitud, longitud) y produce un **GeoTIFF con CRS EPSG:32719** (UTM 19S, metros) y resolución de 0.5 m/píxel.

Flujo:
- Lee puntos de control CSV (role `fit` para ajustar, `check` para validar)
- Ajuste afín por mínimos cuadrados entre píxeles y coordenadas UTM
- Exporta GeoTIFF con `rasterio` (driver GTiff, crs=EPSG:32719, transform affine de origen superior-izquierda)
- Guarda residuales y manifest JSON

### 2. Validación del GeoTIFF antes de inferir

Script: `scripts/inspect_raster.py` / módulo `src/inference/raster.py`

Valida que el GeoTIFF tenga:
- Driver `GTiff`
- CRS no nulo (`src.crs`)
- 3 bandas RGB uint8
- Transform affine válido y no singular
- Resolución entre 0.05 y 2.0 m/píxel
- Bounds en WGS84 válidos

### 3. Ejecución del detector CNN

Script: `scripts/run_detection.py`

Parámetros clave:
```
--image data/imagery/chullo/chullo_rgb.tif   # GeoTIFF con georreferenciación
--salida outputs/detection
--umbral 0.5
--dispositivo cpu
--tamano-mosaico 512
--solapamiento 128
--area-minima 10.0
```

Flujo interno (`src/inference/pipeline.py`):
1. Abre el GeoTIFF con `rasterio.open()` — obtiene `src.crs` y `src.transform`
2. Crea `pyproj.Transformer.from_crs(src.crs, "EPSG:32719")` para reproyectar a metros
3. Itera mosaicos de 512×512 px con solapamiento 128 px
4. Lee cada mosaico con `src.read((1,2,3), window=window)` y normaliza a [0,1]
5. Ejecuta `maskrcnn_resnet50_fpn` con pesos preentrenados (o ajustados en `models/`)
6. Convierte máscaras binarias a polígonos con `rasterio.features.shapes()` usando el `transform` affine del mosaico
7. Reproyecta polígonos al CRS métrico (EPSG:32719) para calcular áreas en m²
8. Filtra por confianza ≥ 0.5 y área ≥ 10 m²
9. Suprime duplicados con NMS geométrico (IoU ≥ 0.35)
10. Guarda `buildings.geojson` (WGS84), `manifest.json` y `preview.png`

### 4. Por qué gsti-teo detecta edificios y chullo-unificado no

| Aspecto | chullo-unificado | gsti-teo |
|---|---|---|
| Imagen de entrada | `chullo_rgb.tif` sin georreferenciar (o .png) | GeoTIFF con CRS EPSG:32719 y transform affine |
| Modelo | `building_footprints_usa.pth` (EE. UU.) | `chullo_local_v1` (datos locales de Chullo) o `spacenet2_khartoum_v1` |
| Detecciones | 0 edificios | Detecta edificios reales en Arequipa |

## Cómo probar con tus imágenes

Necesitas una **imagen GeoTIFF con georreferenciación**, no un .png. Las opciones son:

### Opción A: Usar las imágenes de gsti-teo
El proyecto `gsti-teo` ya tiene datos preparados. Revisa su carpeta `data/imagery/chullo/` para ver si hay un GeoTIFF listo. Si existe, cópialo a `chullo-unificado/data/imagery/chullo/chullo_rgb.tif` y ejecuta:
```
python servidor.py --abrir
```
Luego presiona "Ejecutar detección CNN sobre imagen del sector".

### Opción B: Georreferenciar tus propias imágenes
Necesitas:
1. Una imagen satelital del sector (prueba.png, prueba2.png o aqp.png)
2. Puntos de control conocidos (esquinas de la imagen con sus coordenadas UTM/WGS84)
3. Ejecutar `gsti-teo/scripts/georeference_capture.py` para producir el GeoTIFF

### Opción C: Entrenar un nuevo modelo
Si quieres detectar edificios en Arequipa con mejor precisión, usa los modelos ajustados de gsti-teo:
- `gsti-teo/models/chullo_local_v1/` — entrenado con datos locales de Chullo (F1: 24.9%)
- `gsti-teo/models/spacenet2_khartoum_v1/` — entrenado con SpaceNet 2 (F1: 40.2%)

Copia los pesos `.pth` a `chullo-unificado/models/` y actualiza `backend/detector.py` para cargar el checkpoint correcto en lugar de `building_footprints_usa.pth`.

## Sobre tu pregunta: ¿es similar a YOLO?

Sí, conceptualmente es similar a YOLO (detección de objetos), pero es **Mask R-CNN ResNet50-FPN**:
- Como YOLO: detecta objetos en una imagen
- Diferencia clave: además de cajas delimitadoras, genera **máscaras de instancia** (polígonos precisos del contorno de cada edificio, no solo rectángulos)
- Se entrena con anotaciones de polígonos, no solo cajas

## Resumen: qué hacer ahora

1. **El commit ya está hecho** (`a6c5a22`) con la franja roja ajustada a los límites I y D.
2. **Para que el CNN detecte algo**: necesitas una imagen GeoTIFF georeferenciada en `data/imagery/chullo/chullo_rgb.tif`.
3. **Si no tienes GeoTIFF**: usa el proyecto `gsti-teo` que ya tiene el pipeline completo funcionando, o georreferencia tus imágenes PNG con `gsti-teo/scripts/georeference_capture.py`.
