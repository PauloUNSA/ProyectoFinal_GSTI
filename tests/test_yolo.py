"""Flujo YOLO: celdas, conversión de etiquetas, elección de modelo e inferencia."""
import json
from functools import partial
from pathlib import Path
import threading
import urllib.request

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, box, mapping, shape
from shapely import transform as _transform

from backend import dataset_yolo, modelos

BASE = Path(__file__).resolve().parents[1]
A_WGS = Transformer.from_crs(32719, 4326, always_xy=True).transform


def wgs(geom):
    return _transform(geom, A_WGS, interleaved=False)


@pytest.fixture
def raster(tmp_path):
    """64×64 px a 1 m; origen superior izquierdo en (227200, 8187064)."""
    import rasterio
    from rasterio.transform import from_origin
    path = tmp_path / "rgb.tif"
    datos = np.zeros((3, 64, 64), dtype="uint8")
    datos[0, :, :32] = 200  # mitad izquierda roja: permite verificar el recorte
    with rasterio.open(path, "w", driver="GTiff", width=64, height=64, count=3, dtype="uint8",
                       crs="EPSG:32719", transform=from_origin(227200, 8187064, 1, 1)) as dst:
        dst.write(datos)
    return path


@pytest.fixture
def anotacion(tmp_path, raster):
    """Cuatro celdas de 32 px; la zona solo toca las dos de la izquierda."""
    import rasterio
    zona = box(227200, 8187000, 227220, 8187064)
    with rasterio.open(raster) as src:
        celdas = dataset_yolo.generar_celdas(src, zona, LineString([(227210, 8187064), (227210, 8187000)]), tamano_px=32)
    assert [(c["col_off"], c["row_off"]) for c in celdas] == [(0, 0), (0, 32)]
    data = dataset_yolo.celdas_a_geojson(celdas, 32, {})
    for f, split in zip(data["features"], ("train", "val")):
        f["properties"].update(split=split, estado="completa")
    celdas_path = tmp_path / "celdas.geojson"
    celdas_path.write_text(json.dumps(data))
    # Techo de 8×4 m en la celda superior (píxeles x 4–12, y 10–14) y otro que cruza su borde derecho.
    techos = [box(227204, 8187050, 227212, 8187054), box(227228, 8187040, 227236, 8187044)]
    techos_path = tmp_path / "techos.geojson"
    techos_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(wgs(t))} for t in techos]}))
    return celdas_path, techos_path


def test_poligono_recortado_y_normalizado():
    lineas = dataset_yolo.poligono_a_linea_yolo(box(-5, 2, 10, 6), 20, 20)
    valores = np.array(lineas[0].split()[1:], dtype=float).reshape(-1, 2)
    assert lineas[0].startswith("0 ")
    assert valores.min() >= 0 and valores.max() <= 1
    assert np.isclose(valores[:, 0].min(), 0) and np.isclose(valores[:, 0].max(), 0.5)
    assert dataset_yolo.poligono_a_linea_yolo(box(0, 0, 2, 2), 20, 20) == []  # 4 px² < 8
    assert dataset_yolo.poligono_a_linea_yolo(box(30, 30, 40, 40), 20, 20) == []


