# Entrenar el detector de techos con YOLO-seg

El modelo Mask R-CNN actual (`models/chullo_local_v1`) acierta poco (F1 ≈ 0.25). Sus causas principales:

- se entrenó con solo 3 recortes y unos 150 techos;
- las anotaciones no tuvieron revisión humana;
- se entrenó con una imagen distinta (Google Earth/Airbus) de la que analiza (Esri).

Este flujo entrena un modelo **YOLO-seg** (Ultralytics) sobre la **misma imagen Esri** que usa el visor, con techos dibujados y revisados por una persona.

**La calidad del resultado depende casi por completo de la anotación del paso 2.**

```
preparar_anotacion.py ──► QGIS (dibujar techos) ──► armar_dataset_yolo.py ──► entrenar_yolo.py ──► visor
   celdas + borrador          celdas "completa"          recortes PNG + etiquetas      models/yolo_chullo_v1
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
- **`techos.geojson`**: borrador con las 405 detecciones guardadas del Mask R-CNN. Es un punto de partida, **no** una referencia: omite muchos techos y une otros.

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

- **Primera ronda:** al menos **15 celdas train, 5 val y 5 test**, unos 500 a 1 000 techos. Reparte las celdas a lo largo de todo el corredor.
- **Ideal:** las 59 celdas.
- Cada celda adicional mejora el modelo más que cualquier ajuste de parámetros.

Opcional: el complemento **Geo-SAM** de QGIS segmenta un techo con un clic y acelera el dibujo. Revisa siempre su resultado.

Guarda tu avance en git con frecuencia (`celdas.geojson` y `techos.geojson` sí se versionan).

## 3. Armar el dataset

```powershell
.venv-ml\Scripts\python scripts/armar_dataset_yolo.py
```

Recorta cada celda `completa` como PNG y escribe sus techos en el formato de Ultralytics dentro de `data/training/yolo_chullo/dataset/`, una carpeta regenerable que no se versiona.

- En `train` añade recortes desplazados media celda cuando las celdas vecinas también están completas; así hay más variedad.
- Avisa si falta val o test, o si más de la mitad de los techos son del borrador sin editar.

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
- **Qué hace:** elige la mejor época con val, evalúa **una sola vez** en test y registra el modelo en `models/yolo_chullo_v1/` (`weights.pt` y `manifest.json`).
- **Corridas:** las gráficas y ejemplos quedan en `data/training/yolo_chullo/runs/<fecha>/`. Mira `results.png` y `val_batch*_pred.jpg`.
- **Otro modelo base:** `--base yolo26m-seg.pt` es más grande y conviene cuando ya hay muchas anotaciones; `--base yolo11s-seg.pt` es la generación anterior.
- **Reentrenar:** con más anotaciones, repite los pasos 3 y 4 con `--reemplazar`.

Métrica a mirar: **F1 de máscaras en test** (`metricas_test.f1` del manifiesto).

El 0.249 del Mask R-CNN se midió con otra imagen y otras referencias. Para compararlos de forma justa, ejecuta ambos modelos en el visor y revisa las mismas celdas test.

## 5. Usarlo en el visor

Desde que existe `models/yolo_chullo_v1/manifest.json`, el servidor usa YOLO automáticamente:

- **Inicio:** `iniciar.bat` ya prefiere `.venv-ml`.
- **Mosaicos:** se infiere con el mismo tamaño de celda del entrenamiento.
- **Umbral:** se usa el de F1 máximo en val.
- **Velocidad:** el corredor completo tarda segundos en CPU, frente a unos 4 minutos y medio con Mask R-CNN.

| Variable | Efecto |
| --- | --- |
| `CHULLO_MODELO=auto` | YOLO si está entrenado; si no, Mask R-CNN (por defecto) |
| `CHULLO_MODELO=maskrcnn` | Fuerza el modelo piloto anterior |
| `CHULLO_MODELO=yolo` | Exige YOLO; falla si no está entrenado |

- **Línea de comandos:**

  ```powershell
  .venv-ml\Scripts\python scripts/run_detection.py --imagen data/imagery/chullo/chullo_rgb.tif --salida web/outputs/detection --modelo yolo
  ```

- **Docker:** sigue usando Mask R-CNN, porque no instala Ultralytics ni copia `models/yolo_chullo_v1`.
- **GitHub Pages:** muestra las detecciones guardadas en `web/outputs/detection/`. Para publicar las de YOLO, ejecuta la detección y versiona esos dos archivos.

## Licencias y límites

- **Ultralytics y sus pesos:** licencia **AGPL-3.0**. Un proyecto académico de código abierto la cumple; un uso comercial cerrado requiere licencia de Ultralytics.
- **Imagen:** Esri World Imagery. Se conservan su atribución y condiciones; entrenar no cambia esas condiciones.
- **Alcance:** el modelo detecta **cubiertas visibles**. No confirma viviendas, uso residencial, peligro ni permiso para construir.
- **Validez de las métricas:** solo para las celdas anotadas de esta imagen.
- **Independencia de val y test:** no es total. Las celdas vecinas pueden compartir un techo en el borde, y todas vienen de una sola captura.
