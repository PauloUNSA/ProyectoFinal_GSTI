# ProyectoFinal_GSTI

Proyecto Chullo Unificado: visor de franjas ANA y detección de cubiertas con CNN.

Visor local de los límites documentales ANA y detección automática de cubiertas con Mask R-CNN.

## Despliegue

**Demo pública:** https://paulounsa.github.io/ProyectoFinal_GSTI/

| Opción | Qué permite probar | Requisitos |
| --- | --- | --- |
| GitHub Pages | Mapa, franjas de 20 m, fichas y 405 detecciones guardadas | Navegador; sin instalar Python |
| Docker / servidor Python | Recalcular franjas y ejecutar nuevas inferencias | Docker, o Python y pesos; memoria suficiente |

La demo estática no ejecuta PyTorch. Las inferencias anteriores se identifican como resultados guardados. GitHub Pages sirve archivos estáticos; la CNN requiere el servidor completo.

### Publicar tu propia demo en GitHub Pages

1. Haz un fork de este repositorio y activa **Actions**.
2. En **Settings → Pages → Build and deployment**, selecciona **GitHub Actions**.
3. Ejecuta **Actions → Publicar visor en GitHub Pages → Run workflow** sobre `main` (o realiza un push a `main`).
4. Espera a que termine el despliegue. El trabajo muestra la URL en el entorno `github-pages`.

El archivo `.github/workflows/pages.yml` genera y publica `dist/` automáticamente. Esta demo no descarga el modelo LFS: usa los contornos guardados y genera las franjas mediante Shapely/PyProj. Funciona bajo el subdirectorio de un repositorio de Pages.

Para generar y probar los mismos archivos en tu equipo:

```powershell
python -m pip install numpy shapely pyproj
python scripts/build_static.py
python -m http.server 8081 --directory dist
```

Abre http://localhost:8081/. `dist/` también puede subirse como sitio estático a otro proveedor.

### Ejecutar la aplicación completa con Docker

Instala Docker Desktop (contenedores Linux) o Docker Engine. Después de clonar el repositorio:

```powershell
docker build -t chullo-gsti .
docker run --rm -p 8080:8080 -e CHULLO_ENABLE_DETECTION=1 chullo-gsti
```

Abre http://localhost:8080/. Esta variante permite ejecutar nuevas inferencias desde el botón del visor. La imagen incluye PyTorch CPU y el checkpoint verificado. Si el proveedor solo entrega el puntero Git LFS, `scripts/ensure_weights.py` obtiene la revisión pública fijada y comprueba su SHA256.

Para un servidor remoto: enlaza el contenedor a su puerto público y configura `HOST=0.0.0.0` y `PORT` (por defecto 8080). El contenedor usa esos valores. Reserva inicialmente unos **4 GB de RAM** para probar la CNN y ajusta según el consumo real. No se ha medido un mínimo garantizado en todos los proveedores.

El contenedor desactiva nuevas inferencias por defecto (`CHULLO_ENABLE_DETECTION=0`). Actívalas explícitamente con `1` cuando el servicio tenga recursos disponibles. Se admite una inferencia simultánea por proceso. Los resultados se guardan en el contenedor y se pierden si se reemplaza; conserva los GeoJSON o configura almacenamiento persistente si necesitas historial.

### Desplegar el contenedor en Render

1. Crea una cuenta en Render y conecta tu repositorio GitHub.
2. Selecciona **New → Web Service** y este repositorio.
3. Elige **Docker** como lenguaje y `Dockerfile` como ruta. No necesitas un comando de inicio adicional.
4. Define `CHULLO_ENABLE_DETECTION=1` si vas a permitir inferencias; escoge recursos suficientes para la CNN.
5. Publica el servicio y abre la URL HTTPS que Render asigne.

Esta preparación no crea un servicio de pago ni configura una cuenta de Render. La URL pública verificada del proyecto es la demo en GitHub Pages. La inferencia es síncrona y puede tardar varios minutos: comprueba los límites de tiempo del proxy/proveedor. Para uso concurrente se debe pasar a una cola de trabajos y almacenamiento persistente.

Documentación oficial: [GitHub Pages y Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Docker en Render](https://render.com/docs/docker).

## Clonar con el modelo CNN

Los pesos se distribuyen mediante Git LFS. Antes de ejecutar la detección:

```powershell
git lfs install
git clone https://github.com/PauloUNSA/ProyectoFinal_GSTI.git
cd ProyectoFinal_GSTI
git lfs pull
python -m pip install -r requirements-detection.txt
python servidor.py --abrir
```

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
