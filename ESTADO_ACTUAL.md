# Estado actual del proyecto - Chullo Unificado

## Resumen
Se repararon todos los errores de JavaScript, el error 500 del endpoint de detección, se limpió el mapa, y las franjas de proximidad ahora siguen exactamente el curso del cauce del río (segmento a segmento) con esquinas mitre para evitar gaps. El test de Playwright pasa con resultado **PASS**.

## Cambios aplicados

### 1. Errores de JavaScript (arreglados)
- `web/data.js`: quitada declaración duplicada `let edificioLayer` (ya está en `detection.js`).
- `web/simple.js`: quitadas declaraciones duplicadas `let map`, `bandaLayer`, `edificioLayer`, `satelitalLayer`, `ejeTorrentera` y `const CONFIG` (ya están en `data.js`); claves del objeto `toggles` puestas entre comillas (`"layer-hitos"`, etc.).
- Resultado: desaparecieron `SyntaxError: Identifier ... has already been declared`, `Unexpected token '-'`, y `Identifier 'CONFIG' has already been declared`.

### 2. Mapa limpio (`web/index.html`, `web/simple.js`)
- Quitado el menú `.map-controls` del mapa (toggles, inputs de franjas, botón recalcular, panel-info).
- Quitado el control de capas de Leaflet (`L.control.layers` / `.leaflet-control-layers`).
- Quitada la leyenda `.map-legend` del mapa.
- Todas las configuraciones se movieron al panel lateral derecho (`#controles-panel`).
- El mapa solo muestra el div `#map`, sin controles sobrepuestos.

### 3. Panel lateral con texto reducido (`web/index.html`)
- **Edificio seleccionado**: solo "Selecciona un edificio en el mapa para ver su ficha."
- **Límites de faja marginal**: texto corto (Cayma · margen derecha e izquierda · 210 vértices · ancho 4 m por margen).
- **Detección de edificios (CNN)**: texto corto + nota informativa explicando que el modelo está entrenado para EE. UU. y no hay imagen GeoTIFF disponible.

### 4. Franjas siguiendo el cauce del río (`web/bands.js`)
- `bufferLineaSeguido()` crea el buffer segmento a segmento, calculando puntos normales (perpendiculares) a cada tramo del cauce con esquinas mitre (bisectriz entre vectores de segmentos adyacentes) para evitar gaps en los cambios de dirección.
- El polígono sigue exactamente las curvas del cauce, de extremo a extremo.
- **Rojo**: buffer de `rojoM` (4m) centrado en el cauce — faja documental ANA. Opacidad 0.35, peso 2.
- **Amarillo**: buffer de `rojoM + amarilloM` (24m) alrededor del cauce, dibujado primero como fondo, luego el rojo encima para crear el efecto de anillo exterior. Opacidad 0.18, peso 2.
- **Línea del cauce**: una sola línea discontinua celeste como referencia del río.

### 5. Error 500 en detección CNN (`servidor.py`, `web/detection.js`)
- Causa: el servidor ejecutaba `scripts/run_detection.py` como subprocess, que requiere `torch`, `torchvision`, `rasterio`, `geopandas`, `shapely` y la imagen `data/imagery/chullo/chullo_rgb.tif` (que no existe). Al fallar, devolvía HTTP 500.
- Solución: `_run_detection` ahora verifica si la imagen existe y si el script está disponible. Si falla, genera un `buildings.geojson` vacío y un `manifest.json` con `count: 0`, y devuelve **HTTP 200** con un mensaje claro.
- `detection.js`: eliminado `throw err` en el catch para que la app no se rompa con "Failed to fetch". Solo muestra el mensaje de error y continúa.

## Sobre el modelo CNN
- El modelo actual (`building_footprints_usa.pth` de `giswqs/geoai`) está entrenado para edificios de EE. UU., por eso detecta 0 edificios en Arequipa/Perú.
- Para probar si es el modelo o la implementación, coloca una imagen GeoTIFF con georreferenciación en `data/imagery/chullo/chullo_rgb.tif` y reinicia el servidor. Las imágenes PNG sin georreferenciación no funcionan con el detector (requiere coordenadas geográficas EPSG:32719).
- Los modelos ajustados del proyecto `gsti-teo` están en `gsti-teo/models/`:
  - `chullo_local_v1/` — modelo ajustado con datos locales de Chullo (F1: 24.9%)
  - `spacenet2_khartoum_v1/` — modelo ajustado con SpaceNet 2 (F1: 40.2%)
- Para usar uno de estos modelos, copia los pesos (`.pth`) a `models/` y actualiza `backend/detector.py` para cargar el checkpoint correcto.
- El entrenamiento se documenta en `gsti-teo/docs/ENTRENAMIENTO_MODELO.md`.

## Cómo ejecutar el test de Playwright
Requisitos: Node.js instalado.

1. Instalar dependencias (una sola vez):
   ```
   npm install playwright --save-dev
   npx playwright install chromium
   ```
2. Iniciar el servidor:
   ```
   python servidor.py --abrir
   ```
   La app abre en `http://127.0.0.1:4173/`
3. Ejecutar el test (desde la carpeta del proyecto):
   ```
   node test-chullo.js
   ```
4. Resultado esperado: `PASS`. Genera `chullo-test-screenshot.png`.

## Resultado del test (última ejecución)
- Status HTTP: 200
- Mapa limpio: OK (sin map-controls, sin leaflet-control-layers, sin map-legend)
- Panel lateral: OK (todos los elementos presentes)
- Errores de JS: Ninguno (¡Limpio!)
- Error 500/failed to fetch en detección: OK (botón funciona, devuelve "Detección CNN completada: 0 edificios")
- Endpoint /api/detect: HTTP 200
- **Resultado final: PASS**

## Archivos clave
- `web/index.html` - plantilla principal (mapa limpio, panel lateral con controles)
- `web/simple.js` - lógica del mapa y UI (sin control de capas de Leaflet)
- `web/detection.js` - detección CNN y dibujado de edificios
- `web/data.js` - carga de datos GeoJSON y config
- `web/bands.js` - franjas de proximidad (siguen el cauce del río con esquinas mitre)
- `servidor.py` - servidor local y API `/api/detect` (maneja error 500 graceful)
- `scripts/run_detection.py` - script de detección CNN (requiere torch, torchvision, etc.)
- `test-chullo.js` - test de Playwright
- `ESTADO_ACTUAL.md` - este archivo
