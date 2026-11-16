# Entrenar el detector de techos con YOLO-seg

El modelo Mask R-CNN actual (`models/chullo_local_v1`) acierta poco (F1 ≈ 0.25). Sus causas principales:

- se entrenó con solo 3 recortes y unos 150 techos;
- las anotaciones no tuvieron revisión humana;
- se entrenó con una imagen distinta (Google Earth/Airbus) de la que analiza (Esri).

Este flujo entrena un modelo **YOLO-seg** (Ultralytics) sobre la **misma imagen Esri** que usa el visor, con techos dibujados y revisados por una persona.

**La calidad del resultado depende casi por completo de la anotación del paso 2.**

```
preparar_anotacion.py ──► QGIS (dibujar techos) ──► armar_dataset_yolo.py ──► entrenar_yolo.py ──► visor
   celdas + borrador          celdas "completa"          recortes PNG + etiquetas      models/yolo26_chullo
```

## 0. Entorno

En la raíz del proyecto (Windows, con GPU NVIDIA):

```powershell
py -3.12 -m venv .venv-ml
.venv-ml\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv-ml\Scripts\python -m pip install -r requirements-yolo.txt
```

Sin GPU se puede entrenar igual (mucho más lento), o en Google Colab copiando la carpeta `dataset/` del paso 3.

## 1. Capas de anotación (ya generadas)

`data/training/yolo_chullo/` ya contiene:

- **`celdas.geojson`**: 59 cuadros de 128 × 128 m (256 px a 0.5 m/px) que tocan las franjas roja o amarilla.
  - Cada celda tiene un `split` fijo (`train`, `val` o `test`), asignado por bloques a lo largo del cauce.
  - Cada celda tiene un `estado`, que empieza en `pendiente`.
  - Cada celda tiene una `prioridad`: 1 = test, 2 = val, 3 = train. Anota en ese orden.
- **`techos.geojson`**: borrador con 1 560 huellas de Overture ya limpias y alineadas (antes eran las 405 detecciones del Mask R-CNN). Es un punto de partida, **no** una referencia: faltan techos y algunas huellas cubren un lote entero.

Para regenerarlas (por ejemplo con otro tamaño de celda) usa `--forzar`. **Ojo: borra las anotaciones hechas.**

```powershell
.venv-ml\Scripts\python scripts/preparar_anotacion.py --forzar
```

## 2. Anotar en QGIS

### Preparar el proyecto

1. Abre QGIS (gratuito, 3.28 o posterior) y arrastra estas tres capas:
   - `data/imagery/chullo/chullo_rgb.tif`
   - `data/training/yolo_chullo/celdas.geojson`
   - `data/training/yolo_chullo/techos.geojson`
2. Dale estilo a `celdas` para ver el avance: sin relleno y con borde categorizado por `estado`.
3. Activa la edición de `techos` con el lápiz de la barra de herramientas.

### Anotar una celda

1. Elige una celda `pendiente` y haz zoom hasta verla completa.
2. Revisa cada techo del borrador:
   - **Bórralo** si no es un techo (sombra, vehículo, árbol, terreno).
   - **Corrígelo** con la *Herramienta de vértices* si su contorno está mal.
   - **Divídelo** si une dos o más techos: bórralo y dibuja cada techo por separado.
3. Dibuja con *Añadir polígono* (`Ctrl+.`) **todos** los techos que falten.
4. En la tabla de atributos de `celdas`, cambia el `estado` de esa celda a `completa`.
5. Guarda las ediciones de ambas capas.

### Reglas para que el modelo aprenda bien

- **Una celda `completa` debe tener TODOS sus techos dibujados**, incluidos los que quedan fuera de las franjas y los que el borrador no detectó. Un techo sin dibujar le enseña al modelo que eso es "fondo".
- Dibuja **completo** el techo que cruza el borde de la celda: el script lo recorta solo.
- **Un polígono por techo.** Separa techos contiguos aunque compartan pared; es justo lo que el modelo actual no logra.
- No dibujes patios, calles, losas sin construir ni sombras. Si un árbol tapa parte de un techo, dibuja la parte visible.
- Ante la duda, sé consistente: aplica siempre el mismo criterio.
- No borres ni renombres columnas de `celdas.geojson` (`id`, `col_off`, `row_off`, `tamano_px`, `split`).
- No cambies el `split` de una celda después de entrenar con ella: mezclaría prueba y entrenamiento.

### Cuánto anotar