def test_split_estable_por_bloques_del_cauce():
    splits = [dataset_yolo.CICLO_SPLITS[(i // dataset_yolo.BLOQUE_CELDAS) % 5] for i in range(15)]
    assert splits == ["train"] * 9 + ["val"] * 3 + ["test"] * 3


def test_armar_dataset_georreferencia_y_celdas(tmp_path, raster, anotacion):
    celdas_path, techos_path = anotacion
    resumen = dataset_yolo.armar_dataset(raster, celdas_path, techos_path, tmp_path / "ds", desplazados=False)
    entero, cortado = sorted((np.array(l.split()[1:], dtype=float).reshape(-1, 2) * 32
                              for l in (tmp_path / "ds/labels/train/c000.txt").read_text().splitlines()),
                             key=lambda xy: xy[:, 0].min())
    assert np.allclose(entero.min(0), [4, 10], atol=1e-3) and np.allclose(entero.max(0), [12, 14], atol=1e-3)
    # El techo que cruza el borde se recorta a la celda (x 28–32 px).
    assert np.allclose(cortado.min(0), [28, 20], atol=1e-3) and np.allclose(cortado.max(0), [32, 24], atol=1e-3)
    from PIL import Image
    png = np.asarray(Image.open(tmp_path / "ds/images/train/c000.png"))
    assert png.shape == (32, 32, 3) and png[0, 0, 0] == 200
    assert (tmp_path / "ds/labels/val/c001.txt").read_text() == ""  # celda sin techos: negativo válido
    assert resumen["splits"]["train"]["techos"] == 2 and resumen["splits"]["test"]["celdas"] == 0
    assert any("test" in a for a in resumen["avisos"])
    yaml = (tmp_path / "ds/data.yaml").read_text()
    assert "train: images/train" in yaml and "0: techo" in yaml


def test_solo_usa_celdas_completas_y_detecta_imagen_equivocada(tmp_path, raster, anotacion):
    celdas_path, techos_path = anotacion
    data = json.loads(celdas_path.read_text())
    data["features"][0]["properties"]["estado"] = "pendiente"
    celdas_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="celdas train"):
        dataset_yolo.armar_dataset(raster, celdas_path, techos_path, tmp_path / "ds")
    data["features"][0]["properties"].update(estado="completa", col_off=32)
    celdas_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="no coincide"):
        dataset_yolo.armar_dataset(raster, celdas_path, techos_path, tmp_path / "ds")


def test_no_borra_carpetas_ajenas(tmp_path, raster, anotacion):
    ajena = tmp_path / "importante"
    ajena.mkdir()
    (ajena / "nota.txt").write_text("no borrar")
    with pytest.raises(ValueError, match="no parece"):
        dataset_yolo.armar_dataset(raster, *anotacion, ajena)
    assert (ajena / "nota.txt").exists()


def test_borrador_marca_techos_sin_editar(tmp_path, raster):
    import rasterio
    with rasterio.open(raster) as src:
        celdas = dataset_yolo.generar_celdas(src, box(227200, 8187000, 227264, 8187064), LineString([(227200, 8187064), (227264, 8187000)]), tamano_px=32)
    techo = wgs(box(227204, 8187050, 227212, 8187054))
    borrador, conteo = dataset_yolo.borrador_desde_detecciones(
        {"features": [{"geometry": mapping(techo), "properties": {"confidence": 0.8}}]}, celdas)
    assert sum(conteo.values()) == 1
    editado = json.loads(json.dumps(borrador))
    editado["features"].append(json.loads(json.dumps(borrador["features"][0])))
    editado["features"][1]["geometry"] = mapping(wgs(box(227204, 8187050, 227213, 8187054)))
    path = tmp_path / "techos.geojson"
    path.write_text(json.dumps(editado))
    assert [t["sin_modificar"] for t in dataset_yolo.leer_techos(path, "EPSG:32719")] == [True, False]


def test_comparacion_empareja_por_iou_una_sola_vez():
    import importlib.util
    spec = importlib.util.spec_from_file_location("comparar", BASE / "scripts/comparar_modelos.py")
    comparar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparar)
    ref = [np.zeros((10, 10), bool) for _ in range(2)]
    ref[0][0:4, 0:4] = True
    ref[1][6:10, 6:10] = True
    union = np.ones((10, 10), bool)  # una mancha que une ambos techos no acierta ninguno
    casi = np.zeros((10, 10), bool)
    casi[0:4, 0:3] = True    # IoU 0.75 con el primero; el duplicado no cuenta dos veces
    pred, refs = comparar.emparejar([union, casi, casi.copy()], ref)
    assert len(pred) == 1 and pred <= {1, 2} and refs == {0}
    m = comparar.metricas(3, 2, len(pred))
    assert (m["aciertos"], m["falsos_positivos"], m["omitidos"]) == (1, 2, 1)
    assert m["f1"] == pytest.approx(2 * (1 / 3) * 0.5 / (1 / 3 + 0.5))


