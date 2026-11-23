"""Digitalización visual reproducible del anexo 4 (PDF 67) del A7270.

Los pares exteriores se leyeron sobre la imagen nativa de 947 × 1340 px.
Las coordenadas son píxeles de imagen (origen arriba a la izquierda).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from pypdf import PdfReader
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Polygon, mapping, shape

REPO = Path(__file__).resolve().parents[1]
SHA = '9dd9dc6b0f4ce4b680e1bf53d137d1b2f77e9d495bfcb63da84f3d3cc33559db'
SOURCE = 'https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca/14378_informe-tecnico-n0-a7270-evaluacion-de-peligro-geologico-por-lahares-huaycos-en-el-distrito-de-cayma-provincia-y-departamento-de-arequipa.pdf'

# Marcas UTM impresas, centros de las rayas del marco del anexo.
E_TICKS = [(175, 230000), (355, 235000), (536, 240000), (716, 245000), (896, 250000)]
N_TICKS = [(222, 8210000), (402, 8205000), (583, 8200000), (763, 8195000), (943, 8190000), (1124, 8185000)]

# Tres columnas: fila, borde oeste y borde este, según la mancha coloreada.
# Se incluye el extremo sur del análisis ANA. Cerca del norte el negro opaca
# el contorno y no se digitaliza esa parte. La fila 1084 corta la mancha,
# que sigue aguas abajo del tramo analizado en el prototipo.
TRAZA = [
    (953, 66, 72), (957, 66, 74), (961, 62, 75), (966, 66, 75),
    (971, 67, 76), (978, 69, 79), (985, 69, 81), (990, 72, 86),
    (994, 71, 85), (999, 74, 84), (1003, 73, 84), (1007, 69, 83),
    (1011, 68, 82), (1016, 67, 81), (1021, 71, 78), (1025, 66, 74),
    (1030, 67, 77), (1034, 69, 83), (1039, 72, 85), (1044, 73, 85),
    (1049, 74, 86), (1053, 75, 89), (1057, 75, 96), (1061, 74, 100),
    (1065, 73, 101), (1069, 74, 101), (1074, 76, 103),
    (1078, 80, 105), (1081, 79, 106), (1084, 76, 108),
]

def polygon_parts(geometry):
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [part for sub in getattr(geometry, 'geoms', ()) for part in polygon_parts(sub)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path, help='PDF original A7270')
    pdf = parser.parse_args().pdf
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != SHA:
        raise ValueError('El PDF no coincide con la edición documentada.')
    image = PdfReader(pdf).pages[66].images[0].image
    assert image.size == (947, 1340)
    east = np.polyfit(*zip(*E_TICKS), 1)
    north = np.polyfit(*zip(*N_TICKS), 1)
    errors = [abs(np.polyval(coeff, px) - value)
              for coeff, ticks in [(east, E_TICKS), (north, N_TICKS)] for px, value in ticks]
    west_edge = [(x_west, y) for y, x_west, _ in TRAZA]
    east_edge = [(x_east, y) for y, _, x_east in reversed(TRAZA)]
    footprint_utm = Polygon([(np.polyval(east, x), np.polyval(north, y))
                             for x, y in west_edge + east_edge])
    limites = json.loads((REPO / 'web/layers/limites-faja-cayma.geojson').read_text(encoding='utf-8'))
    a_utm = Transformer.from_crs(4326, 32719, always_xy=True).transform
    a_wgs = Transformer.from_crs(32719, 4326, always_xy=True).transform
    derecha, izquierda = [transform(shape(f['geometry']), a_utm, interleaved=False) for f in limites['features']]
    corredor = Polygon(list(derecha.coords) + list(reversed(izquierda.coords)))
    assert corredor.is_valid and footprint_utm.is_valid
    exterior = footprint_utm.difference(corredor)
    assert exterior.is_valid and not exterior.is_empty
    assert exterior.intersection(corredor).area < 0.001
    metadata = {
        'fuente': 'INGEMMET, Informe Técnico A7270, junio de 2022, anexo 4',
        'url_fuente': SOURCE + '#page=67', 'pagina_pdf': 67, 'figura_contraste_pdf': 58,
        'pdf_sha256': SHA, 'crs_trazado': 'EPSG:32719',
        'resolucion_m_por_pixel': round(float(east[0]), 1),
        'ajuste_marcas_error_max_m': round(max(errors), 1),
        'metodo': 'Trazado visual del contorno exterior de las tres clases visibles en el anexo, georreferenciado con sus marcas UTM; se resta el corredor ANA para la visualización.',
        'alcance': 'Segmento legible de Chullo en el entorno del tramo ANA de Cayma. Los extremos son cortes de cobertura. La zona es referencial a escala distrital.',
        'limite': 'El ajuste de las marcas no mide la exactitud de la huella. El tamaño de píxel, la rotulación y las diferencias entre fuentes limitan la precisión a escala de sector.',
    }
    features = [
        {'type': 'Feature', 'properties': {'clase': 'amarillo', 'etiqueta': 'Alcance simulado de huaicos · referencial'},
         'geometry': mapping(transform(part, a_wgs, interleaved=False))}
        for part in polygon_parts(exterior) if part.area > 1
    ]
    geo = {'type': 'FeatureCollection', 'metadata': metadata, 'features': features}
    (REPO / 'web/layers/huella-huaico-chullo-a7270.geojson').write_text(
        json.dumps(geo, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Huella UTM', footprint_utm.bounds, 'polígonos visibles fuera del corredor', len(features))
    print('Metros por píxel', east[0], -north[0], 'residuo marcas', max(errors))


if __name__ == '__main__':
    main()
