# Estado actual · 31/10/2026

Se corrigió el corredor rojo para cubrir exactamente el espacio entre los límites azul y morado. El amarillo es un anillo exterior configurable y no se superpone al interior rojo. Se eliminó el cierre erróneo de la referencia central.

La CNN usa las mismas zonas UTM que el visor. Se repararon la máscara válida RGB (de 3D a 2D), el error `pieces`/`piezas`, el tratamiento de cero detecciones y las rutas de publicación. Los errores ya no se presentan como ejecuciones exitosas de cero edificios, y no borran resultados anteriores.

La imagen anterior era un PNG sin georreferenciación renombrado como `.tif`; se conserva como `data/imagery/chullo/captura_original_sin_crs.png`. El GeoTIFF de `gsti-teo` no intersectaba este tramo ANA. La entrada actual es una captura georreferenciada del corredor desde Esri World Imagery, con extensión y CRS devueltos por su API y procedencia en `chullo_rgb.json`.

Se integró el modelo local Chullo v1 ya existente, con sus pesos verificados y documentos originales. No hubo entrenamiento nuevo. Su precisión sigue siendo limitada: requiere revisión y no permite afirmar que cada contorno es una casa individual.

Verificación: 26 pruebas Python aprobadas, prueba del navegador aprobada y ejecución CNN real completa: 405 contornos candidatos (118 rojos y 287 amarillos), 49 mosaicos procesados. También se verifica la ruta HTTP de inferencia y descarga del GeoJSON con un recorte real. Los resultados completos están guardados bajo `web/outputs/detection/`.

La guía vigente es `LEEME.md`. Los textos anteriores de planificación y explicación del GeoTIFF describen el estado previo a esta corrección.
