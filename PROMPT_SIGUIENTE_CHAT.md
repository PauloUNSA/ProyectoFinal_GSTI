# Prompt para el siguiente chat

## Contexto
Tengo un proyecto llamado "Chullo Unificado": un visor web local (HTML/JS + servidor Python `servidor.py`) que muestra mapas con Leaflet, puntos ANA, límites de faja, franjas de proximidad y detección de edificios por CNN.

Ya se arreglaron los errores de JavaScript que impedían cargar la app (redeclaraciones de `let` y `const` entre `data.js`, `simple.js` y `detection.js`, claves de objeto sin comillas, y rutas de assets). El test de Playwright en `test-chullo.js` pasa: HTTP 200, todos los elementos del DOM presentes, cero errores de JS.

Documentación del estado: `ESTADO_ACTUAL.md`.

## Tareas que necesito que hagas (en este orden)

### 1. Limpiar la UI de la web
El `index.html` y `simple.js` tienen demasiados textos largos y controles grandes mezclados en el mismo mapa. Necesito:
- Mover los textos explicativos largos (ej. "La detección identifica edificaciones sobre imagen satelital..." y los paneles de "Límites de faja marginal" y "Detección de edificios") fuera de la vista principal, o ponerlos en secciones colapsables / pestañas / modales, para que el mapa no quede saturado.
- Reducir o reorganizar los controles grandes (botones, inputs de banda roja/amarilla, toggles de capas) para que no ocupen tanto espacio visual sobre el mapa.
- Mantener funcionales todos los botones y toggles.

No elimines funcionalidad, solo reorganiza la presentación visual.

### 2. Arreglar el error al presionar "Ejecutar detección sobre imagen del sector"
Al hacer clic en ese botón (o en "Detectar edificios" del header), se llama a `window.EJECUTAR_DETECCION(imagen, umbral)` en `simple.js`, que invoca `/api/detect?imagen=data/imagery/chullo/chullo_rgb.tif&salida=outputs/detection&umbral=0.5`.

El problema puede ser:
- La imagen `data/imagery/chullo/chullo_rgb.tif` no existe o no se sirve correctamente.
- El endpoint `/api/detect` en `servidor.py` no responde con `estado: completado` o devuelve error.
- `detection.js` intenta fetch a `${salida}/buildings.geojson` y falla con 404.

Revisa:
1. Que exista `data/imagery/chullo/chullo_rgb.tif` o ajusta la ruta por defecto en `simple.js` (`configurarUI` y `btn-detected`).
2. Que `scripts/run_detection.py` exista y funcione, o que el servidor maneje graceful su ausencia.
3. Que la respuesta de `/api/detect` incluya `salida` correcta y que `buildings.geojson` esté disponible en esa ruta.
4. Que `detection.js` maneje el caso en que no hay geojson sin romper la app.

## Cómo verificar tu trabajo
Desde la carpeta del proyecto:
1. `python servidor.py --abrir` (abre http://127.0.0.1:4173/)
2. `node test-chullo.js` (debe salir PASS)
3. Abrir manualmente la consola del navegador y presionar "Ejecutar detección sobre imagen del sector": no debe haber `SyntaxError`, ni 404 de `buildings.geojson`, ni errores no controlados.

## Archivos clave
- `web/index.html` - plantilla principal
- `web/simple.js` - lógica del mapa y UI
- `web/detection.js` - detección CNN y dibujado de edificios
- `web/data.js` - carga de datos GeoJSON y config
- `web/bands.js` - franjas de proximidad
- `servidor.py` - servidor local y API `/api/detect`
- `scripts/run_detection.py` - script de detección (puede no existir)
- `test-chullo.js` - test de Playwright (no modificar)
- `ESTADO_ACTUAL.md` - resumen de cambios previos

## Reglas
- No rompas lo que ya funciona (el test `test-chullo.js` debe seguir pasando).
- Si instalas dependencias de Node para el test, no las subas al proyecto (solo `node_modules` local).
- Documenta brevemente qué cambiaste y por qué.
