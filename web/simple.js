"use strict";

/* ============================================================
   Chullo Unificado - simple.js
   Lógica principal del mapa Leaflet: inicialización, capas,
   puntos ANA, límites de faja, línea del cauce (unión de límites),
   franjas de proximidad con valores reales de ANA y detección CNN
   obligatoria de edificios.
   ============================================================ */

let map = null;
let puntoLayer = null;
let limiteLayer = null;
let cauceLayer = null;          // Línea del cauce uniendo los dos límites
let bandaLayer = null;
let edificioLayer = null;
let satelitalLayer = null;

const TILES_OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
// Capa satelital de mejor calidad (Esri World Imagery) para ver edificios como figuras de 4 lados
const TILES_SATELITAL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

// Valores por defecto basados en los documentos ANA (4 m por margen según Tabla 02 / RD 1610-2018).
// El usuario puede ajustarlos en la UI, pero la referencia real son los límites documentales de ANA.
const CONFIG = {
  rojoM: 4,        // ancho de faja documental por margen (derecha e izquierda)
  amarilloM: 20,   // franja adicional de seguridad más allá de la faja documental
  umbralDeteccion: 0.5,
};

function esc(v) {
  return String(v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function coordinateText(f) {
  const [lon, lat] = f.geometry.coordinates;
  return { lat: lat.toFixed(6), lon: lon.toFixed(6) };
}

// ------------------------------------------------------------------
// Mapa base
// ------------------------------------------------------------------
function initMap() {
  if (!window.L) {
    document.getElementById("map-state").textContent = "No disponible";
    document.getElementById("map-state").className = "error";
    document.getElementById("map").textContent = "No se pudo cargar el visor. Recarga la página.";
    return;
  }

  map = L.map("map", {
    scrollWheelZoom: false,
    zoomAnimation: false,
    fadeAnimation: false,
    markerZoomAnimation: false,
  }).setView([-16.39, -71.55], 15);

  const osm = L.tileLayer(TILES_OSM, {
    maxZoom: 19,
    attribution: "&copy; <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noopener'>OpenStreetMap</a> contributors",
  });

  satelitalLayer = L.tileLayer(TILES_SATELITAL, {
    maxZoom: 19,
    attribution: "&copy; <a href='https://www.esri.com/' target='_blank' rel='noopener'>Esri</a> · World Imagery",
  });

  // Satelital como base por defecto para identificar edificios (figuras de 4 lados / techos)
  satelitalLayer.addTo(map);
  document.getElementById("map-state").textContent = "Conectado";
  document.getElementById("map-state").className = "ready";

  L.control.scale({ imperial: false, maxWidth: 150 }).addTo(map);

  // Control de capas base
  const baseLayers = {
    "Imagen satelital (Esri)": satelitalLayer,
    "OpenStreetMap (callejero)": osm,
  };
  L.control.layers(baseLayers, null, { collapsed: false, position: "topright" }).addTo(map);

  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));

  // Cargar datos y capas
  cargarTodo();
}

// ------------------------------------------------------------------
// Cargar hitos, límites y calcular línea del cauce
// ------------------------------------------------------------------
async function cargarTodo() {
  // Hitos
  if (window.CARGAR_HITOS) await window.CARGAR_HITOS();
  // Límites
  if (window.CARGAR_LIMITES) await window.CARGAR_LIMITES();

  // Calcular línea del cauce uniendo los dos límites documentales (margen derecha + izquierda)
  const limites = window.CHULLO_BOUNDARIES;
  if (limites) {
    ejeTorrentera = calcularLineaCauce(limites);
  }

  // Dibujar capas
  dibujarPuntos();
  dibujarLimites();
  dibujarLineaCauce();
  dibujarBandas();

  // Configurar controles de UI
  configurarUI();
}

// Variable global para la línea del cauce
let ejeTorrentera = null;