- **Primero, las 11 celdas test (`prioridad = 1`, unos 360 techos).** Hoy todos los modelos se miden contra Overture, que no es exacto. Con las celdas test revisadas por ti, `comparar_modelos.py --split test` mide la exactitud real y permite elegir el mejor modelo con datos fiables.
- **Primera ronda:** al menos **15 celdas train, 5 val y 5 test**, unos 500 a 1 000 techos. Reparte las celdas a lo largo de todo el corredor.
- **Ideal:** las 59 celdas.
- Cada celda adicional mejora el modelo más que cualquier ajuste de parámetros.

Opcional: el complemento **Geo-SAM** de QGIS segmenta un techo con un clic y acelera el dibujo. Revisa siempre su resultado.

Guarda tu avance en git con frecuencia (`celdas.geojson` y `techos.geojson` sí se versionan).

### Atajo sin anotar: huellas de Overture

Para tener un primer modelo YOLO sin dibujar nada, se pueden usar como etiquetas las huellas de edificios de **Overture Maps**, que combinan Google Open Buildings, Microsoft ML Buildings y OpenStreetMap:

```powershell
.venv-ml\Scripts\python -m pip install overturemaps
.venv-ml\Scripts\python scripts/importar_huellas_overture.py
.venv-ml\Scripts\python scripts/armar_dataset_yolo.py --celdas data/training/yolo_chullo/overture/celdas.geojson --techos data/training/yolo_chullo/overture/techos.geojson --origen overture
```

- **Qué descarga:** solo el recuadro del GeoTIFF, unas 5 000 huellas.
- **Limpieza y alineación** (`backend/huellas.py`, se puede omitir con `--sin-limpiar`):
  - descarta huellas de menos de 6 m²;
  - marca para ignorar las de más de 1 500 m² (lotes, manzanas o naves): el dataset pinta esa zona de gris, así no cuentan ni como techo ni como fondo;
  - corrige el desplazamiento de cada fuente buscando el corrimiento que hace coincidir los bordes de las huellas con los de la imagen. Solo se aplica si mejora la coincidencia en al menos 4 % y no cae en el borde de la búsqueda. En la práctica corrige sobre todo a Microsoft (unos 2 m).
- **Dónde las guarda:** en `data/training/yolo_chullo/overture/`, con todas las celdas marcadas como completas. Tus anotaciones de QGIS no se tocan.
- **Limitaciones:** nadie revisó estas huellas. Faltan techos, algunas cubren un lote entero y pueden ser de otra fecha que la imagen. El modelo hereda esos defectos, y sus métricas miden el acuerdo con Overture, no la exactitud.
- **Licencia:** ODbL. Conserva la atribución de `overture/metadatos.json`.
- **Uso recomendado:** como primer modelo y como borrador mucho más completo para anotar. Las anotaciones humanas siguen siendo la vía para un modelo fiable.

## 3. Armar el dataset

```powershell
.venv-ml\Scripts\python scripts/armar_dataset_yolo.py
```

Recorta cada celda `completa` como PNG y escribe sus techos en el formato de Ultralytics dentro de `data/training/yolo_chullo/dataset/`, una carpeta regenerable que no se versiona.

- En `train` añade recortes desplazados media celda cuando las celdas vecinas también están completas; así hay más variedad.
- Avisa si falta val o test, o si más de la mitad de los techos son del borrador sin editar.

### Más datos: otros distritos de Arequipa

```powershell
.venv-ml\Scripts\python scripts/ampliar_arequipa.py
.venv-ml\Scripts\python scripts/armar_dataset_yolo.py --celdas data/training/yolo_chullo/overture/celdas.geojson --techos data/training/yolo_chullo/overture/techos.geojson --origen overture --bloques-arequipa
```

- **Qué agrega:** 8 bloques de 1 × 1 km (`config/bloques_arequipa.json`) con imagen Esri y huellas de Overture limpias; 392 celdas y unos 20 000 techos. Hunter queda para validación.
- **Separación:** ningún bloque toca la imagen de la torrentera ni las zonas de prueba (el script lo comprueba).
- **Dónde:** imágenes en `data/imagery/arequipa_bloques/` (no se versionan); celdas y huellas en `data/training/yolo_arequipa/`.

### Techos limpios de otros países: RAMP

```powershell
.venv-ml\Scripts\python scripts/descargar_ramp.py
.venv-ml\Scripts\python scripts/armar_dataset_ramp.py
.venv-ml\Scripts\python scripts/preentrenar_ramp.py
```

