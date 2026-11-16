"""Figura por tramos de la torrentera con las detecciones publicadas en el visor.

Uso (con .venv-ml):
    python scripts/figura_detecciones.py
    python scripts/figura_detecciones.py --tramos 8 --lado 200

Reparte N tramos a lo largo de la referencia central del cauce y dibuja en
cada uno la imagen Esri, los límites del corredor rojo y de la franja
amarilla, y los contornos de web/outputs/detection/buildings.geojson
coloreados por clase. Guarda data/evaluacion/torrentera_tramos.png.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
import sys

import numpy as np

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
COLORES = {"rojo": (220, 38, 38), "amarillo": (250, 204, 21)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tramos", type=int, default=6)
    parser.add_argument("--lado", type=float, default=192, help="Lado de cada tramo en metros")
    parser.add_argument("--salida", default=str(BASE / "data/evaluacion/torrentera_tramos.png"))
    args = parser.parse_args()

    import rasterio
    from PIL import Image, ImageDraw
    from pyproj import Transformer
    from rasterio.windows import from_bounds
    from shapely.geometry import box, shape
    from shapely import transform as transformar
    from backend.spatial import construir_zonas
    sys.path.insert(0, str(BASE / "scripts"))
    from comparar_modelos import fuentes

    limites = json.loads((BASE / "web/layers/limites-faja-cayma.geojson").read_text(encoding="utf-8-sig"))
    detecciones = json.loads((BASE / "web/outputs/detection/buildings.geojson").read_text(encoding="utf-8"))
    manifest = json.loads((BASE / "web/outputs/detection/manifest.json").read_text(encoding="utf-8"))
    zonas = construir_zonas(limites, manifest.get("zonas", {}).get("amarillo_m", 20))
    a_m = Transformer.from_crs(4326, zonas["crs"], always_xy=True).transform
    contornos = [(transformar(shape(f["geometry"]), a_m, interleaved=False), f["properties"]) for f in detecciones["features"]]
    grande, chica = fuentes()
    escala = 2
    paneles = []
    with rasterio.open(BASE / "data/imagery/chullo/chullo_rgb.tif") as src:
        cauce = zonas["cauce"]
        for k in range(args.tramos):
            distancia = cauce.length * (k + 0.5) / args.tramos
            centro = cauce.interpolate(distancia)
            recuadro = box(centro.x - args.lado / 2, centro.y - args.lado / 2, centro.x + args.lado / 2, centro.y + args.lado / 2)
            ventana = from_bounds(*recuadro.bounds, src.transform).round_offsets().round_lengths()
            rgb = src.read([1, 2, 3], window=ventana, boundless=True).transpose(1, 2, 0)
            alto, ancho = rgb.shape[:2]
            im = Image.fromarray(rgb).resize((ancho * escala, alto * escala), Image.LANCZOS).convert("RGBA")
            a, b, c, d, e, f = (~src.window_transform(ventana))[:6]

            def px(geom):
                return transformar(geom, lambda xy: np.column_stack(((a * xy[:, 0] + b * xy[:, 1] + c) * escala,
                                                                       (d * xy[:, 0] + e * xy[:, 1] + f) * escala)))
            capa = Image.new("RGBA", im.size, (0, 0, 0, 0))
            dibujo = ImageDraw.Draw(capa)
            cuenta = {"rojo": 0, "amarillo": 0}
            for geom, props in contornos:
                if not geom.intersects(recuadro):
                    continue
                color = COLORES.get(props.get("clase"), (102, 120, 139))
                cuenta[props.get("clase")] = cuenta.get(props.get("clase"), 0) + 1
                for parte in getattr(geom, "geoms", [geom]):
                    dibujo.polygon([tuple(p) for p in np.asarray(px(parte).exterior.coords)], fill=color + (115,), outline=color + (255,), width=2)
            for clave, color in (("exterior", (234, 179, 8)), ("rojo", (220, 38, 38))):
                borde = zonas[clave].boundary.intersection(recuadro.buffer(5))
                for linea in getattr(borde, "geoms", [borde]):
                    if linea.geom_type == "LineString":
                        dibujo.line([tuple(p) for p in np.asarray(px(linea).coords)], fill=color + (255,), width=3)
            im.alpha_composite(capa)
            km = distancia / 1000
            paneles.append((im, f"Tramo {k + 1} · km {km:.1f} del cauce",
                            f"{cuenta['rojo']} rojos · {cuenta['amarillo']} amarillos · {args.lado:.0f} × {args.lado:.0f} m"))

    columnas = 3
    lado_px = paneles[0][0].size[0]
    filas = math.ceil(len(paneles) / columnas)
    lienzo = Image.new("RGB", (columnas * (lado_px + 12) + 12, filas * (lado_px + 80) + 70), "white")
    dibujo = ImageDraw.Draw(lienzo)
    for k, (im, titulo, sub) in enumerate(paneles):
        x, y = 12 + (k % columnas) * (lado_px + 12), 12 + (k // columnas) * (lado_px + 80)
        dibujo.text((x, y), titulo, font=grande, fill=(36, 52, 45))
        dibujo.text((x, y + 30), sub, font=chica, fill=(83, 98, 89))
        lienzo.paste(im.convert("RGB"), (x, y + 60))
    pie = (f"{manifest.get('arquitectura', '')} · {manifest['count']} contornos en franjas "
           f"(rojo {manifest['counts_by_class'].get('rojo', 0)}, amarillo {manifest['counts_by_class'].get('amarillo', 0)}) · "
           "Rojo: toca el corredor entre límites ANA · Amarillo: franja exterior de 20 m · Sin revisión humana.")
    dibujo.text((12, lienzo.size[1] - 46), pie, font=chica, fill=(83, 98, 89))
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    lienzo.save(args.salida)
    print(args.salida)


if __name__ == "__main__":
    main()
