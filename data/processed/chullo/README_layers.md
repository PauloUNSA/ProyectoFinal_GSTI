"""Capas vectoriales preparadas para el sector Chullo.

Este archivo describe las capas que debe tener data/processed/chullo/ para
el análisis espacial. En la primera versión unificada, el visor lee los
GeoJSON directamente desde web/layers/.
"""

{
  "area": "Polígono de estudio del sector Chullo (EPSG:4326)",
  "rivers": "Eje de la torrentera Chullo calculado a partir de límites ANA Cayma",
  "buildings": "Edificios detectados por CNN (generado tras ejecutar la detección)",
  "sources": {
    "hitos_ana": "ANA Cayma RD 1610-2018 + ANA Yanahuara 2017",
    "limites_faja": "ANA Cayma Tabla 02 de vértices (planos pp. 40-44)",
    "modelo_cnn": "giswqs/geoai building_footprints_usa (Mask R-CNN ResNet50-FPN)"
  }
}
