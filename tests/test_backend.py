"""Regresiones de geometría, máscaras CNN y publicación HTTP."""
import json
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import urllib.request
import urllib.error

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely import transform as _transform
def transform(fn, geom):
    return _transform(geom, fn, interleaved=False)

from backend.spatial import (calcular_linea_cauce_desde_limites, clasificar_distancia,
                             construir_zonas, evaluar_edificio, generar_poligonos_banda)
import servidor

BASE = Path(__file__).resolve().parents[1]

@pytest.fixture
def limites():
    a_wgs = Transformer.from_crs(32719, 4326, always_xy=True).transform
    # El corredor cambia de ancho; un buffer de 4 m del eje no lo cubre.
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"bank": bank}, "geometry": mapping(transform(a_wgs, LineString(coords)))}
        for bank, coords in [("Derecha", [(227200,8187000),(227210,8187050),(227200,8187100)]),
                             ("Izquierda", [(227240,8187000),(227270,8187050),(227240,8187100)])]]}

@pytest.mark.parametrize("distancia,esperado", [(0,"rojo"),(4,"rojo"),(4.001,"amarillo"),(24,"amarillo"),(24.01,"verde"),(None,"desconocido"),(-1,"desconocido"),(float('nan'),"desconocido")])
def test_clasificador_legado(distancia, esperado):
    assert clasificar_distancia(distancia,4,20).clase == esperado


def test_cauce_abierto_y_ultimo_vertice(limites):
    linea = calcular_linea_cauce_desde_limites(limites)
    assert len(linea.coords) == 3
    assert linea.coords[-1] != linea.coords[0]
    assert not linea.is_ring
    assert calcular_linea_cauce_desde_limites(None) is None


def test_particion_cauce_y_dos_fajas_sin_ampliacion(limites):
    zonas = construir_zonas(limites)
    bandas = generar_poligonos_banda(limites)
    rojo = transform(zonas['a_m'], shape(bandas['rojo']['geometry']))
    naranja = transform(zonas['a_m'], shape(bandas['naranja']['geometry']))
    assert rojo.is_valid and naranja.is_valid
    assert rojo.intersection(naranja).area < 1e-5
    assert rojo.union(naranja).symmetric_difference(zonas['corredor']).area < 1e-5
    for f in limites['features']:
        margen = transform(zonas['a_m'], shape(f['geometry']))
        assert margen.difference(naranja.buffer(1e-6)).is_empty
    assert rojo.covers(Point(227240,8187050))
    assert zonas['faja_derecha'].area > 0 and zonas['faja_izquierda'].area > 0
    assert bandas['metadata']['separacion_interior'].startswith('aproximada')


def test_direccion_invertida(limites):
    antes = construir_zonas(limites)
    limites['features'][1]['geometry']['coordinates'] = list(reversed(limites['features'][1]['geometry']['coordinates']))
    despues = construir_zonas(limites)
    assert antes['rojo'].equals(despues['rojo'])
    assert antes['naranja'].equals(despues['naranja'])


@pytest.mark.parametrize('ancho',[-1,20,501,float('nan'),float('inf')])
def test_rechazar_zona_amarilla_retirada(limites, ancho):
    with pytest.raises(ValueError):
        construir_zonas(limites,ancho)


def test_clasifica_contorno_y_prioridad_roja(limites):
    zonas = construir_zonas(limites)
    assert evaluar_edificio(box(227230,8187040,227250,8187060),zonas)['clase'] == 'rojo'
    assert evaluar_edificio(box(227268,8187049,227269,8187051),zonas)['clase'] == 'naranja'
    assert evaluar_edificio(box(227280,8187049,227290,8187051),zonas)['clase'] == 'verde'
    assert evaluar_edificio(box(227260,8187049,227300,8187051),zonas)['clase'] == 'rojo'


def test_cruce_huella_sin_distancia_fija_y_prioridad(limites):
    a_wgs = Transformer.from_crs(32719, 4326, always_xy=True).transform
    huella = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(transform(a_wgs, box(227260,8187040,227300,8187060)))}],
    }
    zonas = construir_zonas(limites, huella_huaico=huella)
    solo_huella = box(227280,8187049,227290,8187051)
    assert zonas['exterior'].covers(solo_huella)
    assert evaluar_edificio(solo_huella, zonas)['clase'] == 'amarillo'
    assert evaluar_edificio(box(227268,8187049,227282,8187051), zonas)['clase'] == 'naranja'
    assert evaluar_edificio(box(227260,8187049,227282,8187051), zonas)['clase'] == 'rojo'
    assert evaluar_edificio(box(227305,8187049,227310,8187051), zonas)['clase'] == 'verde'