def test_zonas_de_prueba_en_utm_local_y_fuera_de_la_torrentera():
    import importlib.util
    import rasterio
    from rasterio.warp import transform_bounds
    from shapely.geometry import Point
    spec = importlib.util.spec_from_file_location("probar", BASE / "scripts/probar_otras_zonas.py")
    probar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probar)
    assert probar.epsg_utm(-16.4, -71.5) == 32719
    assert probar.epsg_utm(40.38, -3.73) == 32630
    assert probar.epsg_utm(30.05, 31.24) == 32636
    with rasterio.open(BASE / "data/imagery/chullo/chullo_rgb.tif") as src:
        torrentera = box(*transform_bounds(src.crs, "EPSG:4326", *src.bounds))
    zonas = json.loads((BASE / "config/zonas_prueba.json").read_text(encoding="utf-8"))["zonas"]
    assert len({z["id"] for z in zonas}) == len(zonas) == 20
    assert not any(Point(z["lon"], z["lat"]).buffer(0.0025).intersects(torrentera) for z in zonas)


def test_metrica_de_area_tolera_techos_unidos():
    import importlib.util
    spec = importlib.util.spec_from_file_location("comparar", BASE / "scripts/comparar_modelos.py")
    comparar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comparar)
    ref = [np.zeros((12, 12), bool) for _ in range(3)]
    for k in range(3):
        ref[k][0:4, 4 * k:4 * k + 4] = True
    unido = ref[0] | ref[1] | ref[2]  # un solo contorno sobre tres techos vecinos (IoU 1/3 con cada uno)
    assert comparar.emparejar([unido], ref) == (set(), set())  # por techo: cero aciertos
    area = comparar.metricas_area(*comparar.pixeles_area([unido], ref, 12))
    assert area["f1_area"] == 1.0 and area["area_referencia_m2"] == 48 * 0.25


def test_alineacion_recupera_corrimiento_y_limpieza():
    from affine import Affine
    from shapely import affinity
    from backend import huellas
    rgb = np.zeros((200, 200, 3), dtype=np.uint8)
    techos = []
    for k in range(30):
        x, y = 10 + (k % 6) * 30, 10 + (k // 6) * 36
        rgb[y:y + 14, x:x + 18] = 220
        techos.append(box(x, -y - 14, x + 18, -y))  # metros = píxeles, norte arriba
    transform = Affine(1, 0, 0, 0, -1, 0)
    corridas = [affinity.translate(t, 3, 2) for t in techos]  # 3 px a la derecha y 2 px hacia arriba
    nuevas, registro = huellas.alinear(rgb, transform, corridas, ["overture:X"] * 30)
    assert (registro[0]["dx_px"], registro[0]["dy_px"]) == (-3, 2) and registro[0]["aplicado"]
    assert nuevas[0].equals_exact(techos[0], 1e-9)
    conservados, descartes = huellas.limpiar([box(0, 0, 2, 2), box(0, 0, 10, 10), box(0, 0, 50, 50)])
    assert conservados == [1] and descartes == {"diminuta": 1, "lote_o_manzana": 1}


def test_huellas_grandes_se_ignoran_en_gris(tmp_path, raster, anotacion):
    celdas_path, techos_path = anotacion
    data = json.loads(techos_path.read_text())
    data["features"][0]["properties"]["ignorar"] = True
    techos_path.write_text(json.dumps(data))
    resumen = dataset_yolo.armar_dataset(raster, celdas_path, techos_path, tmp_path / "ds", desplazados=False)
    from PIL import Image
    png = np.asarray(Image.open(tmp_path / "ds/images/train/c000.png"))
    assert (png[11, 6] == 114).all()  # dentro del techo ignorado
    assert resumen["splits"]["train"]["techos"] == 1


def test_resolver_modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("CHULLO_YOLO_DIR", str(tmp_path))
    monkeypatch.delenv("CHULLO_MODELO", raising=False)
    assert modelos.resolver_tipo() == "maskrcnn"
    assert modelos.parametros_mosaico("maskrcnn") == (512, 128) and modelos.umbral_por_defecto("maskrcnn") == 0.5
    assert modelos.describir("yolo")["error"]
    (tmp_path / "manifest.json").write_text(json.dumps({"id": "x", "filename": "weights.pt", "sha256": "0", "tile_px": 320, "umbral_recomendado": 0.35}))
    assert modelos.resolver_tipo() == "yolo"
    assert modelos.parametros_mosaico("yolo") == (320, 80) and modelos.umbral_por_defecto("yolo") == 0.35
    assert "Faltan los pesos" in modelos.describir()["error"]
    monkeypatch.setenv("CHULLO_MODELO", "maskrcnn")
    assert modelos.resolver_tipo() == "maskrcnn"
    with pytest.raises(ValueError):
        modelos.resolver_tipo("resnet")


def test_detector_yolo_usa_mosaico_y_datos_del_modelo(tmp_path, monkeypatch):
    import rasterio
    from rasterio.transform import from_origin
    from backend import detector
    limites = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"bank": bank}, "geometry": mapping(wgs(LineString(coords)))}
        for bank, coords in [("Derecha", [(227200, 8187000), (227210, 8187050), (227200, 8187100)]),
                             ("Izquierda", [(227240, 8187000), (227270, 8187050), (227240, 8187100)])]]}
    (tmp_path / "limites.geojson").write_text(json.dumps(limites))
    imagen = tmp_path / "rgb.tif"
    with rasterio.open(imagen, "w", driver="GTiff", width=64, height=64, count=3, dtype="uint8",
                       crs="EPSG:32719", transform=from_origin(227210, 8187082, 1, 1)) as dst:
        dst.write(np.full((3, 64, 64), 90, dtype="uint8"))
    monkeypatch.setenv("CHULLO_YOLO_DIR", str(tmp_path))
    (tmp_path / "manifest.json").write_text(json.dumps({"id": "chullo/yolo_prueba", "filename": "weights.pt", "sha256": "abc",
                                                        "tile_px": 32, "imgsz": 64, "umbral_recomendado": 0.4}))
    vistos = []

    def falso_predictor(dispositivo, umbral):
        assert umbral == 0.4

        def predecir(datos):
            vistos.append(datos.shape)
            mascara = np.zeros((1,) + datos.shape[1:], dtype=bool)
            mascara[0, 4:20, 4:20] = True
            return np.array([0.9]), mascara
        return predecir, "cpu", {"id": "chullo/yolo_prueba", "sha256": "abc", "arquitectura": "Ultralytics prueba", "limitacion": "prueba"}

    monkeypatch.setattr(detector, "_predictor_yolo", falso_predictor)
    manifest = detector.detectar_edificios(imagen, tmp_path / "salida", limites_path=tmp_path / "limites.geojson")
    assert set(vistos) == {(3, 32, 32)}
    assert manifest["tamano_mosaico"] == 32 and manifest["solapamiento"] == 8
    assert manifest["modelo"] == "chullo/yolo_prueba" and manifest["umbral"] == 0.4 and manifest["count"] >= 1
    features = json.loads((tmp_path / "salida/buildings.geojson").read_text(encoding="utf-8"))["features"]
    assert {f["properties"]["model_id"] for f in features} == {"chullo/yolo_prueba"}
    assert "prueba" in manifest["limitaciones"]


