"""Resuelve el checkpoint público cuando el checkout del proveedor contiene un puntero LFS."""
import hashlib
from pathlib import Path
import requests
BASE=Path(__file__).resolve().parents[1]
PATH=BASE/'models/chullo_local_v1/weights.pth'
SHA='dcc985d4b57ec6ab0c6dbc36bf48f8b6433bfe61e9d89faf2445bb7b05d5f61c'
URL='https://media.githubusercontent.com/media/PauloUNSA/ProyectoFinal_GSTI/ce45cd0c609d622d98b4d0d184d4404ce9cb7690/models/chullo_local_v1/weights.pth'
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ensure():
    if PATH.is_file() and digest(PATH)==SHA:return
    tmp=PATH.with_suffix('.download');PATH.parent.mkdir(parents=True,exist_ok=True)
    with requests.get(URL,stream=True,timeout=(30,300)) as r:
        r.raise_for_status()
        with tmp.open('wb') as out:
            for chunk in r.iter_content(1024*1024):out.write(chunk)
    if digest(tmp)!=SHA:
        tmp.unlink();raise ValueError('SHA256 del modelo incorrecto')
    tmp.replace(PATH)
if __name__=='__main__':ensure()
