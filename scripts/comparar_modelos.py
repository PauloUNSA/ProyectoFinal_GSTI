"""Compara Mask R-CNN y YOLO en celdas de anotación, con imagen y métricas.

Uso (con .venv-ml):
    python scripts/comparar_modelos.py --celdas c028 c032
    python scripts/comparar_modelos.py --split test        # todas las celdas test completas

Por cada celda guarda un PNG con cuatro paneles (imagen, referencia, Mask
R-CNN, YOLO) en data/training/yolo_chullo/comparaciones/. Si la celda está
marcada como completa, cuenta aciertos (IoU ≥ 0.5), falsos positivos y
omisiones de cada modelo; si no, la referencia es solo el borrador.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
ANOTACION = BASE / "data/training/yolo_chullo"
ESCALA = 3
COLORES = {"referencia": (59, 130, 246), "acierto": (34, 197, 94), "falso": (239, 68, 68), "omitido": (250, 204, 21)}


def fuentes():
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arialbd.ttf", 22), ImageFont.truetype("arial.ttf", 17)
    except OSError:
        return ImageFont.load_default(22), ImageFont.load_default(17)


def emparejar(predichas, referencias, iou_minimo=0.5):
    """Emparejamiento voraz por IoU de máscaras: devuelve índices acertados de cada lado."""
    pares = []
    for i, p in enumerate(predichas):
        for j, r in enumerate(referencias):
            inter = np.logical_and(p, r).sum()
            if inter:
                iou = inter / np.logical_or(p, r).sum()
                if iou >= iou_minimo:
                    pares.append((iou, i, j))
    usados_p, usados_r = set(), set()
    for _, i, j in sorted(pares, reverse=True):
        if i not in usados_p and j not in usados_r:
            usados_p.add(i)
            usados_r.add(j)
    return usados_p, usados_r


def metricas(n_pred, n_ref, aciertos):
    p = aciertos / n_pred if n_pred else 0.0
    r = aciertos / n_ref if n_ref else 0.0
    return {"aciertos": aciertos, "falsos_positivos": n_pred - aciertos, "omitidos": n_ref - aciertos,
            "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def pixeles_area(predichas, referencias, tam):
    """Píxeles de área construida: (predicho ∩ referencia, predicho, referencia)."""
    pred = np.zeros((tam, tam), bool)
    ref = np.zeros((tam, tam), bool)
    for m in predichas:
        pred |= m
    for m in referencias:
        ref |= m
    return int((pred & ref).sum()), int(pred.sum()), int(ref.sum())


def metricas_area(inter, pred, ref, res_m=0.5):
    """Área construida: tolera techos unidos o lotes enteros, que el conteo por techo castiga."""
    p = inter / pred if pred else 0.0
    r = inter / ref if ref else 0.0
    return {"area_predicha_m2": pred * res_m ** 2, "area_referencia_m2": ref * res_m ** 2,
            "precision_area": p, "recall_area": r, "f1_area": 2 * p * r / (p + r) if p + r else 0.0}


def mascaras_referencia(techos, ventana_transform, tam):
    from rasterio.features import rasterize
    mascaras = []
    for t in techos:
        m = rasterize([(t, 1)], out_shape=(tam, tam), transform=ventana_transform, dtype="uint8").astype(bool)
        if m.sum() >= 8:  # mismo mínimo que las etiquetas YOLO
            mascaras.append(m)
    return mascaras


def panel(rgb, mascaras, colores, etiquetas=None):
    from PIL import Image, ImageDraw
    tam = rgb.shape[0]
    img = Image.fromarray(rgb).resize((tam * ESCALA, tam * ESCALA), Image.LANCZOS).convert("RGBA")
    capa = np.zeros((tam * ESCALA, tam * ESCALA, 4), dtype=np.uint8)
    for m, color in zip(mascaras, colores):
        grande = np.kron(m, np.ones((ESCALA, ESCALA), dtype=bool))
        borde = grande & ~(np.roll(grande, 1, 0) & np.roll(grande, -1, 0) & np.roll(grande, 1, 1) & np.roll(grande, -1, 1))
        capa[grande] = color + (90,)
        capa[borde] = color + (255,)
    img.alpha_composite(Image.fromarray(capa))
    if etiquetas:
        dibujo = ImageDraw.Draw(img)
        _, chica = fuentes()
        for m, texto in zip(mascaras, etiquetas):
            ys, xs = np.nonzero(m)
            dibujo.text((xs.mean() * ESCALA - 14, ys.mean() * ESCALA - 9), texto, font=chica,
                        fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    return img


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--celdas", nargs="*", default=[], help="Ids de celda, p. ej. c028")
    parser.add_argument("--split", choices=["train", "val", "test"], help="Todas las celdas completas de ese split")
    parser.add_argument("--imagen", default=str(BASE / "data/imagery/chullo/chullo_rgb.tif"))
    parser.add_argument("--celdas-geojson", default=str(ANOTACION / "celdas.geojson"))
    parser.add_argument("--techos", default=str(ANOTACION / "techos.geojson"))
    parser.add_argument("--destino", default=str(ANOTACION / "comparaciones"))
    parser.add_argument("--dispositivo", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--umbral-yolo", type=float, default=None, help="Umbral de confianza de YOLO; por defecto, el del manifiesto")
    args = parser.parse_args()

    import rasterio
    from PIL import Image, ImageDraw
    from rasterio.windows import Window
    from backend import modelos
    from backend.dataset_yolo import leer_celdas, leer_techos
    from backend.detector import _predictor_maskrcnn, _predictor_yolo
    from shapely import STRtree
    from shapely.geometry import box
    from rasterio.windows import bounds

    celdas = {c["id"]: c for c in leer_celdas(args.celdas_geojson)}
    elegidas = list(args.celdas)
    if args.split:
        elegidas += [i for i, c in celdas.items() if c["split"] == args.split and c["completa"]]
    if not elegidas:
        parser.exit(1, "Indica --celdas o un --split con celdas completas.\n")
    desconocidas = [i for i in elegidas if i not in celdas]
    if desconocidas:
        parser.exit(1, f"Celdas inexistentes: {', '.join(desconocidas)}\n")

    predictores = {"Mask R-CNN piloto": _predictor_maskrcnn(args.dispositivo, 0.5)}
    yolo = modelos.describir("yolo")
    if not yolo["error"]:
        predictores["YOLO"] = _predictor_yolo(args.dispositivo, args.umbral_yolo or modelos.umbral_por_defecto("yolo"))
    destino = Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    grande, chica = fuentes()
    totales = {nombre: {"pred": 0, "ref": 0, "aciertos": 0, "px_inter": 0, "px_pred": 0, "px_ref": 0} for nombre in predictores}
    completas = 0

    origenes = {str((f.get("properties") or {}).get("origen") or "") for f in
                json.loads(Path(args.techos).read_text(encoding="utf-8-sig")).get("features", [])}
    nombre_ref = "Referencia Overture (sin revisión)" if any(o.startswith("overture") for o in origenes) else "Referencia humana"

    with rasterio.open(args.imagen) as src:
        techos = leer_techos(args.techos, src.crs)
        indice = STRtree([t["geom"] for t in techos])
        for celda_id in elegidas:
            c = celdas[celda_id]
            col, fila, tam = c["col_off"], c["row_off"], c["tamano_px"]
            ventana = Window(col, fila, tam, tam)
            rgb = src.read([1, 2, 3], window=ventana).transpose(1, 2, 0)
            huella = box(*bounds(ventana, src.transform))
            refs = mascaras_referencia([techos[k]["geom"] for k in indice.query(huella, predicate="intersects")],
                                       src.window_transform(ventana), tam)
            paneles = [(panel(rgb, [], []), "Imagen Esri", f"Celda {celda_id} · split {c['split']} · 128 × 128 m")]
            titulo_ref = nombre_ref if c["completa"] else "Borrador sin revisar"
            sub_ref = f"{len(refs)} techos" + ("" if c["completa"] else " · no sirve para medir")
            colores_ref = [COLORES["referencia"]] * len(refs)
            resultados = {}
            for nombre, (predecir, _, info) in predictores.items():
                # Mask R-CNN se aplica como en producción: mosaico de 512 px centrado en la celda.
                margen = max(0, (512 - tam) // 2) if nombre.startswith("Mask") else 0
                datos = src.read([1, 2, 3], window=Window(col - margen, fila - margen, tam + 2 * margen, tam + 2 * margen),
                                 boundless=True)
                puntuaciones, mascaras = predecir(datos)
                mascaras = [m[margen:margen + tam, margen:margen + tam] for m in mascaras]
                pares = [(s, m) for s, m in zip(puntuaciones, mascaras) if m.sum() >= 8]
                mascaras = [m for _, m in pares]
                aciertos_p, aciertos_r = emparejar(mascaras, refs) if c["completa"] else (set(), set())
                resultados[nombre] = (pares, aciertos_p, aciertos_r)
            for nombre, (pares, aciertos_p, aciertos_r) in resultados.items():
                mascaras = [m for _, m in pares]
                colores = [COLORES["acierto"] if i in aciertos_p else COLORES["falso"] for i in range(len(mascaras))] \
                    if c["completa"] else [(168, 85, 247)] * len(mascaras)
                # Las omisiones se dibujan en amarillo con la referencia que no se encontró.
                omitidas = [r for j, r in enumerate(refs) if j not in aciertos_r] if c["completa"] else []
                img = panel(rgb, mascaras + omitidas, colores + [COLORES["omitido"]] * len(omitidas),
                            [f"{s:.2f}" for s, _ in pares] + [""] * len(omitidas))
                if c["completa"]:
                    m = metricas(len(mascaras), len(refs), len(aciertos_p))
                    t = totales[nombre]
                    t["pred"] += len(mascaras)
                    t["ref"] += len(refs)
                    t["aciertos"] += len(aciertos_p)
                    px = pixeles_area(mascaras, refs, tam)
                    for clave, valor in zip(("px_inter", "px_pred", "px_ref"), px):
                        t[clave] += valor
                    area = metricas_area(*px)
                    sub = (f"F1 techos {m['f1']:.2f} · F1 área {area['f1_area']:.2f} · "
                           f"aciertos {m['aciertos']} · falsos {m['falsos_positivos']} · omitidos {m['omitidos']}")
                else:
                    sub = f"{len(mascaras)} techos detectados"
                paneles.append((img, nombre, sub))
            paneles.insert(1, (panel(rgb, refs, colores_ref), titulo_ref, sub_ref))
            if "YOLO" not in predictores:
                vacio = Image.new("RGBA", (tam * ESCALA, tam * ESCALA), (241, 245, 235, 255))
                ImageDraw.Draw(vacio).text((40, tam * ESCALA // 2 - 20), "Aún no hay modelo YOLO entrenado.\nEjecuta scripts/entrenar_yolo.py",
                                           font=grande, fill=(83, 98, 89))
                paneles.append((vacio, "YOLO", "—"))
            completas += c["completa"]

            ancho = tam * ESCALA
            lienzo = Image.new("RGB", (len(paneles) * (ancho + 10) + 10, ancho + 120), "white")
            dibujo = ImageDraw.Draw(lienzo)
            for k, (img, titulo, sub) in enumerate(paneles):
                x = 10 + k * (ancho + 10)
                lienzo.paste(img.convert("RGB"), (x, 80))
                dibujo.text((x, 12), titulo, font=grande, fill=(36, 52, 45))
                dibujo.text((x, 46), sub, font=chica, fill=(83, 98, 89))
            leyenda = ("Verde: acierto (IoU ≥ 0.5) · Rojo: falso positivo · Amarillo: techo omitido · Azul: referencia"
                       if c["completa"] else "Celda sin anotar: se muestran las detecciones sin medir aciertos.")
            dibujo.text((10, ancho + 90), leyenda, font=chica, fill=(83, 98, 89))
            salida = destino / f"{celda_id}.png"
            lienzo.save(salida)
            print(salida)

    if completas:
        resumen = {nombre: {**metricas(t["pred"], t["ref"], t["aciertos"]),
                            **metricas_area(t["px_inter"], t["px_pred"], t["px_ref"])} for nombre, t in totales.items()}
        print(json.dumps({"celdas_completas": completas, "modelos": resumen}, ensure_ascii=False, indent=2))
        (destino / "resumen.json").write_text(json.dumps({"celdas": elegidas, "modelos": resumen}, ensure_ascii=False, indent=2),
                                              encoding="utf-8")


if __name__ == "__main__":
    main()