def test_servidor_pasa_modelo_y_umbral_opcional(tmp_path, monkeypatch, raster):
    import servidor
    monkeypatch.setattr(servidor, "OUTPUTS_DIR", tmp_path / "detection")
    monkeypatch.setenv("CHULLO_MODELO", "maskrcnn")
    comandos = []

    def simular(cmd, **kwargs):
        comandos.append(cmd)
        salida = Path(cmd[cmd.index("--salida") + 1])
        (salida / "buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        (salida / "manifest.json").write_text(json.dumps({"estado": "completado", "count": 0}))
        return type("Resultado", (), {"returncode": 0})()

    monkeypatch.setattr(servidor.subprocess, "run", simular)
    server = servidor.ServidorLocal(("127.0.0.1", 0), partial(servidor.Archivos, directory=str(BASE / "web")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        imagen = str(raster).replace("\\", "/")
        urllib.request.urlopen(f"{url}/api/detect?imagen={imagen}").read()
        urllib.request.urlopen(f"{url}/api/detect?imagen={imagen}&umbral=0.3").read()
        with urllib.request.urlopen(url + "/api/status") as r:
            assert json.load(r)["modelo"] == "Mask R-CNN · Chullo local v1 (piloto)"
    finally:
        server.shutdown()
        server.server_close()
    assert "--umbral" not in comandos[0] and comandos[0][comandos[0].index("--modelo") + 1] == "maskrcnn"
    assert comandos[1][comandos[1].index("--umbral") + 1] == "0.3"
