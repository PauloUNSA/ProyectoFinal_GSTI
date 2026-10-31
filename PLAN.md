# Plan de fusion - Chullo Unificado (1ra version)

Objetivo: unificar en un solo proyecto local dos prototipos:
1. chullo-local: visor OpenStreetMap con hitos ANA (Cayma y Yanahuara) y límites de faja marginal de la torrentera Chullo.
2. gsti-teo: detector de edificios con CNN (Mask R-CNN) sobre imagen satelital, con franjas de proximidad (semáforo rojo/amarillo/verde) calculadas desde el eje de la torrentera.

Todo desplegable localmente, como el primero, sin depender de la nube.

---

## Paso 1 - Estructura del proyecto unificado

Crear carpeta `chullo-unificado/` con los siguientes directorios:

```
/chullo-unificado/
├── LEEME.md                 # Guía para el usuario
├── PLAN.md                  # Este plan
├── iniciar.bat              # Lanzador local (doble clic)
├── servidor.py              # Servidor HTTP local + API de detección
├── web/                     # Frontend (HTML/CSS/JS)
│   ├── index.html           # Página principal del mapa
│   ├── simple.css           # Estilos
│   ├── simple.js            # Lógica principal del mapa Leaflet
│   ├── data.js              # Puntos ANA Cayma + Yanahuara + límites de faja
│   ├── bands.js             # Cálculo y dibujo de franjas de proximidad
│   ├── detection.js         # Interfaz de detección CNN de edificios
│   ├── vendor/              # Leaflet JS/CSS (copiado de chullo-local)
│   ├── docs/                # Documentos ANA (PDF/TXT copiados)
│   └── layers/              # GeoJSON: hitos, límites, edificios detectados, bandas
├── backend/                 # Lógica Python (CNN + análisis espacial)
│   ├── detector.py          # Ejecuta Mask R-CNN sobre imagen (de gsti-teo)
│   └── spatial.py           # Franjas de proximidad y distancias edificio-cauce
├── config/                  # Configuración
│   ├── proximity_rules.json # Reglas del semáforo (de gsti-teo)
│   └── study_areas.json     # Área de estudio Chullo (CRS EPSG:32719)
├── data/
│   └── processed/chullo/    # Capas vectoriales (ríos, edificios, área)
├── models/                  # Pesos del modelo CNN (descarga opcional)
├── scripts/
│   ├── run_detection.py     # CLI: ejecutar detección de edificios
│   └── generate_bands.py    # CLI: generar GeoJSON de franjas de proximidad
└── outputs/
    └── detection/           # Resultados de detección (GeoJSON, manifiesto)
```

---

## Paso 2 - Datos desde chullo-local (lo que se toma del primero)

### 2.1 Puntos ANA (hitos documentales)
- Archivo: `web/layers/hitos-ana.geojson`
- 48 hitos de Cayma + 12 de Yanahuara (en revisión)
- Cada punto tiene: código (ej. R-CH-01), margen (Derecha/Izquierda), sector, coordenadas UTM/WGS84, vínculo al documento fuente.
- Estos puntos marcan dónde ANA prevé colocar hitos de señalización de la faja marginal.

### 2.2 Límites exteriores de faja (Cayma)
- Archivo: `web/layers/limites-faja-cayma.geojson`
- Dos LineString (margen Derecha e Izquierda) con 105 vértices cada uno (210 en total).
- Fuente: Tabla 02 del expediente ANA Cayma (RD 1610-2018), planos pp. 40-44.
- No es un polígono oficial de faja, son las dos líneas exteriores documentadas.

### 2.3 Documentos ANA
- Carpeta: `web/docs/` (ANA-Cayma.pdf, ANA-estudio-2017.txt, ANA-resolucion-2017.txt, ZS-*.pdf)
- Se mantienen disponibles para consulta desde el visor.

---

## Paso 3 - Funcionalidad desde gsti-teo (lo que se toma del segundo)

### 3.1 Mapa con imagen satelital
- El visor usará OpenStreetMap como base.
- Se agregará una capa opcional de imagen satelital (overlay) sobre el sector, similar al "Mapa del sector" de gsti-teo.
- El usuario puede alternar entre mapa callejero y vista satelital.