// ------------------------------------------------------------------
// Unir los dos límites en una línea continua del cauce
// Calcula el punto medio entre margen derecha e izquierda en cada vértice
// y los conecta en orden para formar la línea del cauce de la torrentera.
// ------------------------------------------------------------------
function calcularLineaCauce(limites) {
  if (!limites || !limites.features || limites.features.length < 2) return null;

  const derecha = limites.features.find(f => f.properties.bank === "Derecha");
  const izquierda = limites.features.find(f => f.properties.bank === "Izquierda");

  if (!derecha || !izquierda) return null;

  const coordsD = derecha.geometry.coordinates;
  const coordsI = izquierda.geometry.coordinates;

  // Unir los dos límites punto a punto (medio entre ambas márgenes)
  // para formar la línea central del cauce de forma continua.
  const n = Math.min(coordsD.length, coordsI.length);
  const cauceCoords = [];
  for (let i = 0; i < n; i++) {
    const lon = (coordsD[i][0] + coordsI[i][0]) / 2;
    const lat = (coordsD[i][1] + coordsI[i][1]) / 2;
    cauceCoords.push([lon, lat]);
  }

  // Cerrar la línea uniendo el último punto con el primero si hay suficientes vértices
  // (forma un polígono aproximado del cauce + faja)
  if (cauceCoords.length > 2) {
    cauceCoords.push(cauceCoords[0]);
  }

  return {
    type: "Feature",
    geometry: { type: "LineString", coordinates: cauceCoords },
    properties: {
      role: "torrentera_axis",
      description: "Línea del cauce de la torrentera Chullo obtenida uniendo los límites documentales de ANA (margen derecha e izquierda)",
      fuente: "ANA Cayma · Tabla 02 de vértices de faja marginal (planos pp. 40-44)",
      vertices: cauceCoords.length,
    },
  };
}

// Exportar para módulos
window.CALCULAR_LINEA_CAUCE = calcularLineaCauce;
window.OBTENER_CAUCE = () => ejeTorrentera;

// ------------------------------------------------------------------
// Puntos ANA (hitos)
// ------------------------------------------------------------------
function dibujarPuntos() {
  if (puntoLayer && map) map.removeLayer(puntoLayer);
  const features = window.CHULLO_DATA ? window.CHULLO_DATA.features : [];
  if (!features || features.length === 0) return;

  puntoLayer = L.geoJSON(
    { type: "FeatureCollection", features },
    {
      pointToLayer: (f, latlng) => {
        const sector = f.properties.sector;
        const enRevision = f.properties.location_status === "source_conflict";
        return L.circleMarker(latlng, {
          radius: 7,
          color: "#fff",
          weight: 1.5,
          fillColor: sector === "Cayma" ? "#285d43" : "#c77827",
          fillOpacity: enRevision ? 0.5 : 1,
          dashArray: enRevision ? "4 3" : null,
          bubblingMouseEvents: false,
        });
      },
      onEachFeature: (f, layer) => {
        const p = f.properties;
        const c = coordinateText(f);
        const html =
          `<div class="point-popup" style="font:15px/1.5 system-ui,sans-serif;max-width:300px">` +
          `<strong>${esc(p.code)}</strong>` +
          (p.location_status === "source_conflict" ? `<p class="review-badge">Ubicación en revisión</p>` : "") +
          `<p>${esc(p.sector)} · margen ${p.bank.toLowerCase()}</p>` +
          `<dl style="margin:8px 0">` +
          `<dt>Latitud</dt><dd>${c.lat}</dd>` +
          `<dt>Longitud</dt><dd>${c.lon}</dd>` +
          `<dt>Este (UTM)</dt><dd>${p.easting} m</dd>` +
          `<dt>Norte (UTM)</dt><dd>${p.norte || p.northing} m</dd>` +
          `</dl>` +
          `<button class="source-button" data-open-source data-id="${esc(f.id)}">Ver fila de origen</button>` +
          `</div>`;
        layer.bindPopup(html, { minWidth: 280, maxWidth: 350, autoPan: true });
      },
    }
  ).addTo(map);

  if (puntoLayer.getBounds().isValid()) {
    map.fitBounds(puntoLayer.getBounds(), { padding: [40, 40], maxZoom: 17, animate: false });
  }
}

