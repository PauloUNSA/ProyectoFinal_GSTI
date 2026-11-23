"""Resuelve y verifica ambos checkpoints, también desde un checkout con punteros LFS."""
import hashlib
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
MEDIA = "https://media.githubusercontent.com/media/PauloUNSA/ProyectoFinal_GSTI"
CHECKPOINTS = (
    (
        BASE / "models/yolo26_chullo/weights.pt",
        "94c4c54a92365390f5ceb06ca7c238a7756bbecc0d15833df17e603f2c975e4b",
        f"{MEDIA}/8694d396ad0e8aa6e1cef7aea0045fef6168b568/models/yolo26_chullo/weights.pt",
    ),
    (
        BASE / "models/chullo_local_v1/weights.pth",
        "dcc985d4b57ec6ab0c6dbc36bf48f8b6433bfe61e9d89faf2445bb7b05d5f61c",
        f"{MEDIA}/ce45cd0c609d622d98b4d0d184d4404ce9cb7690/models/chullo_local_v1/weights.pth",
    ),
)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def ensure_checkpoint(path, sha256, url):
    if path.is_file() and digest(path) == sha256:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".download")
    try:
        with requests.get(url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
        if digest(temporary) != sha256:
            raise ValueError(f"SHA256 del modelo incorrecto: {path.name}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure():
    for checkpoint in CHECKPOINTS:
        ensure_checkpoint(*checkpoint)


if __name__ == "__main__":
    ensure()