def test_limites_reales_y_fajas_conservan_corredor():
    limites = json.loads((BASE/'web/layers/limites-faja-cayma.geojson').read_text())
    zonas = construir_zonas(limites)
    rojo, naranja = zonas['rojo'], zonas['naranja']
    assert rojo.is_valid and naranja.is_valid
    assert rojo.intersection(naranja).area < 1e-6
    assert rojo.union(naranja).symmetric_difference(zonas['corredor']).area < 1e-6
    assert len(calcular_linea_cauce_desde_limites(limites).coords) == 105
    for f in limites['features']:
        margen = transform(zonas['a_m'],shape(f['geometry']))
        assert margen.difference(naranja.buffer(1e-6)).is_empty
    assert 'amarillo' not in generar_poligonos_banda(limites)


def test_vertices_publicados_copian_las_210_coordenadas_documentales():
    limites = json.loads((BASE/'web/layers/limites-faja-cayma.geojson').read_text(encoding='utf-8'))
    vertices = json.loads((BASE/'web/layers/vertices-limites-cayma.geojson').read_text(encoding='utf-8'))
    assert len(vertices['features']) == vertices['metadata']['count'] == 210
    assert len({f['id'] for f in vertices['features']}) == 210
    for linea in limites['features']:
        bank = linea['properties']['bank']
        puntos = sorted((f for f in vertices['features'] if f['properties']['bank'] == bank),
                        key=lambda f: f['properties']['position'])
        assert len(puntos) == len(linea['geometry']['coordinates']) == 105
        assert [f['properties']['position'] for f in puntos] == list(range(1, 106))
        assert [f['geometry']['coordinates'] for f in puntos] == linea['geometry']['coordinates']
        assert all(f['geometry']['type'] == 'Point' and
                   f['properties']['role'] == 'documentary_outer_limit_vertex' for f in puntos)

@pytest.fixture
def imagen(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    path = tmp_path/'rgb.tif'
    with rasterio.open(path,'w',driver='GTiff',width=32,height=32,count=3,dtype='uint8',crs='EPSG:32719',transform=from_origin(227220,8187070,1,1)) as dst:
        dst.write(np.full((3,32,32),128,dtype='uint8'))
    return path


def test_mascara_geometria_preserva_huecos():
    from backend.detector import mascara_a_geometria
    from rasterio.transform import from_origin
    mascara = np.ones((10,10),dtype='uint8')
    mascara[3:7,3:7] = 0
    geom = mascara_a_geometria(mascara,from_origin(0,10,1,1))
    assert geom.area == 84
    assert len(geom.interiors) == 1

@pytest.mark.parametrize('hay_detecciones',[True,False])
def test_pipeline_rgb_mascara_2d_y_salida_vacia(tmp_path, monkeypatch, imagen, limites, hay_detecciones):
    import torch
    from backend import detector
    limites_path = tmp_path/'limites.geojson'
    limites_path.write_text(json.dumps(limites))
    def modelo(tensores):
        assert tensores[0].shape == (3,32,32)
        mask = torch.zeros((1,1,32,32))
        mask[0,0,8:20,8:20] = 1
        return [{'scores': torch.tensor([0.9 if hay_detecciones else 0.1]),'labels':torch.tensor([1]),'masks':mask}]
    monkeypatch.setattr(detector,'cargar_modelo',lambda dispositivo: (modelo,'cpu'))
    output = tmp_path/'salida'
    manifest = detector.detectar_edificios(imagen,output,tamano_mosaico=32,solapamiento=0,limites_path=limites_path,modelo='maskrcnn')
    features = json.loads((output/'buildings.geojson').read_text())['features']
    assert manifest['count'] == len(features) == int(hay_detecciones)
    if features:
        assert features[0]['properties']['clase'] == 'rojo'
        assert shape(features[0]['geometry']).is_valid


def test_rechaza_png_renombrado(tmp_path):
    from PIL import Image
    from backend.raster import validar_imagen
    path = tmp_path/'falso.tif'
    Image.new('RGB',(20,20)).save(path,format='PNG')
    with pytest.raises(ValueError,match='GeoTIFF'):
        validar_imagen(path)

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor,'OUTPUTS_DIR',tmp_path/'detection')
    server = servidor.ServidorLocal(('127.0.0.1',0),partial(servidor.Archivos,directory=str(BASE/'web')))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()


