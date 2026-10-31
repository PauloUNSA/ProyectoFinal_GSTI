"""Servidor local de Chullo Unificado.

Sirve el visor web (HTML/CSS/JS/GeoJSON) y expone una API simple para
ejecutar la deteccion de edificios con CNN y generar franjas de proximidad.

Solo requiere Python 3 para el servidor base. La deteccion CNN requiere
instalar por separado torch, torchvision, rasterio, geopandas y shapely.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
BACKEND_DIR = BASE_DIR / "backend"
SCRIPTS_DIR = BASE_DIR / "scripts"
OUTPUTS_DIR = BASE_DIR / "outputs" / "detection"


class Archivos(SimpleHTTPRequestHandler):
    """Manejador de archivos estáticos con MIME types para GeoJSON y JS."""

    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".geojson": "application/geo+json",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".csv": "text/csv; charset=utf-8",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".pdf": "application/pdf",
        ".txt": "text/plain; charset=utf-8",
    }

    def list_directory(self, path):
        self.send_error(403, "Listado de carpetas deshabilitado")
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Rutas de la API
        if path.startswith("/api/"):
            self._handle_api(path, parsed.query)
            return

        # Servir archivos estáticos desde web/
        self.directory = str(WEB_DIR)
        # Ajustar la ruta relativa para servir desde web/
        if path == "/" or path == "":
            path = "/index.html"
        # Simular que el directorio raiz es web/
        translated = self.translate_path(path)
        # Forzar directorio base web/
        relative = Path(path).relative_to("/") if path.startswith("/") else Path(path)
        target = WEB_DIR / relative
        if not target.exists() and target.suffix == "":
            target = WEB_DIR / relative / "index.html"
        if target.exists() and target.is_file():
            self.path = str(relative)
            return super().do_GET()
        # Fallback: intentar servir normalmente desde WEB_DIR
        self.directory = str(WEB_DIR)
        return super().do_GET()

    def _handle_api(self, path: str, query: str):
        params = parse_qs(query)

        if path == "/api/detect":
            self._run_detection(params)
        elif path == "/api/bands":
            self._generate_bands(params)
        elif path == "/api/status":
            self._status(params)
        elif path == "/api/list":
            self._list_outputs(params)
        else:
            self._send_json(404, {"error": "Endpoint API no encontrado"})

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _run_detection(self, params: dict):
        """Ejecuta la deteccion CNN como subprocess."""
        imagen = params.get("imagen", [None])[0]
        salida = params.get("salida", [str(OUTPUTS_DIR)])[0]
        umbral = params.get("umbral", ["0.5"])[0]

        if not imagen:
            self._send_json(400, {"error": "Falta el parametro 'imagen'"})
            return

        script = SCRIPTS_DIR / "run_detection.py"
        if not script.exists():
            self._send_json(
                501,
                {
                    "error": "Script de deteccion no disponible",
                    "detalle": "scripts/run_detection.py no existe. La deteccion CNN es opcional.",
                },
            )
            return

        cmd = [
            sys.executable,
            str(script),
            "--imagen",
            imagen,
            "--salida",
            salida,
            "--umbral",
            umbral,
        ]

        try:
            resultado = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, cwd=str(BASE_DIR)
            )
            if resultado.returncode != 0:
                self._send_json(
                    500,
                    {
                        "error": "La deteccion fallo",
                        "stderr": resultado.stderr[-2000:] if resultado.stderr else "",
                        "stdout": resultado.stdout[-1000:] if resultado.stdout else "",
                    },
                )
                return

            manifest_path = Path(salida) / "manifest.json"
            manifest = {}
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self._send_json(
                200,
                {
                    "estado": "completado",
                    "mensaje": "Deteccion finalizada",
                    "salida": salida,
                    "manifest": manifest,
                },
            )
        except subprocess.TimeoutExpired:
            self._send_json(504, {"error": "Tiempo de espera agotado en la deteccion"})
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc)})

    def _generate_bands(self, params: dict):
        """Genera poligonos de franjas de proximidad desde los limites de faja."""
        rojo = float(params.get("rojo", ["25"])[0])
        amarillo = float(params.get("amarillo", ["25"])[0])

        script = SCRIPTS_DIR / "generate_bands.py"
        if not script.exists():
            # Generacion simple en el servidor sin dependencias externas
            self._send_json(
                200,
                {
                    "estado": "ok",
                    "mensaje": "Usa el visor para calcular franjas localmente (bands.js)",
                    "rojo_m": rojo,
                    "amarillo_m": amarillo,
                    "limite_exterior_m": rojo + amarillo,
                },
            )
            return

        try:
            resultado = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--rojo",
                    str(rojo),
                    "--amarillo",
                    str(amarillo),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(BASE_DIR),
            )
            if resultado.returncode != 0:
                self._send_json(500, {"error": resultado.stderr[-2000:]})
                return
            self._send_json(
                200,
                {"estado": "completado", "salida": resultado.stdout.strip()},
            )
        except Exception as exc:  # noqa: BLE001
            self._send_json(500, {"error": str(exc)})

    def _status(self, params: dict):
        """Estado del servidor y disponibilidad de deteccion."""
        tiene_torch = False
        try:
            import torch  # noqa: F401

            tiene_torch = True
        except ImportError:
            pass

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        detecciones = []
        if OUTPUTS_DIR.exists():
            for f in sorted(OUTPUTS_DIR.iterdir()):
                if f.suffix == ".geojson":
                    detecciones.append(f.name)

        self._send_json(
            200,
            {
                "servidor": "chullo-unificado",
                "puerto": getattr(self.server, "server_address", ("", 0))[1],
                "cnn_disponible": tiene_torch,
                "detecciones_disponibles": detecciones,
                "web_dir": str(WEB_DIR),
            },
        )

    def _list_outputs(self, params: dict):
        """Lista archivos de salida de deteccion."""
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        archivos = []
        for f in sorted(OUTPUTS_DIR.iterdir()):
            archivos.append(
                {
                    "nombre": f.name,
                    "tipo": f.suffix.lstrip("."),
                    "tamano": f.stat().st_size,
                }
            )
        self._send_json(200, {"archivos": archivos})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=4173)
    parser.add_argument("--abrir", action="store_true", help="Abrir en el navegador")
    args = parser.parse_args()

    if not (WEB_DIR / "index.html").is_file():
        parser.exit(1, "Falta web/index.html. Verifica que la carpeta web/ este completa.\n")

    url = f"http://127.0.0.1:{args.puerto}/"
    try:
        servidor = ThreadingHTTPServer(
            ("127.0.0.1", args.puerto), partial(Archivos, directory=str(WEB_DIR))
        )
    except OSError as error:
        parser.exit(
            1,
            f"No se pudo iniciar el servidor: {error}\n"
            f"Prueba otro puerto: python servidor.py --puerto 4174 --abrir\n",
        )

    print(f"Chullo Unificado disponible en {url}", flush=True)
    print("Solo en este equipo. Para detener: Ctrl+C.", flush=True)
    print(f"API: {url}api/status", flush=True)
    print(f"Visor: {url}", flush=True)

    if args.abrir:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
