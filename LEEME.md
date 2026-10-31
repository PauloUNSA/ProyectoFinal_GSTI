# Chullo Unificado

Visor local de los límites documentales ANA y detección automática de cubiertas con Mask R-CNN.

## Franjas corregidas

- **Rojo:** un único corredor que ocupa todo el espacio entre las líneas azul y morada. Su ancho sigue los límites existentes; no es un buffer fijo de 4 m desde el eje.
- **Amarillo:** anillo exterior de 20 m por defecto, configurable entre 0 y 500 m. Se mide desde el borde del corredor rojo.
- **Referencia central:** línea discontinua abierta entre ambas márgenes; nunca une artificialmente el final con el inicio.

Los 4 m documentales se conservan como referencia del documento; no desplazan ni sustituyen las coordenadas de los límites. Estas capas no son una validación legal ni un estudio de peligro.

El visor y la CNN comparten la geometría calculada en `backend/spatial.py`, en EPSG:32719. La intersección de cualquier parte del contorno con rojo tiene prioridad roja; si solo toca la zona exterior se clasifica amarillo. Se conservan los contornos completos. No se muestran candidatos fuera de ambas zonas.

## Uso

1. Abre `iniciar.bat`, o ejecuta `python servidor.py --abrir` desde esta carpeta.
2. Visita http://127.0.0.1:4173/.
3. Pulsa **Ejecutar detección CNN sobre imagen del sector**. Una ejecución completa sobre CPU tardó aproximadamente 4 minutos y medio en este equipo.
4. Selecciona un contorno para consultar distancias y puntuación.
5. Si cambias el ancho amarillo y recalculas, vuelve a ejecutar la CNN. El visor limpia el resultado anterior para evitar mostrar una clasificación con otro ancho.

Los resultados completos guardados se cargan al abrir el visor. Un fallo devuelve un error real y conserva los archivos de la última detección válida.

## Imagen y modelo incluidos

- `data/imagery/chullo/chullo_rgb.tif`: GeoTIFF RGB real, EPSG:32719, 1177 × 8942 píxeles, que cubre el corredor ANA con contexto alrededor.
- `data/imagery/chullo/chullo_rgb.json`: procedencia, extensiones devueltas por ArcGIS, parámetros de las tres capturas y hashes. Fuente: [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer). Se conservan los créditos del proveedor. La fecha de descarga no se presenta como fecha de captura.
- `data/imagery/chullo/captura_original_sin_crs.png`: respaldo de la imagen que antes estaba renombrada como `.tif`, sin coordenadas.
- `models/chullo_local_v1/`: pesos y documentación del modelo piloto ya existente en el proyecto original `gsti-teo`. Se verifica el SHA256 antes de cargarlo. No se entrenó un modelo nuevo en esta corrección.

El GeoTIFF del proyecto original cubría otro tramo, al sur del corredor ANA, por lo que se descartó como entrada de esta detección. No se asignaron coordenadas inventadas al PNG ni se desplazaron límites para hacerlo coincidir.

Para repetir la captura local del corredor: `python scripts/prepare_imagery.py` (requiere conexión al servicio Esri).

## Ejecución y salidas

Instala las dependencias si faltan: `python -m pip install -r requirements-detection.txt`.

```powershell
python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida web/outputs/detection --umbral 0.5 --amarillo 20
python scripts/generate_bands.py --amarillo 20
```

La API publica `web/outputs/detection/buildings.geojson` y `manifest.json`; se sirven bajo `/outputs/detection/`. El manifiesto registra conteos por color, modelo, imagen, cobertura y parámetros.

La ejecución real de verificación del 31/10/2026 produjo **405 contornos candidatos: 118 rojos y 287 amarillos**, procesando 49 mosaicos con datos relevantes. Esto verifica que la inferencia funciona; no certifica la precisión de los contornos.

## Pruebas

```powershell
python -m pytest -p no:xonsh tests -q
npm ci
$env:CHULLO_URL = 'http://127.0.0.1:4173'
npm test
```

Si la instalación local de pytest carga plugins ajenos incompatibles con la consola, usa `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'` antes de ejecutar pytest.

Se verifican las franjas, el último vértice de ambas márgenes, anillos interiores, prioridad por intersección del contorno, máscaras RGB bidimensionales, resultado vacío real y preservación de resultados ante errores. La prueba del navegador comprueba controles, geometría y presentación honesta de errores. La inferencia real se comprobó también a través de la API con un recorte del GeoTIFF.

## Alcance de la CNN

El modelo local sigue siendo **experimental**: su evaluación previa en dos recortes del proyecto original obtuvo F1 de instancias ≈0.249, con omisiones, falsos positivos y máscaras que unen techos. Esa cifra no mide su precisión en la nueva imagen Esri. Detecta cubiertas visibles; no confirma viviendas individuales ni su uso residencial. Es necesario revisar los contornos en el mapa.