// ------------------------------------------------------------------
// Límites de faja (líneas exteriores Cayma)
// ------------------------------------------------------------------
function dibujarLimites() {
  if (limiteLayer && map) map.removeLayer(limiteLayer);
  const limites = window.CHULLO_BOUNDARIES;
  if (!limites || !limites.features) return;

  limiteLayer = L.geoJSON(limites, {
    style: f => ({
      color: f.properties.bank === "Derecha" ? "#216aab" : "#6b4ca0",
      weight: 3,
      opacity: 0.95,
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(
        `<strong>Límite exterior de faja · ${p.bank}</strong><br>` +
        `Cayma · ${p.vertices} vértices del documento ANA.<br>` +
        `Tabla 02 · RD 1610-2018 · Ancho documental: 4 m por margen`,
        { maxWidth: 300 }
      );
    },
  }).addTo(map);
}

// ------------------------------------------------------------------
// Línea del cauce (unión de los dos límites)
// ------------------------------------------------------------------
function dibujarLineaCauce() {
  if (cauceLayer && map) map.removeLayer(cauceLayer);
  if (!ejeTorrentera || !map) return;

  cauceLayer = L.geoJSON(ejeTorrentera, {
    style: { color: "#07838a", weight: 3, opacity: 0.9, dashArray: "6 8" },
  });
  cauceLayer.bindPopup(
    `<strong>Línea del cauce de la torrentera Chullo</strong><br>` +
    `Obtenida uniendo los límites documentales de ANA (margen derecha e izquierda)<br>` +
    `Vértices: ${ejeTorrentera.properties.vertices || "N/A"}`
  );
  cauceLayer.addTo(map);
}

// ------------------------------------------------------------------
// Franjas de proximidad con valores reales de ANA
// Rojo: dentro de la faja documental (0 a 4 m por margen)
// Amarillo: franja adicional de seguridad (4 a 24 m)
// Verde: más allá de 24 m
// ------------------------------------------------------------------
function dibujarBandas() {
  if (!ejeTorrentera || !map) return;
  if (window.RECALCULAR_BANDAS) {
    bandaLayer = window.RECALCULAR_BANDAS(map, CONFIG.rojoM, CONFIG.amarilloM);
  }

  // La línea del cauce ya se dibuja en dibujarLineaCauce()
  actualizarInfoPanel();
}

// ------------------------------------------------------------------
// Edificios detectados (CNN obligatorio)
// ------------------------------------------------------------------
function dibujarEdificiosDetectados(geojson) {
  if (!map) return;
  if (window.DIBUJAR_EDIFICIOS) {
    edificioLayer = window.DIBUJAR_EDIFICIOS(map, geojson, CONFIG.rojoM, CONFIG.amarilloM);
  }
}

function limpiarEdificios() {
  if (edificioLayer && map) {
    map.removeLayer(edificioLayer);
    edificioLayer = null;
  }
  const panel = document.getElementById("edificio-info");
  if (panel) panel.innerHTML = `<p class="vacio">Edificios eliminados. Ejecuta la detección CNN para volver a cargarlos.</p>`;
}

// ------------------------------------------------------------------
// UI y controles
// ------------------------------------------------------------------
function configurarUI() {
  // Toggle capas
  const toggles = {
    layer-hitos: () => toggleCapa(puntoLayer, "layer-hitos"),
    layer-limites: () => toggleCapa(limiteLayer, "layer-limites"),
    layer-cauce: () => toggleCapa(cauceLayer, "layer-cauce"),
    layer-bandas: () => toggleCapa(bandaLayer, "layer-bandas"),
    layer-edificios: () => toggleCapa(edificioLayer, "layer-edificios"),
    layer-satelital: toggleSatelital,
  };

  Object.entries(toggles).forEach(([id, fn]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", fn);
  });

  // Recalcular bandas con valores de ANA
  const btnRecalcular = document.getElementById("btn-recalcular-bandas");
  const inputRojo = document.getElementById("band-rojo");
  const inputAmarillo = document.getElementById("band-amarillo");

  if (btnRecalcular && inputRojo && inputAmarillo) {
    btnRecalcular.addEventListener("click", () => {
      const rojo = parseFloat(inputRojo.value) || 4;
      const amarillo = parseFloat(inputAmarillo.value) || 20;
      CONFIG.rojoM = rojo;
      CONFIG.amarilloM = amarillo;
      if (window.RECALCULAR_BANDAS) {
        bandaLayer = window.RECALCULAR_BANDAS(map, rojo, amarillo);
      }
      // Reclasificar edificios existentes si los hay
      if (edificioLayer && window.EJECUTAR_DETECCION) {
        // Los edificios se reclasifican al recargar su GeoJSON con nuevos umbrales
      }
      actualizarInfoPanel();
    });
  }

  // Botón detección CNN (obligatorio, siempre visible)
  const btnDetect = document.getElementById("btn-run-detect");
  if (btnDetect && window.EJECUTAR_DETECCION) {
    btnDetect.addEventListener("click", async () => {
      // Intentar usar imagen local del sector si existe, sino notificar
      const imagen = "data/imagery/chullo/chullo_rgb.tif";
      btnDetect.disabled = true;
      btnDetect.textContent = "Procesando CNN…";
      try {
        await window.EJECUTAR_DETECCION(imagen, CONFIG.umbralDeteccion);
      } finally {
        btnDetect.disabled = false;
        btnDetect.textContent = "Ejecutar detección CNN de edificios";
      }
    });
  }

  // Botón detectar edificios (header) - CNN obligatorio
  const btnDetected = document.getElementById("btn-detected");
  if (btnDetected && window.EJECUTAR_DETECCION) {
    btnDetected.addEventListener("click", async () => {
      const imagen = "data/imagery/chullo/chullo_rgb.tif";
      btnDetected.disabled = true;
      btnDetected.textContent = "Procesando CNN…";
      try {
        await window.EJECUTAR_DETECCION(imagen, CONFIG.umbralDeteccion);
      } finally {
        btnDetected.disabled = false;
        btnDetected.textContent = "Detectar edificios (CNN)";
      }
    });
  }

  // Diálogo de fuente
  const dialog = document.getElementById("source-dialog");
  const btnClose = document.getElementById("close-source");
  btnClose.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", ev => {
    if (ev.target === dialog) dialog.close();
  });

  // Delegación para botones "Ver fila de origen" en popups
  document.getElementById("map").addEventListener("click", ev => {
    const btn = ev.target.closest("[data-open-source]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const id = btn.getAttribute("data-id");
    if (!id) return;
    abrirFuente(id);
  });
}