- **Qué es:** [RAMP](https://source.coop/ramp/ramp) publica recortes de imágenes Maxar con techos dibujados y revisados por personas. Se descargan 1 200 recortes de Mascate, Les Cayes, Acra y Nairobi (unos 1.1 GB, en `data/externos/`).
- **Escala:** se remuestrean a 0.5 m/px y se rellenan hasta 256 px, para que un techo ocupe los mismos píxeles que en Arequipa.
- **Licencia:** CC BY-NC 4.0. Un modelo entrenado con RAMP es de uso **no comercial**; el manifiesto lo indica.
- **Dos formas de usarlo:** como punto de partida (`entrenar_yolo.py --base data/training/ramp_runs/preentrenado.pt --lr0 0.0005`) o entrenando a la vez con Arequipa (`entrenar_yolo.py --sumar-ramp`).

## 4. Entrenar

```powershell
.venv-ml\Scripts\python scripts/entrenar_yolo.py
```

- **Configuración por defecto:**
  - modelo base `yolo26s-seg.pt`;
  - hasta 150 épocas, que se detienen solas tras 40 épocas sin mejora en val;
  - entrada de 640 px (cada celda de 256 px se amplía 2.5×, porque los techos son pequeños);
  - giros y volteos, porque en vista cenital los techos no tienen "arriba".
- **Tiempo:** con unas decenas de celdas, en la RTX 5070 Ti debería tardar pocos minutos.
- **Qué hace:** elige la mejor época con val, evalúa **una sola vez** en test y registra el modelo en `models/yolo26_chullo/` (`weights.pt` y `manifest.json`).
- **Corridas:** las gráficas y ejemplos quedan en `data/training/yolo_chullo/runs/<fecha>/`. Mira `results.png` y `val_batch*_pred.jpg`.
- **Otro modelo base:** `--base yolo26m-seg.pt` es más grande y conviene cuando ya hay muchas anotaciones; `--base yolo11s-seg.pt` es la generación anterior.
- **Reentrenar:** con más anotaciones, repite los pasos 3 y 4 con `--reemplazar`.
- **Afinar un modelo previo:** `--lr0 0.0005` usa AdamW con una tasa baja y `--congelar N` fija las primeras N capas.
- **Mezclar con RAMP:** `--sumar-ramp` entrena con RAMP y Arequipa a la vez; val y test siguen siendo solo de Arequipa.
- **Entrada más grande:** `--imgsz 1024` amplía más cada celda; más lento.

Métrica a mirar: **F1 de máscaras en test** (`metricas_test.f1` del manifiesto).

El 0.249 del Mask R-CNN se midió con otra imagen y otras referencias. Para compararlos de forma justa, ejecuta ambos modelos en el visor y revisa las mismas celdas test.

## 5. Ver la mejora

```powershell
.venv-ml\Scripts\python scripts/comparar_modelos.py --split test
.venv-ml\Scripts\python scripts/comparar_modelos.py --celdas c028 c032
```

Por cada celda guarda un PNG en `data/training/yolo_chullo/comparaciones/` con cuatro paneles:

1. la imagen;
2. la referencia;
3. Mask R-CNN;
4. YOLO.

En las celdas **completas**, cada detección se pinta según el resultado:

| Color | Significado |
| --- | --- |
| Verde | Acierto (IoU ≥ 0.5 con un techo de referencia) |
| Rojo | Falso positivo |
| Amarillo | Techo de referencia omitido |

Al final imprime y guarda en `resumen.json` la precisión, la recuperación y el F1 de ambos modelos sobre las mismas celdas. Esa es la comparación justa.

Además del conteo por techo, mide el **área construida** (`f1_area`): compara la superficie detectada con la de referencia, sin exigir que cada techo coincida uno a uno. Es más tolerante con techos unidos o huellas que cubren un lote, y responde mejor a la pregunta del proyecto: cuánto hay construido en las franjas.

**Para medir, usa celdas `test`:** el modelo no las vio al entrenar.

**En celdas sin anotar no se miden aciertos:** solo se dibujan las detecciones, porque el borrador no es una referencia. Por ejemplo, Mask R-CNN parecería acertar en todos los techos que él mismo puso en el borrador.

### Fuera de la torrentera

```powershell
.venv-ml\Scripts\python scripts/probar_otras_zonas.py
```

Prueba ambos modelos en las 20 zonas de `config/zonas_prueba.json`: 10 fuera de Perú, 5 de Arequipa lejos de la torrentera y 5 de Lima.

- **Datos:** para cada zona descarga un recorte de Esri y las huellas de Overture del mismo lugar. Mide en una celda de 128 m, la misma escala del entrenamiento.
- **Salida:** escribe las figuras, `mosaico_yolo.png` y `resumen.json` en `data/evaluacion/otras_zonas/`, una carpeta que no se versiona.
- **Control:** rechaza cualquier punto que se superponga a la imagen de entrenamiento.

## 6. Usarlo en el visor

Desde que existe `models/yolo26_chullo/manifest.json`, el servidor usa YOLO automáticamente:

- **Inicio:** `iniciar.bat` ya prefiere `.venv-ml`.
- **Mosaicos:** se infiere con el mismo tamaño de celda del entrenamiento.
- **Umbral:** se usa el de F1 máximo en val.
- **Velocidad:** el corredor completo tardó 14 s en CPU con YOLO26s, frente a 62 s con Mask R-CNN en la misma máquina.

| Variable | Efecto |
| --- | --- |
| `CHULLO_MODELO=auto` | YOLO si está entrenado; si no, Mask R-CNN (por defecto) |
| `CHULLO_MODELO=maskrcnn` | Fuerza el modelo piloto anterior |
| `CHULLO_MODELO=yolo` | Exige YOLO; falla si no está entrenado |

- **Línea de comandos:**

  ```powershell
  .venv-ml\Scripts\python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida web/outputs/detection --modelo yolo
  ```

- **Docker:** sigue usando Mask R-CNN, porque no instala Ultralytics ni copia `models/yolo26_chullo`.
- **GitHub Pages:** muestra las detecciones guardadas en `web/outputs/detection/`. Para publicar las de YOLO, ejecuta la detección y versiona esos dos archivos.

## Resultados de noviembre de 2026 (sin anotación manual)

F1 de **área construida** contra huellas de Overture (que no revisó nadie). Corredor: 11 celdas test. Zonas: `probar_otras_zonas.py`.

| Variante | Corredor | Arequipa (5 zonas) | Lima (5) | Fuera de Perú (10) | Media |
| --- | --- | --- | --- | --- | --- |
| Mask R-CNN piloto | 0.28 | 0.29 | **0.35** | 0.31 | 0.31 |
| Overture del corredor (36 celdas) | 0.46 | **0.48** | 0.16 | 0.24 | 0.34 |
| + 8 bloques de Arequipa | 0.49 | 0.40 | 0.20 | 0.35 | 0.36 |
| RAMP afinado con Arequipa | **0.49** | 0.42 | 0.21 | 0.33 | 0.36 |
| Solo RAMP | 0.38 | 0.35 | 0.25 | **0.52** | 0.37 |
| YOLO26-Chullo: RAMP + Arequipa a la vez | 0.46 | 0.42 | 0.22 | 0.45 | 0.39 |
| **YOLO26-Chullo con umbral 0.05 (modelo final)** | **0.58** | **0.60** | 0.34 | **0.58** | **0.53** |

Todas las filas salvo la última usan umbral 0.10. Al registrar los modelos se aplicaba un piso de 0.10 al umbral, pero estos modelos dan confianzas bajas (0.03–0.08) y ese piso descartaba muchas casas que sí detectaban. El umbral final, 0.05, se eligió barriendo 0.02–0.10 en las celdas val del corredor. Ya no hay piso: `entrenar_yolo.py` solo evita valores por debajo de 0.02.

Lo que mostraron estas pruebas:

- **Las etiquetas son el límite.** Con las huellas de Overture el modelo no logra ajustarse ni a sus propios datos de entrenamiento (mAP50 de máscaras 0.12), aunque tenga 15 veces más techos. Con las etiquetas limpias de RAMP, el mismo proceso llega a mAP50 0.77 en su validación.
- **Más datos de Overture ayudan poco** en la torrentera y empeoran algo en otros distritos.
- **RAMP generaliza mejor** fuera de Arequipa; mezclado con Arequipa (YOLO26-Chullo) da el mejor equilibrio.
- **Ninguno funciona bien en Lima.** Las diferencias de ±0.05 entre variantes están dentro del ruido de 5 zonas.
- **El siguiente salto requiere anotación humana**, empezando por las 11 celdas test para poder medir de verdad.

## Licencias y límites

- **Ultralytics y sus pesos:** licencia **AGPL-3.0**. Un proyecto académico de código abierto la cumple; un uso comercial cerrado requiere licencia de Ultralytics.
- **Imagen:** Esri World Imagery. Se conservan su atribución y condiciones; entrenar no cambia esas condiciones.
- **Alcance:** el modelo detecta **cubiertas visibles**. No confirma viviendas, uso residencial, peligro ni permiso para construir.
- **Validez de las métricas:** solo para las celdas anotadas de esta imagen.
- **Independencia de val y test:** no es total. Las celdas vecinas pueden compartir un techo en el borde, y todas vienen de una sola captura.
