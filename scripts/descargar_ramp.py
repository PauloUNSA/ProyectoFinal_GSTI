"""Descarga una muestra del dataset abierto RAMP (techos anotados a mano).

Uso:
    python scripts/descargar_ramp.py
    python scripts/descargar_ramp.py --regiones ramp_muscat_oman --por-region 2000

RAMP (Replicable AI for Microplanning, DevGlobal/OMS) publica en Source
Cooperative recortes de 256 × 256 px de imágenes Maxar con los techos
dibujados y revisados. Licencia CC BY-NC 4.0: solo uso no comercial, con
atribución. Se descargan pares imagen/etiqueta elegidos al azar con semilla
fija; los archivos ya descargados se reutilizan.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import random
import re

BASE = Path(__file__).resolve().parents[1]
URL = "https://data.source.coop/ramp/ramp/"
REGIONES = ("ramp_muscat_oman", "ramp_les_cayes_haiti", "ramp_accra_ghana", "ramp_nairobi_kenya")


def listar(sesion, prefijo):
    claves, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefijo}
        if token:
            params["continuation-token"] = token
        texto = sesion.get(URL, params=params, timeout=60).text
        claves += re.findall(r"<Key>([^<]+)</Key>", texto)
        siguiente = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", texto)
        if not siguiente:
            return claves
        token = siguiente.group(1)


def main():
    import requests
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--regiones", nargs="*", default=list(REGIONES))
    parser.add_argument("--por-region", type=int, default=1200)
    parser.add_argument("--destino", default=str(BASE / "data/externos/ramp"))
    args = parser.parse_args()
    sesion = requests.Session()
    for region in args.regiones:
        ids = sorted(Path(k).stem for k in listar(sesion, f"{region}/labels/") if k.endswith(".geojson"))
        elegidos = random.Random(42).sample(ids, min(args.por_region, len(ids)))
        destino = Path(args.destino) / region
        (destino / "source").mkdir(parents=True, exist_ok=True)
        (destino / "labels").mkdir(parents=True, exist_ok=True)

        def bajar(chip):
            for carpeta, ext in (("source", ".tif"), ("labels", ".geojson")):
                path = destino / carpeta / f"{chip}{ext}"
                if path.exists() and path.stat().st_size:
                    continue
                r = sesion.get(f"{URL}{region}/{carpeta}/{chip}{ext}", timeout=120)
                r.raise_for_status()
                path.write_bytes(r.content)

        with ThreadPoolExecutor(16) as pool:
            list(pool.map(bajar, elegidos))
        print(f"{region}: {len(elegidos)} de {len(ids)} recortes -> {destino}", flush=True)
    (Path(args.destino) / "LICENCIA.txt").write_text(
        "RAMP · Replicable AI for Microplanning (DevGlobal, OMS). https://source.coop/ramp/ramp\n"
        "DOI 10.34911/rdnt.b0noju · Licencia CC BY-NC 4.0: uso no comercial con atribución.\n"
        "Imágenes: Maxar Open Data Program.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