def test_no_permite_dos_servidores_en_el_mismo_puerto(api):
    from urllib.parse import urlparse
    with pytest.raises(OSError):
        servidor.ServidorLocal(('127.0.0.1',urlparse(api).port),servidor.Archivos)


def test_api_bandas_reales_e_inputs_invalidos(api):
    with urllib.request.urlopen(api+'/api/bands?amarillo=0') as r:
        data = json.load(r)
    assert [f['properties']['clase'] for f in data['features']] == ['naranja','rojo','cauce','amarillo']
    assert data['metadata']['distrito'] == 'Cayma'
    capas = BASE / 'web/layers'
    distrito = shape(json.loads((capas / 'distrito-cayma.geojson').read_text(encoding='utf-8'))['geometry'])
    huella = json.loads((capas / 'huella-huaico-chullo-a7270.geojson').read_text(encoding='utf-8'))
    amarillo = next(shape(f['geometry']) for f in data['features'] if f['properties']['clase'] == 'amarillo')
    assert all(distrito.buffer(1e-7).covers(shape(f['geometry'])) for f in data['features'])
    assert all(shape(f['geometry']).intersection(distrito).difference(amarillo.buffer(1e-7)).area < 1e-12
               for f in huella['features'])
    for query in ('nan','-1','abc'):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(api+'/api/bands?amarillo='+query)
        assert exc.value.code == 400


def test_error_no_es_exito_y_conserva_detecciones(api):
    servidor.OUTPUTS_DIR.mkdir()
    path = servidor.OUTPUTS_DIR/'buildings.geojson'
    path.write_text('resultado previo')
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(api+'/api/detect?imagen=no-existe.tif')
    assert exc.value.code == 400
    assert json.load(exc.value)['estado'] == 'error'
    assert path.read_text() == 'resultado previo'


def test_api_publica_resultado_en_ruta_servida(api, imagen, monkeypatch):
    def simular_subprocess(cmd,**kwargs):
        output = Path(cmd[cmd.index('--salida')+1])
        (output/'buildings.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[]}))
        (output/'manifest.json').write_text(json.dumps({'estado':'completado','count':0}))
        return type('Resultado',(),{'returncode':0})()
    monkeypatch.setattr(servidor.subprocess,'run',simular_subprocess)
    with urllib.request.urlopen(api+'/api/detect?imagen='+str(imagen).replace('\\','/')) as r:
        resultado = json.load(r)
    assert resultado['geojson'] == '/outputs/detection/buildings.geojson'
    assert json.loads((servidor.OUTPUTS_DIR/'buildings.geojson').read_text())['features'] == []


def test_fallo_de_subproceso_no_sobrescribe(api, imagen, monkeypatch):
    servidor.OUTPUTS_DIR.mkdir()
    path = servidor.OUTPUTS_DIR/'buildings.geojson'
    path.write_text('anterior')
    monkeypatch.setattr(servidor.subprocess,'run',lambda *a,**k: type('Fallo',(),{'returncode':1,'stderr':'ERROR de prueba','stdout':''})())
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(api+'/api/detect?imagen='+str(imagen).replace('\\','/'))
    assert exc.value.code == 422
    assert path.read_text() == 'anterior'


def test_servidor_publico_restringe_imagen(api, imagen, monkeypatch):
    monkeypatch.setenv('CHULLO_PUBLIC','1')
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(api+'/api/detect?imagen='+str(imagen).replace('\\','/'))
    assert exc.value.code == 400
    assert 'solo analiza' in json.load(exc.value)['error']


def test_inferencia_desactivada_en_servidor(api, monkeypatch):
    monkeypatch.setenv('CHULLO_ENABLE_DETECTION','0')
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(api+'/api/detect')
    assert exc.value.code == 403
    with urllib.request.urlopen(api+'/api/status') as r:
        assert json.load(r)['cnn_disponible'] is False


def test_etiquetas_guardadas_en_utf8():
    from backend.spatial import ETIQUETAS
    data=json.loads((BASE/'web/outputs/detection/buildings.geojson').read_text(encoding='utf-8'))
    for f in data['features']:
        p=f['properties']
        assert p['etiqueta']==ETIQUETAS[p['clase']]
        assert p['review_status']=='Sin revisión manual · inferencia IA'
    manifest=json.loads((BASE/'web/outputs/detection/manifest.json').read_text(encoding='utf-8'))
    assert manifest['limitaciones'][0]=='Detecciones automáticas sin revisión humana.'
