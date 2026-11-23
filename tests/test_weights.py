"""Resolución LFS: aceptar checkpoints íntegros y conservar el anterior al fallar."""
import hashlib
import json

import pytest

from scripts import ensure_weights


class Response:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.content[:3]
        yield self.content[3:]


def test_modelos_fijados_coinciden_con_sus_manifiestos():
    for path, sha256, url in ensure_weights.CHECKPOINTS:
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        assert path.name == manifest["filename"]
        assert sha256 == manifest["sha256"]
        assert "/main/" not in url


def test_modelo_integro_no_requiere_red(tmp_path, monkeypatch):
    path = tmp_path / "weights.pt"
    path.write_bytes(b"modelo integro")
    monkeypatch.setattr(ensure_weights.requests, "get", lambda *a, **k: pytest.fail("No debe descargar"))
    ensure_weights.ensure_checkpoint(path, ensure_weights.digest(path), "https://invalid.test/model")


@pytest.mark.parametrize("initial", [None, b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\n"])
def test_descarga_y_verifica_peso_ausente_o_puntero_lfs(tmp_path, monkeypatch, initial):
    path = tmp_path / "weights.pt"
    if initial is not None:
        path.write_bytes(initial)
    expected = b"checkpoint binario verificado"
    monkeypatch.setattr(ensure_weights.requests, "get", lambda *a, **k: Response(expected))
    ensure_weights.ensure_checkpoint(path, hashlib.sha256(expected).hexdigest(), "https://invalid.test/model")
    assert path.read_bytes() == expected
    assert not path.with_suffix(".pt.download").exists()


def test_descarga_corrupta_conserva_anterior_y_limpia_temporal(tmp_path, monkeypatch):
    path = tmp_path / "weights.pt"
    path.write_bytes(b"anterior")
    monkeypatch.setattr(ensure_weights.requests, "get", lambda *a, **k: Response(b"corrupto"))
    with pytest.raises(ValueError, match="SHA256"):
        ensure_weights.ensure_checkpoint(path, "0" * 64, "https://invalid.test/model")
    assert path.read_bytes() == b"anterior"
    assert not path.with_suffix(".pt.download").exists()


def test_ensure_resuelve_todos_los_checkpoints(tmp_path, monkeypatch):
    contenido = b"checkpoint"
    sha256 = hashlib.sha256(contenido).hexdigest()
    paths = [tmp_path / "yolo/weights.pt", tmp_path / "maskrcnn/weights.pth"]
    monkeypatch.setattr(ensure_weights, "CHECKPOINTS", tuple((p, sha256, "https://invalid.test/model") for p in paths))
    monkeypatch.setattr(ensure_weights.requests, "get", lambda *a, **k: Response(contenido))
    ensure_weights.ensure()
    assert all(p.read_bytes() == contenido for p in paths)
