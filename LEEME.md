# Chullo Unificado · Mapa y detección de edificaciones en la torrentera Chullo

Proyecto local que unifica dos prototipos en una sola aplicación:

1. **Visor documental** (de chullo-local): mapa con imagen satelital, hitos ANA de Cayma y Yanahuara, límites de faja documental y línea del cauce obtenida uniendo ambos límites.
2. **Detección de edificios con CNN** (de gsti-teo, ahora obligatoria): identificación de edificaciones sobre imagen satelital y clasificación por distancia al cauce usando valores reales de ANA.

Todo se ejecuta en tu computadora, sin cuenta en la nube.

---

## ¿Qué hace este programa?

Muestra un mapa del sector Chullo (Arequipa) con:

- **Puntos ANA**: hitos documentales de la faja marginal en Cayma (48 puntos) y Yanahuara (12 puntos, en revisión).
- **Límites de faja**: las dos líneas exteriores documentadas de Cayma (margen derecha e izquierda) con 210 vértices del documento ANA (RD 1610-2018).
- **Línea del cauce**: obtenida uniendo los dos límites documentales punto a punto (punto medio entre margen derecha e izquierda en cada vértice).
- **Franjas de proximidad con valores reales de ANA**:
  - Rojo: 0 a 4 m (faja documental, 4 m por margen según Tabla 02 / RD 1610-2018)
  - Amarillo: 4 a 24 m (franja de seguridad adicional configurable)
  - Verde: más de 24 m
- **Edificios detectados**: polígonos de edificaciones identificados por CNN (Mask R-CNN), coloreados según su distancia al cauce.
- **Imagen satelital**: capa base por defecto para identificar edificios (techos como figuras de 4 lados).

Cada edificio detectado, al hacer clic, muestra su distancia al cauce, el color del semáforo y la puntuación del detector.

**Importante:** la proximidad no determina peligro ni permiso para construir. Verde no significa seguro.

---

## Cómo usar (despliegue local)

### Requisitos
- Python 3 instalado en tu equipo.
- Para la detección CNN: torch, torchvision, rasterio, geopandas, shapely, pyproj, requests.

### Pasos

1. Abre la carpeta `chullo-unificado`.
2. Doble clic en `iniciar.bat`.
   - O ejecuta: `python servidor.py --abrir`
3. El navegador se abre en: `http://127.0.0.1:4173/`
4. Para detener el servidor: presiona `Ctrl+C` en la ventana negra.

Si el puerto 4173 está ocupado:
```
python servidor.py --puerto 4174 --abrir
```

---

## Capas del mapa (qué puedes activar/desactivar)

1. **Puntos ANA Cayma** (verde oscuro) — hitos de señalización de faja marginal.
2. **Puntos ANA Yanahuara** (naranja) — hitos en revisión por discrepancias entre fuentes.
3. **Límites de faja Cayma** — dos líneas exteriores documentadas (margen derecha e izquierda).
4. **Línea del cauce** — unión de los dos límites documentales (punto medio entre márgenes).
5. **Franjas de proximidad (ANA)** — rojo/faja documental, amarillo/seguridad, verde/fuera.
6. **Edificios detectados (CNN)** — polígonos de edificios identificados por CNN, coloreados por proximidad.
7. **Vista satelital** — imagen satelital como base para identificar edificios.

---

## Detección de edificios con CNN (obligatoria)

La detección usa Mask R-CNN ResNet50-FPN con pesos preentrenados para huellas de edificios.

Para ejecutarla desde el visor: pulsa el botón **"Detectar edificios (CNN)"**. El servidor ejecuta `backend/detector.py` sobre la imagen del sector y devuelve los contornos como GeoJSON.

También desde línea de comandos:

```powershell
python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida outputs/detection --umbral 0.5
```

Esto genera un GeoJSON con los contornos de edificios detectados y un manifiesto de ejecución.

---

## Estructura del proyecto

| Carpeta/archivo | Contenido |
|---|---|
| `servidor.py` | Servidor HTTP local y API de detección CNN |
| `iniciar.bat` | Lanzador con doble clic |
| `web/index.html` | Página principal del mapa |
| `web/simple.css` | Estilos visuales |
| `web/simple.js` | Lógica del mapa Leaflet, línea del cauce, franjas ANA |
| `web/data.js` | Puntos ANA y límites de faja (GeoJSON embebido) |
| `web/bands.js` | Franjas de proximidad con valores reales de ANA |
| `web/detection.js` | Detección CNN obligatoria de edificios |
| `web/vendor/` | Leaflet (mapa) |
| `web/docs/` | Documentos ANA de referencia |
| `web/layers/` | Archivos GeoJSON de capas |
| `backend/detector.py` | Ejecución del modelo CNN Mask R-CNN |
| `backend/spatial.py` | Línea del cauce, franjas ANA, distancias edificio-cauce |
| `config/proximity_rules.json` | Reglas del semáforo (basadas en ANA) |
| `data/processed/chullo/` | Capas vectoriales del sector |
| `scripts/run_detection.py` | CLI para ejecutar detección de edificios |
| `scripts/generate_bands.py` | CLI para generar GeoJSON de franjas |
| `outputs/detection/` | Resultados guardados de detección |

---

## Advertencias

- Las franjas de proximidad usan los valores reales de los documentos ANA (4 m por margen), no criterios ilustrativos inventados.
- No es una faja marginal legal ni un estudio de inundaciones.
- El detector CNN puede producir omisiones y falsos positivos; requiere revisión humana.
- Para decisiones sobre construcción se necesitan análisis hidráulicos, delimitaciones oficiales y permisos aplicables.
- La imagen satelital y el mapa base OpenStreetMap requieren conexión a internet.

---

## Referencias documentales

- Expediente ANA Cayma (RD 1610-2018, rectificación 22/03/2019) — Tabla 02 de vértices de faja, planos pp. 40-44, hitos pp. 71-73.
- Resolución ANA Yanahuara–Sachaca (28/12/2017) — delimitación por coordenadas (en revisión).
- Informes INGEMMET ZS-Cayma, ZS-Yanahuara, ZS-Chullo — contexto de peligro, no delimitación legal.
- Modelo CNN: Mask R-CNN ResNet50-FPN (giswqs/geoai, building_footprints_usa).