### 3.2 Franjas de proximidad (unir puntos para trazar las fajas)
- Se calcula un eje de referencia de la torrentera a partir de los límites documentales de Cayma (las dos líneas de faja).
- Desde ese eje se generan buffers (áreas de influencia) a distancias configurables:
  - Zona roja: 0 a 25 m (proximidad inmediata)
  - Zona amarilla: 25 a 50 m (proximidad intermedia)
  - Zona verde: más de 50 m (mayor distancia)
- Estas zonas se dibujan como polígonos semitransparentes sobre el mapa.

### 3.3 Detección de edificios con CNN
- Modelo: Mask R-CNN ResNet50-FPN (de gsti-teo).
- Entrada: imagen GeoTIFF o satelital del sector Chullo.
- Salida: contornos (polígonos) de edificios detectados, con puntuación de confianza.
- Los edificios detectados se clasifican por su distancia mínima al eje de la torrentera:
  - Rojo: dentro de 25 m → edificio en zona de mayor proximidad
  - Amarillo: entre 25 y 50 m → edificio en franja adicional de proximidad
  - Verde: más de 50 m → fuera de las franjas configuradas

---

## Paso 4 - Integración: un solo visor web

El mapa unificado mostrará, en capas separadas activables/desactivables:

1. **Puntos ANA** (Cayma en verde oscuro, Yanahuara en naranja, en revisión)
2. **Límites de faja** (dos líneas exteriores de Cayma, margen derecha e izquierda)
3. **Franjas de proximidad** (roja, amarilla, verde) calculadas desde el eje
4. **Edificios detectados** (polígonos coloreados por proximidad: rojo/amarillo/verde)
5. **Imagen satelital** (overlay opcional)

Cada edificio detectado, al hacer clic, muestra:
- Identificador
- Distancia mínima al cauce
- Color del semáforo y motivo
- Puntuación del detector CNN
- Nota: la proximidad no determina peligro ni permiso para construir.

---

## Paso 5 - Servidor local y API de detección

`servidor.py` hace dos cosas:
1. Sirve los archivos estáticos del visor (como chullo-local, puerto 4173 por defecto).
2. Expone un endpoint simple `/api/detect` que ejecuta `backend/detector.py` para correr el CNN sobre una imagen del sector y devuelve GeoJSON de edificios detectados.

El detector CNN es opcional: si no se tienen las dependencias de PyTorch ni los pesos del modelo, el visor sigue funcionando mostrando los datos estáticos (puntos ANA, límites, franjas) y puede cargar resultados de detección previos desde `outputs/detection/`.

---

## Paso 6 - Scripts de línea de comandos

- `scripts/run_detection.py`: ejecuta la detección CNN sobre una imagen y guarda resultados en `outputs/detection/`.
- `scripts/generate_bands.py`: genera el GeoJSON de franjas de proximidad a partir de los límites de faja y los umbrales configurados.

---

## Paso 7 - Despliegue local

1. Extraer o clonar la carpeta `chullo-unificado`.
2. Ejecutar `iniciar.bat` (doble clic) o `python servidor.py --abrir`.
3. El navegador se abre en `http://127.0.0.1:4173/`.
4. Para detener: Ctrl+C en la ventana del servidor.

No se requiere cuenta de nube, API key, ni conexión a internet para los datos locales. El mapa base OpenStreetMap y la imagen satelital requieren internet para cargar teselas.

---

## Paso 8 - Mejoras sugeridas (versiones futuras)

- Incorporar polígonos oficiales de faja marginal (no solo líneas exteriores).
- Agregar hitos y límites de Yanahuara una vez resueltas las discrepancias de coordenadas.
- Integrar datos de sisgrid (INGEMMET) sobre peligros de lahares e inundaciones en la torrentera Chullo.
- Permitir cargar GeoTIFF propio del usuario para detección en otro sector.
- Exportar resultados a CSV/GeoJSON/ZIP con informe de proximidad por edificio.
- Versión con Streamlit (como gsti-teo) para análisis más avanzado si se necesita.

---

## Limitaciones importantes (leer antes de usar)

- Las franjas de proximidad son criterios de demostración, no una faja marginal legal ni un mapa de peligro.
- Verde no significa seguro ni edificable.
- El detector CNN puede tener omisiones y falsos positivos; requiere revisión humana.
- Las distancias se calculan sobre geometrías disponibles, no son mediciones de campo certificadas.
- Para decisiones de construcción se requieren estudios hidráulicos, delimitaciones oficiales y permisos aplicables.