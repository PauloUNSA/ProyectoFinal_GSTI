"use strict";

/* ============================================================
   Chullo Unificado - data.js
   Datos embebidos: puntos ANA (Cayma + Yanahuara) y límites de faja (Cayma).
   Se cargan desde archivos GeoJSON locales en web/layers/.
   ============================================================ */

const CHULLO = {
  version: "1.0.0",
  descripcion: "Torrentera Chullo · Arequipa · Datos unificados",
  fuentes: {
    hitos: "ANA Cayma (RD 1610-2018, rectif. 22/03/2019) + ANA Yanahuara (28/12/2017, en revisión)",
    limites: "ANA Cayma · Tabla 02 de vértices de faja marginal (planos pp. 40-44)",
  },
  crs: { original: "EPSG:32719", geojson: "EPSG:4326" },
};

// Referencias a capas Leaflet (se asignan en simple.js)
let pointLayer = null;
let boundaryLayer = null;
let bandaLayer = null;
let edificioLayer = null;
let satelitalLayer = null;
let map = null;
let ejeTorrentera = null; // LineString del eje calculado

const CONFIG = {
  rojoM: 25,
  amarilloM: 25,
  umbralDeteccion: 0.5,
};

// Cargar GeoJSON de hitos ANA
async function cargarHitos() {
  try {
    const resp = await fetch("layers/hitos-ana.geojson");
    if (!resp.ok) throw new Error("No se pudo cargar hitos-ana.geojson");
    const data = await resp.json();
    window.CHULLO_DATA = data;
    return data;
  } catch (e) {
    console.error("Error cargando hitos:", e);
    return null;
  }
}

// Cargar GeoJSON de límites de faja Cayma
async function cargarLimites() {
  try {
    const resp = await fetch("layers/limites-faja-cayma.geojson");
    if (!resp.ok) throw new Error("No se pudo cargar limites-faja-cayma.geojson");
    const data = await resp.json();
    window.CHULLO_BOUNDARIES = data;
    return data;
  } catch (e) {
    console.error("Error cargando límites:", e);
    return null;
  }
}

// Calcular eje aproximado de la torrentera como línea central entre los dos límites
function calcularEjeTorrentera(limites) {
  if (!limites || !limites.features || limites.features.length < 2) return null;

  const derecha = limites.features.find(f => f.properties.bank === "Derecha");
  const izquierda = limites.features.find(f => f.properties.bank === "Izquierda");

  if (!derecha || !izquierda) return null;

  const coordsD = derecha.geometry.coordinates;
  const coordsI = izquierda.geometry.coordinates;

  // Interpolar puntos medios a lo largo del tramo común
  const n = Math.min(coordsD.length, coordsI.length);
  const ejeCoords = [];
  for (let i = 0; i < n; i++) {
    const lon = (coordsD[i][0] + coordsI[i][0]) / 2;
    const lat = (coordsD[i][1] + coordsI[i][1]) / 2;
    ejeCoords.push([lon, lat]);
  }

  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates: ejeCoords },
    properties: {
      role: "torrentera_axis",
      description: "Eje aproximado de la torrentera Chullo (media entre límites documentales de Cayma)",
      fuente: "Calculado a partir de límites ANA Cayma",
    },
  };
}

// Obtener el eje (se calcula una vez cargados los límites)
function obtenerEje() {
  return ejeTorrentera;
}

// Exportar para uso en otros módulos
window.CHULLO = CHULLO;
window.CARGAR_HITOS = cargarHitos;
window.CARGAR_LIMITES = cargarLimites;
window.CALCULAR_EJE = calcularEjeTorrentera;
window.OBTENER_EJE = obtenerEje;
window.CONFIG = CONFIG;
