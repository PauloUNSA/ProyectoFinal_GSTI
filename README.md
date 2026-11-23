# ProyectoFinal_GSTI

Proyecto Chullo Unificado: visor de franjas ANA y detección de cubiertas con CNN.

Visor de los límites documentales ANA y detección de posibles cubiertas con YOLO26-Chullo. Mask R-CNN se conserva como alternativa experimental explícita.

## Despliegue

**Demo pública en Sites:** https://chullo-gsti-publico-paulo.paulohidalgoch.chatgpt.site

**GitHub Pages (disponible cuando finalice el workflow):** https://paulounsa.github.io/ProyectoFinal_GSTI/

| Opción | Qué permite probar | Requisitos |
| --- | --- | --- |
| GitHub Pages | Mapa, corredor documental, proximidad exploratoria de 20 m, fichas y detecciones guardadas de YOLO26-Chullo | Navegador; sin instalar Python |
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

Esta preparación no crea un servicio de pago ni configura una cuenta de Render. La demo pública utiliza los resultados guardados; la CNN en un servidor remoto se configura por separado. La inferencia es síncrona y puede tardar varios minutos: comprueba los límites de tiempo del proxy/proveedor. Para uso concurrente se debe pasar a una cola de trabajos y almacenamiento persistente.

Documentación oficial: [GitHub Pages y Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Docker en Render](https://render.com/docs/docker).

## Clonar y ejecutar el modelo actual

Los pesos se distribuyen mediante Git LFS. Antes de ejecutar la detección:

```powershell
git lfs install
git clone https://github.com/PauloUNSA/ProyectoFinal_GSTI.git
cd ProyectoFinal_GSTI
git lfs pull
python -m venv .venv-ml
.venv-ml\Scripts\python -m pip install -r requirements-detection.txt
.venv-ml\Scripts\python servidor.py --abrir
```

## Franjas corregidas

- **Rojo:** un único corredor que ocupa todo el espacio entre las líneas azul y morada. Su ancho sigue los límites existentes; no es un buffer fijo de 4 m desde el eje.
- **Amarillo:** anillo exterior de 20 m por defecto, configurable entre 0 y 500 m. Se mide desde el borde del corredor rojo, con esquinas redondeadas para no exceder la distancia elegida. No es un retiro legal.
- **Referencia central:** se conserva internamente para las distancias, pero no se dibuja en el visor para evitar que se confunda con una carretera.

Los 4 m documentales se conservan como referencia del documento; no desplazan ni sustituyen las coordenadas de los límites. Estas capas no son una validación legal ni un estudio de peligro.

El visor y la CNN comparten la geometría calculada en `backend/spatial.py`, en EPSG:32719. La intersección de cualquier parte del contorno con rojo tiene prioridad roja; si solo toca la zona exterior se clasifica amarillo. Se conservan los contornos completos. No se muestran candidatos fuera de ambas zonas.

## Documentos y distancias

El visor incluye [la justificación y sus fuentes](web/normativa.html). Revisión documental al **22/11/2026**:

- **Cauce, ribera y faja marginal son diferentes.** Ley 29338 art. 74 y DS 001-2010-AG arts. 108, 111 y 113–115. La AAA fija la faja; estar fuera de ella no acredita seguridad o permiso para construir.
- **Chullo en Cayma:** RD 1610-2018 y rectificación RD 289-2019 del 22/03/2019. El expediente fija 4 m de faja por margen. La RJ 332-2016-ANA art. 12 define mínimos por pendiente, material y protección; para >2 % y conglomerado contempla 4 m desde el límite superior de ribera. No son 4 m desde el eje ni una regla basada solo en profundidad. Los arts. 13–14 regulan mayor ancho y modificaciones.
- **Puntos trazables:** 210 vértices (105 por línea) representan los límites exteriores digitalizados; 48 hitos de Cayma son referencias de señalización. El visor muestra ambos y permite descargar los vértices. La capa nueva copia exactamente las coordenadas existentes; no inventa una actualización de campo. La antigüedad no prueba caducidad: confirmar cartografía aplicable con AAA Caplina Ocoña/ALA Chili.
- **Rojo:** corredor entre límites exteriores. Incluye cauce y fajas; no equivale solo al cauce ni a las dos fajas aisladas. El eje discontinuo es una referencia geométrica, no un levantamiento de la corriente.
- **Amarillo:** distancia exploratoria configurable desde ese corredor. Los 20 m no provienen de un retiro universal de RNE/PDM. Las esquinas se redondean; se corrigieron las puntas de los ingletes que podían superar el ancho configurado.
- **RNE pertinente:** TH.050 arts. 3 y 8 (riberas y laderas); A.010 arts. 4 y 8 (parámetros y retiros desde linderos). No establecen la equivalencia profundidad de 10 m → margen de 0,5 m.
- **PDM:** OM 961 y OM 975, reglamento Título III cap. 1. El horizonte 2025 no deroga automáticamente el plan (DS 012-2022-VIVIENDA art. 40.2). El nuevo PDM 2026–2045 está en consulta pública hasta el 06/12/2026 según IMPLA. La MPA reconoce restricciones judiciales del plan anterior: verificar aplicación por sector. No se asignó zonificación a cada detección sin una capa predial oficial.

Fuentes directas: [expediente ANA](https://repositorio.ana.gob.pe/bitstream/20.500.12543/4034/1/ANA0002438.pdf), [RJ 332 anexo](https://faolex.fao.org/docs/pdf/per167827anx.pdf), [TH.050](https://cdn.www.gob.pe/uploads/document/file/2365177/12%20TH.050%20HABILITACIONES%20EN%20RIBERAS%20Y%20LADERAS.pdf?v=1636045242), [reglamento PDM](https://www.muniarequipa.gob.pe/descargas/transparencia/pdm/reglamento/4_1_titulo%20III_1_zonificacion%20y%20compatibilidades.pdf), [consulta del nuevo PDM](https://www.gob.pe/institucion/impla/noticias/1471044-exhibicion-y-consulta-publica-del-pdm-2026-2045).

## Uso

1. Abre `iniciar.bat`, o ejecuta `python servidor.py --abrir` desde esta carpeta.
2. Visita http://127.0.0.1:4173/.
3. Pulsa **Ejecutar detección CNN sobre imagen del sector**. El servidor selecciona YOLO26 y su umbral recomendado; la duración depende del equipo y del modelo.
4. Selecciona un contorno para consultar distancias y puntuación.
5. Si cambias el ancho amarillo y recalculas, vuelve a ejecutar la CNN. El visor limpia el resultado anterior para evitar mostrar una clasificación con otro ancho.

Los resultados completos guardados se cargan al abrir el visor. Un fallo devuelve un error real y conserva los archivos de la última detección válida.

## Imagen y modelo incluidos

- `data/imagery/chullo/chullo_rgb.tif`: GeoTIFF RGB real, EPSG:32719, 1177 × 8942 píxeles, que cubre el corredor ANA con contexto alrededor.
- `data/imagery/chullo/chullo_rgb.json`: procedencia, extensiones devueltas por ArcGIS, parámetros de las tres capturas y hashes. Fuente: [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer). Se conservan los créditos del proveedor. La fecha de descarga no se presenta como fecha de captura.
- `data/imagery/chullo/captura_original_sin_crs.png`: respaldo de la imagen que antes estaba renombrada como `.tif`, sin coordenadas.
- `models/yolo26_chullo/`: modelo activo YOLO26s-seg, manifiesto y pesos SHA256 verificados. Su entrenamiento y evaluación se documentan en `docs/ENTRENAMIENTO_YOLO.md`.
- `models/chullo_local_v1/`: piloto Mask R-CNN conservado para comparación. Para usarlo: `$env:CHULLO_MODELO="maskrcnn"`. Se verifica su SHA256 antes de cargarlo.

El GeoTIFF del proyecto original cubría otro tramo, al sur del corredor ANA, por lo que se descartó como entrada de esta detección. No se asignaron coordenadas inventadas al PNG ni se desplazaron límites para hacerlo coincidir.

Para repetir la captura local del corredor: `python scripts/prepare_imagery.py` (requiere conexión al servicio Esri).

## Ejecución y salidas

Instala las dependencias si faltan: `python -m pip install -r requirements-detection.txt`.

```powershell
python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida web/outputs/detection --modelo yolo --amarillo 20
python scripts/generate_bands.py --amarillo 20
```

La API publica `web/outputs/detection/buildings.geojson` y `manifest.json`; se sirven bajo `/outputs/detection/`. El manifiesto registra conteos por color, modelo, imagen, cobertura y parámetros.

La verificación local del **22/11/2026** con **YOLO26-Chullo**, umbral 0.05 y anillo redondeado de 20 m produjo **437 contornos candidatos: 114 rojos y 323 amarillos**, en 115 mosaicos y 67,34 s de CPU en este equipo. Los contornos son cerrados y válidos; falta validar su correspondencia con techos reales. La versión guardada del 15/11/2026 tenía 442 (113 rojos y 329 amarillos) con la geometría anterior. El cambio de geometría y las diferencias del entorno de inferencia impiden atribuir toda variación de conteo al detector. El Mask R-CNN piloto había dado 405 (118 rojos y 287 amarillos) el 31/10/2026. Ninguna cifra certifica la precisión de los contornos; ver la evaluación en [docs/ENTRENAMIENTO_YOLO.md](docs/ENTRENAMIENTO_YOLO.md).

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

El detector sigue siendo **experimental**. El F1 de instancias ≈0.249 corresponde al piloto Mask R-CNN, no a YOLO26. El manifiesto de YOLO publica métricas de instancias y de área distintas, medidas contra huellas automáticas de Overture sin revisión humana. No deben interpretarse como exactitud verificada ni compararse entre sí como si midieran lo mismo. Los contornos pueden omitir techos, unirlos o incluir otras superficies; un polígono cerrado y válido no demuestra que corresponda a un edificio real.

## Modelo final: YOLO26-Chullo

El detector del visor es **YOLO26-Chullo** (`models/yolo26_chullo`): un YOLO26s-seg de Ultralytics entrenado a la vez con techos de [RAMP](https://source.coop/ramp/ramp), dibujados por personas en otras ciudades, y con huellas de Overture limpias de la torrentera y de 8 distritos de Arequipa.

- **Frente al Mask R-CNN piloto:** cubre bastante más área construida (F1 de área 0.53 de media frente a 0.31; 0.58 frente a 0.28 en la torrentera) y recorre el corredor en unos 12 s en CPU en vez de 62 s.
- **Limitaciones:** contando techo por techo todavía omite muchos, y todas las métricas se midieron contra huellas automáticas, no contra una referencia revisada.
- **Licencia:** por usar RAMP (CC BY-NC 4.0), el modelo es de uso no comercial.
- **Volver al modelo anterior:** `CHULLO_MODELO=maskrcnn`.

Para mejorarlo, anota techos en QGIS sobre `data/training/yolo_chullo/celdas.geojson`, empezando por las 11 celdas test (`prioridad = 1`), y reentrena con `scripts/entrenar_yolo.py --sumar-ramp`. Guía completa y resultados: [docs/ENTRENAMIENTO_YOLO.md](docs/ENTRENAMIENTO_YOLO.md). Figura por tramos: `python scripts/figura_detecciones.py`.

## Verificación del despliegue

Se aprobaron 28 pruebas del backend y una prueba de navegador de la demo bajo un subdirectorio. Se construyó el Dockerfile en Linux y se ejecutó la CNN real sobre un recorte del GeoTIFF: devolvió 13 contornos. Se comprobó también la API HTTP del contenedor y la carga de los 405 resultados guardados. El contenedor incluye `libexpat1`, requerido por Rasterio en la imagen base slim.

## Verificación del 22 de noviembre de 2026

- 51 pruebas Python aprobadas, incluidas regresiones de distancia en esquinas, copia exacta de los 210 vértices y verificación SHA256 de los dos modelos.
- Inferencia real sobre el GeoTIFF completo, con YOLO26 y CPU; resultados guardados y manifiesto actualizados. La comprobación geométrica no detectó anillos abiertos, geometrías inválidas ni clases incoherentes (tolerancia de ida y vuelta de coordenadas de 1e-6 m).
- El Dockerfile ahora incluye YOLO, su manifiesto y dependencias, además del piloto Mask R-CNN. No se reconstruyó la imagen Docker en esta revisión porque el motor Linux de Docker no estaba iniciado.
- El artículo conserva los resultados históricos del piloto y añade el marco normativo y una nota de versión; no se reemplazan sus métricas por las del nuevo modelo sin una revisión específica.

En el caso agrícola de la Fig. 2b del artículo, el contorno histórico de 2361,25 m² del piloto ya no recibe candidatos YOLO en la misma región e imagen. Es una inspección puntual, no una evaluación formal. [Comparación visual](docs/comparacion-chacra-20261122.png) y [registro de la verificación](docs/verificacion-20261122.json).
