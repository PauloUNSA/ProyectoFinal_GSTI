# Chullo Unificado · Mapa y detección de edificaciones en la torrentera Chullo

Proyecto local que une dos prototipos en una sola aplicación:

1. **Visor documental** (de chullo-local): mapa OpenStreetMap con los hitos ANA de Cayma y Yanahuara y los límites exteriores de faja marginal de la torrentera Chullo.
2. **Detección de edificios con CNN** (de gsti-teo): identificación de edificaciones sobre imagen satelital y clasificación por proximidad al cauce (semáforo rojo/amarillo/verde).

Todo se ejecuta en tu computadora, sin cuenta en la nube.

---

## ¿Qué hace este programa?

Muestra un mapa del sector Chullo (Arequipa) con:

- **Puntos ANA**: hitos documentales de la faja marginal en Cayma (48 puntos) y Yanahuara (12 puntos, en revisión).
- **Límites de faja**: las dos líneas exteriores documentadas de Cayma (margen derecha e izquierda) con 210 vértices.
- **Franjas de proximidad**: zonas roja (0-25 m), amarilla (25-50 m) y verde (>50 m) trazadas desde el eje de la torrentera.
- **Edificios detectados**: polígonos de edificaciones identificados por una red neuronal CNN (Mask R-CNN), coloreados según su distancia al cauce.
- **Imagen satelital**: capa opcional de vista satelital sobre el sector.

Cada edificio detectado, al hacer clic, muestra su distancia al cauce, el color del semáforo y la puntuación del detector.

**Importante:** la proximidad no determina peligro ni permiso para construir. Verde no significa seguro.

---

## Cómo usar (despliegue local)

### Requisitos
- Python 3 instalado en tu equipo.
- Para la detección CNN opcional: PyTorch y torchvision (se instalan por separado si se quiere usar el detector).

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

## Estructura del proyecto

| Carpeta/archivo | Contenido |
|---|---|
| `servidor.py` | Servidor HTTP local y API de detección |
| `iniciar.bat` | Lanzador con doble clic |
| `web/index.html` | Página principal del mapa |
| `web/simple.css` | Estilos visuales |
| `web/simple.js` | Lógica del mapa Leaflet |
| `web/data.js` | Puntos ANA y límites de faja (GeoJSON embebido) |
| `web/bands.js` | Cálculo y dibujo de franjas de proximidad |
| `web/detection.js` | Interfaz de detección CNN de edificios |
| `web/vendor/` | Leaflet (mapa) |
| `web/docs/` | Documentos ANA de referencia |
| `web/layers/` | Archivos GeoJSON de capas |
| `backend/detector.py` | Ejecución del modelo CNN Mask R-CNN |
| `backend/spatial.py` | Análisis de distancias edificio-cauce |
| `config/proximity_rules.json` | Reglas del semáforo (rojo/amarillo/verde) |
| `data/processed/chullo/` | Capas vectoriales del sector |
| `scripts/run_detection.py` | CLI para ejecutar detección de edificios |
| `outputs/detection/` | Resultados guardados de detección |

---

## Capas del mapa (qué puedes activar/desactivar)

1. **Puntos ANA Cayma** (verde oscuro) — hitos de señalización de faja marginal.
2. **Puntos ANA Yanahuara** (naranja) — hitos en revisión por discrepancias entre fuentes.
3. **Límites de faja Cayma** — dos líneas exteriores documentadas (margen derecha e izquierda).
4. **Franjas de proximidad** — semáforo rojo/amarillo/verde desde el eje de la torrentera.
5. **Edificios detectados** — polígonos de edificios identificados por CNN, coloreados por proximidad.
6. **Imagen satelital** — vista satelital del sector (requiere internet).

---

## Detección de edificios con CNN (opcional)

La detección usa Mask R-CNN ResNet50-FPN con pesos preentrenados para huellas de edificios.

Para ejecutarla:

```powershell
python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida outputs/detection
```

Esto genera un GeoJSON con los contornos de edificios detectados y un manifiesto de ejecución. El mapa puede cargar ese archivo para mostrar los edificios sobre las franjas de proximidad.

Si no instalas PyTorch ni descargas los pesos del modelo, el visor funciona normalmente con los datos estáticos (puntos ANA, límites, franjas). La detección CNN es una funcionalidad adicional.

---

## Advertencias

- Las franjas de proximidad son criterios ilustrativos del proyecto, no umbrales oficiales de peligro.
- No es una faja marginal legal ni un estudio de inundaciones.
- El detector CNN puede producir omisiones y falsos positivos; requiere revisión humana.
- Para decisiones sobre construcción se necesitan análisis hidráulicos, delimitaciones oficiales y permisos aplicables.
- El mapa base OpenStreetMap y la imagen satelital requien conexión a internet.

---

## Referencias documentales

- Expediente ANA Cayma (RD 1610-2018, rectificación 22/03/2019) — Tabla 02 de vértices de faja, planos pp. 40-44, hitos pp. 71-73.
- Resolución ANA Yanahuara–Sachaca (28/12/2017) — delimitación por coordenadas (en revisión).
- Informes INGEMMET ZS-Cayma, ZS-Yanahuara, ZS-Chullo — contexto de peligro, no delimitación legal.
- Modelo CNN: Mask R-CNN ResNet50-FPN (giswqs/geoai, building_footprints_usa).