"use strict";

/* ============================================================
   Chullo Unificado - data.js
   Datos: puntos ANA, límites de faja, configuración.
   No declara capas Leaflet ni el mapa (eso está en simple.js).
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

// Configuración por defecto (valores ANA: faja documental 4 m, franja seguridad 20 m)
const CONFIG = {
  rojoM: 4,
  amarilloM: 20,
  umbralDeteccion: 0.5,
};

// Referencias globales (se asignan desde simple.js)
let ejeTorrentera = null;

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

// Calcular línea del cauce uniendo los dos límites documentales (punto medio entre márgenes)
function calcularEjeTorrentera(limites) {
  if (!limites || !limites.features || limites.features.length < 2) return null;

  const derecha = limites.features.find(f => f.properties.bank === "Derecha");
  const izquierda = limites.features.find(f => f.properties.bank === "Izquierda");

  if (!derecha || !izquierda) return null;

  const coordsD = derecha.geometry.coordinates;
  const coordsI = izquierda.geometry.coordinates;

  const n = Math.min(coordsD.length, coordsI.length);
  const ejeCoords = [];
  for (let i = 0; i < n; i++) {
    const lon = (coordsD[i][0] + coordsI[i][0]) / 2;
    const lat = (coordsD[i][1] + coordsI[i][1]) / 2;
    ejeCoords.push([lon, lat]);
  }

  if (ejeCoords.length > 2) {
    ejeCoords.push(ejeCoords[0]);
  }

  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates: ejeCoords },
    properties: {
      role: "torrentera_axis",
      description: "Línea del cauce de la torrentera Chullo (unión de límites documentales ANA)",
      fuente: "ANA Cayma · Tabla 02 de vértices (planos pp. 40-44)",
    },
  };
}

function obtenerEje() {
  return ejeTorrentera;
}

window.CHULLO = CHULLO;
window.CARGAR_HITOS = cargarHitos;
window.CARGAR_LIMITES = cargarLimites;
window.CALCULAR_EJE = calcularEjeTorrentera;
window.OBTENER_EJE = obtenerEje;
window.CONFIG = CONFIG;
