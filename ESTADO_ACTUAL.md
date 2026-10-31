# Estado actual del proyecto - Chullo Unificado

## Resumen
Se repararon los errores de JavaScript que impedían cargar la aplicación. La página ahora carga sin `SyntaxError` y todos los elementos del DOM están presentes.

## Archivos modificados
- `web/index.html`: agregado `<base href="/">` y corregida ruta de descarga de hitos ANA.
- `web/simple.js`: quitadas declaraciones duplicadas de `let` (`map`, `bandaLayer`, `edificioLayer`, `satelitalLayer`, `ejeTorrentera`) y `const CONFIG` (ya declarados en `data.js`); claves del objeto `toggles` puestas entre comillas.
- `web/data.js`: quitada declaración duplicada de `let edificioLayer`.
- `test-chullo.js`: test de smoke con Playwright (nuevo).

## Cómo ejecutar el test de Playwright
Requisitos: Node.js instalado.

1. Instalar dependencias una sola vez:
   ```
   npm install playwright --save-dev
   npx playwright install chromium
   ```
2. Iniciar el servidor local:
   ```
   python servidor.py --abrir
   ```
   La app se abre en `http://127.0.0.1:4173/`
3. Ejecutar el test (en otra terminal, desde la carpeta del proyecto):
   ```
   node test-chullo.js
   ```
4. Resultado esperado: `PASS`. Genera `chullo-test-screenshot.png`.

## Estado de los errores
- `Identifier '...' has already been declared`: CORREGIDO (variables `let` duplicadas entre `data.js`, `simple.js`, `detection.js`).
- `Unexpected token '-'`: CORREGIDO (claves sin comillas en objeto `toggles`).
- `Identifier 'CONFIG' has already been declared`: CORREGIDO (duplicado entre `data.js` y `simple.js`).
- 404 en `vendor/leaflet.css`, `vendor/leaflet.js`: CORREGIDO con `<base href="/">`.
- 404 en descarga hitos ANA: CORREGIDO (ruta `layers/hitos-ana.geojson`).

## Errores conocidos (pendientes para el próximo chat)
1. Peticiones a `tile.openstreetmap.org` fallan (404) si no hay internet. No es un bug del código, son tiles externos.
2. Al presionar "Ejecutar detección sobre imagen del sector" puede fallar por ruta de imagen inexistente o endpoint `/api/detect` sin respuesta válida. Revisar `servidor.py` y `scripts/run_detection.py`.
