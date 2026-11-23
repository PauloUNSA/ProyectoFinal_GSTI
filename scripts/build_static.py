"""Genera el visor público sin Python ni PyTorch en el servidor de destino."""
import json
import shutil
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from servidor import leer_bandas

def build():
    destino=BASE/'dist'
    # Directorio fijo del proyecto, nunca un destino aportado por el usuario.
    if destino.exists():
        if destino.resolve().parent != BASE.resolve():
            raise ValueError('Destino fuera del proyecto')
        shutil.rmtree(destino)
    shutil.copytree(BASE/'web',destino)
    p=destino/'index.html'
    p.write_text(p.read_text(encoding='utf-8').replace('<script src="vendor/leaflet.js">','<script>window.CHULLO_STATIC = true;</script>\n<script src="vendor/leaflet.js">'),encoding='utf-8')
    (destino/'layers/bandas-proximidad.geojson').write_text(json.dumps(leer_bandas(0),ensure_ascii=False),encoding='utf-8')
    (destino/'.nojekyll').touch()
    # Los datos públicos no necesitan rutas locales de la máquina que infirió.
    p=destino/'outputs/detection/manifest.json';m=json.loads(p.read_text(encoding='utf-8'))
    m['imagen']='chullo_rgb.tif';m.get('cobertura',{}).pop('path',None)
    p.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Visor estático preparado: {destino}')
if __name__=='__main__':build()