function toggleCapa(layer, id) {
  const el = document.getElementById(id);
  if (!layer || !el) return;
  if (el.checked) {
    if (!map.hasLayer(layer)) layer.addTo(map);
  } else {
    if (map.hasLayer(layer)) map.removeLayer(layer);
  }
}

function toggleSatelital(ev) {
  if (ev.target.checked) {
    if (!map.hasLayer(satelitalLayer)) satelitalLayer.addTo(map);
  } else {
    if (map.hasLayer(satelitalLayer)) map.removeLayer(satelitalLayer);
  }
}

// ------------------------------------------------------------------
// Información de faja y edificio en panel lateral
// ------------------------------------------------------------------
function actualizarInfoPanel() {
  const panel = document.getElementById("panel-info");
  if (!panel) return;
  const rojo = CONFIG.rojoM;
  const amarillo = CONFIG.amarilloM;
  const exterior = rojo + amarillo;
  panel.innerHTML =
    `<strong>Franjas de proximidad (valores ANA)</strong><br>` +
    `Rojo: 0 a ${rojo} m (faja documental · 4 m por margen)<br>` +
    `Amarillo: ${rojo} a ${exterior} m (franja de seguridad adicional)<br>` +
    `Verde: &gt; ${exterior} m<br>` +
    `<small>Basado en los límites documentales de ANA (RD 1610-2018), no en criterios ilustrativos.</small>`;
}

function abrirFuente(id) {
  const f = window.CHULLO_DATA ? window.CHULLO_DATA.features.find(x => x.id === id) : null;
  if (!f) return;

  const p = f.properties;
  const c = coordinateText(f);
  const dialog = document.getElementById("source-dialog");
  const title = document.getElementById("source-title");
  const body = document.getElementById("source-body");

  title.textContent = "Fuente de " + esc(p.code);

  let fragment = "";
  if (p.source_kind === "pdf_crop") {
    fragment = `
      <h3>Fragmento del documento original</h3>
      <div class="scan-source">
        <img src="docs/${esc(p.source_header)}" alt="Cabecera original de la tabla">
        <p class="source-row-caption">Fila del punto seleccionado</p>
        <img class="source-row" src="docs/${esc(p.source_crop)}" alt="Fila original ${esc(p.code)}">
      </div>
    `;
  } else {
    const literal = esc(p.source_raw_line || "");
    const marked = p.source_selected_text
      ? literal.replace(esc(p.source_selected_text), `<mark>${esc(p.source_selected_text)}</mark>`)
      : literal;
    fragment = `
      <h3>Extracto literal del TXT recibido</h3>
      <pre class="literal-source">${marked}</pre>
    `;
  }

  const referencia = p.sector === "Cayma"
    ? "Expediente ANA Cayma · RD 1610-2018, rectificación del 22/03/2019"
    : "Resolución ANA del 28/12/2017 · Yanahuara";

  body.innerHTML =
    `<p class="source-document">${esc(referencia)}</p>` +
    `<p class="small">${esc(p.source_title || "")}</p>` +
    `<p class="source-location">${esc(p.source_locator || "")}</p>` +
    `<table class="source-values">` +
    `<thead><tr><th>Hito</th><th>Este (UTM) · m</th><th>Norte (UTM) · m</th></tr></thead>` +
    `<tbody><tr><td>${esc(p.source_code || p.code)}</td><td>${p.easting}</td><td>${p.norte || p.northing}</td></tr></tbody>` +
    `</table>` + fragment +
    `<p class="source-projection">Coordenadas UTM WGS84 zona 19S convertidas a latitud ${c.lat}, longitud ${c.lon}. No es una medición de campo.</p>` +
    `<a class="full-source" href="docs/${esc(p.source)}" target="_blank" rel="noopener">Abrir documento completo ↗</a>`;

  dialog.showModal();
}

// Inicializar cuando el DOM esté listo
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initMap);
} else {
  initMap();
}

// Exportar para módulos
window.MAP = () => map;
window.DIBUJAR_EDIFICIOS_DETECTADOS = dibujarEdificiosDetectados;
window.LIMPIAR_EDIFICIOS = limpiarEdificios;
window.OBTENER_CONFIG = () => CONFIG;
