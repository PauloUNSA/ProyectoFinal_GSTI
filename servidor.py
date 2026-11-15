"""Servidor local: visor, franjas compartidas y detección CNN real."""
from __future__ import annotations
import argparse
import importlib.util
import json
import math
import os
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUTS_DIR = WEB_DIR / "outputs/detection"
DEFAULT_IMAGE = BASE_DIR / "data/imagery/chullo/chullo_rgb.tif"
LIMITES_PATH = WEB_DIR / "layers/limites-faja-cayma.geojson"
sys.path.insert(0, str(BASE_DIR))
from backend.modelos import describir, resolver_tipo  # noqa: E402
DETECTION_LOCK = threading.Lock()


class ServidorLocal(ThreadingHTTPServer):
    # Windows permite enlazar varias instancias con SO_REUSEADDR. Impedir que
    # una copia antigua siga atendiendo el mismo puerto tras reiniciar.
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def leer_bandas(amarillo=20):
    from backend.spatial import generar_poligonos_banda
    limites = json.loads(LIMITES_PATH.read_text(encoding="utf-8-sig"))
    bandas = generar_poligonos_banda(limites, amarillo_m=amarillo)
    return {"type": "FeatureCollection", "features": [bandas[c] for c in ("amarillo", "rojo", "cauce") if bandas[c]["geometry"]["coordinates"]], "metadata": bandas["metadata"]}


class Archivos(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".geojson": "application/geo+json", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}

    def list_directory(self, path):
        self.send_error(403, "Listado de carpetas deshabilitado")
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/api/bands":
                    self._send_json(200, leer_bandas(float(params.get("amarillo", [20])[0])))
                elif parsed.path == "/api/detect":
                    self._run_detection(params)
                elif parsed.path == "/api/status":
                    self._status()
                elif parsed.path == "/api/list":
                    archivos = [{"nombre": f.name, "tamano": f.stat().st_size} for f in OUTPUTS_DIR.glob("*") if f.is_file()]
                    self._send_json(200, {"archivos": archivos})
                else:
                    self._send_json(404, {"estado": "error", "error": "Endpoint API no encontrado"})
            except (ValueError, FileNotFoundError) as exc:
                self._send_json(400, {"estado": "error", "error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"estado": "error", "error": str(exc)})
            return
        super().do_GET()

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _run_detection(self, params):
        if os.getenv("CHULLO_ENABLE_DETECTION", "1") != "1":
            self._send_json(403, {"estado": "error", "error": "Las nuevas inferencias están desactivadas en este servidor."})
            return
        from backend.raster import validar_imagen
        imagen = Path(params.get("imagen", [str(DEFAULT_IMAGE)])[0])
        if not imagen.is_absolute():
            imagen = BASE_DIR / imagen
        if os.getenv("CHULLO_PUBLIC", "0") == "1" and imagen.resolve() != DEFAULT_IMAGE.resolve():
            raise ValueError("El servidor público solo analiza la imagen del sector configurada.")
        umbral = float(params["umbral"][0]) if params.get("umbral") else None
        amarillo = float(params.get("amarillo", [20])[0])
        if umbral is not None and (not math.isfinite(umbral) or not 0 <= umbral <= 1):
            raise ValueError("El umbral debe estar entre 0 y 1.")
        if not math.isfinite(amarillo) or not 0 <= amarillo <= 500:
            raise ValueError("El ancho amarillo debe estar entre 0 y 500 m.")
        if params.get("salida", ["outputs/detection"])[0].strip("/") != "outputs/detection":
            raise ValueError("La salida del visor es outputs/detection.")
        validar_imagen(imagen)
        if not DETECTION_LOCK.acquire(blocking=False):
            self._send_json(409, {"estado": "error", "error": "Ya hay una detección CNN en curso."})
            return
        try:
            OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
            # Publicar solo resultados completos. Un fallo conserva el resultado anterior.
            with tempfile.TemporaryDirectory(prefix="chullo-cnn-") as temp:
                comando = [sys.executable, "-u", str(SCRIPTS_DIR / "run_detection.py"), "--imagen", str(imagen),
                           "--salida", temp, "--amarillo", str(amarillo), "--modelo", resolver_tipo()]
                if umbral is not None:
                    comando += ["--umbral", str(umbral)]
                resultado = subprocess.run(
                    comando,
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, cwd=str(BASE_DIR),
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                if resultado.returncode:
                    error = (resultado.stderr or resultado.stdout)[-2000:].strip()
                    self._send_json(422, {"estado": "error", "error": "No se completó la inferencia CNN. " + error})
                    return
                geojson = json.loads((Path(temp)/"buildings.geojson").read_text(encoding="utf-8"))
                manifest = json.loads((Path(temp)/"manifest.json").read_text(encoding="utf-8"))
                if manifest.get("estado") != "completado" or manifest.get("count") != len(geojson["features"]):
                    raise ValueError("La salida del detector está incompleta.")
                manifest["outputs"] = {"buildings": "/outputs/detection/buildings.geojson"}
                (Path(temp)/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                for nombre in ("buildings.geojson", "manifest.json"):
                    destino = OUTPUTS_DIR / nombre
                    staging = destino.with_suffix(destino.suffix + ".tmp")
                    shutil.copyfile(Path(temp)/nombre, staging)
                    staging.replace(destino)
                self._send_json(200, {"estado": "completado", "salida": "/outputs/detection", "manifest": manifest,
                                      "geojson": "/outputs/detection/buildings.geojson"})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"estado": "error", "error": "La CNN superó 15 minutos; se conserva la detección anterior."})
        finally:
            DETECTION_LOCK.release()

    def _status(self):
        from backend.raster import validar_imagen
        try:
            modelo = describir()
        except ValueError as exc:
            modelo = {"nombre": "Desconocido", "error": str(exc), "dependencias": []}
        faltantes = [m for m in modelo["dependencias"] if importlib.util.find_spec(m) is None]
        imagen, error = None, None
        try:
            imagen = validar_imagen(DEFAULT_IMAGE)
        except Exception as exc:
            error = str(exc)
        if faltantes:
            error = "Faltan dependencias: " + ", ".join(faltantes)
        elif modelo["error"]:
            error = modelo["error"]
        manifest = None
        manifest_path = OUTPUTS_DIR / "manifest.json"
        if manifest_path.is_file() and (OUTPUTS_DIR/"buildings.geojson").is_file():
            candidato = json.loads(manifest_path.read_text(encoding="utf-8"))
            if candidato.get("estado") == "completado" and candidato.get("zonas", {}).get("geometria") == "corredor_entre_limites":
                manifest = candidato
        self._send_json(200, {"servidor": "chullo-unificado", "puerto": self.server.server_address[1],
                              "cnn_disponible": error is None and os.getenv("CHULLO_ENABLE_DETECTION", "1") == "1", "error": error, "imagen": imagen,
                              "modelo": modelo["nombre"], "manifest": manifest,
                              "detecciones_disponibles": ["buildings.geojson"] if manifest else []})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=int(os.getenv("PORT", "4173")))
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--abrir", action="store_true")
    args = parser.parse_args()
    try:
        servidor = ServidorLocal((args.host, args.puerto), partial(Archivos, directory=str(WEB_DIR)))
    except OSError as exc:
        parser.exit(1, f"No se pudo abrir el puerto {args.puerto}: {exc}. Cierra la instancia anterior o usa --puerto 4174.\n")
    url = f"http://127.0.0.1:{args.puerto}/"
    print(f"Chullo Unificado disponible en {url}", flush=True)
    if args.abrir:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()

if __name__ == "__main__":
    main()
