"use strict";

/* ============================================================
   Chullo Unificado - simple.js
   Lógica principal del mapa Leaflet: inicialización, capas,
   puntos ANA, límites de faja, franjas de proximidad y UI.
   ============================================================ */

let map = null;
let puntoLayer = null;
let limiteLayer = null;
let bandaLayer = null;
let edificioLayer = null;
let satelitalLayer = null;
let ejeTorrentera = null;

const TILES_OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILES_SATELITAL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

const CONFIG = {
  rojoM: 25,
  amarilloM: 25,
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

  osm.addTo(map);
  document.getElementById("map-state").textContent = "Conectado";
  document.getElementById("map-state").className = "ready";

  L.control.scale({ imperial: false, maxWidth: 150 }).addTo(map);

  // Control de capas base
  const baseLayers = {
    "OpenStreetMap (callejero)": osm,
    "Imagen satelital (Esri)": satelitalLayer,
  };
  L.control.layers(baseLayers, null, { collapsed: false, position: "topright" }).addTo(map);

  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));

  // Cargar datos y capas
  cargarTodo();
}

// ------------------------------------------------------------------
// Cargar hitos, límites y calcular eje
// ------------------------------------------------------------------
async function cargarTodo() {
  // Hitos
  if (window.CARGAR_HITOS) await window.CARGAR_HITOS();
  // Límites
  if (window.CARGAR_LIMITES) await window.CARGAR_LIMITES();

  // Calcular eje de torrentera desde los límites
  const limites = window.CHULLO_BOUNDARIES;
  if (limites && window.CALCULAR_EJE) {
    ejeTorrentera = window.CALCULAR_EJE(limites);
  }

  // Dibujar capas
  dibujarPuntos();
  dibujarLimites();
  dibujarBandas();

  // Configurar controles de UI
  configurarUI();
}

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
          `<dt>Este</dt><dd>${p.easting} m</dd>` +
          `<dt>Norte</dt><dd>${p.norte || p.northing} m</dd>` +
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
        `Tabla 02 · RD 1610-2018`,
        { maxWidth: 300 }
      );
    },
  }).addTo(map);
}

// ------------------------------------------------------------------
// Franjas de proximidad
// ------------------------------------------------------------------
function dibujarBandas() {
  if (!ejeTorrentera || !map) return;
  if (window.RECALCULAR_BANDAS) {
    bandaLayer = window.RECALCULAR_BANDAS(map, CONFIG.rojoM, CONFIG.amarilloM);
  }

  // Dibujar línea del eje si no está en bandas
  if (ejeTorrentera) {
    const ejeLayer = L.geoJSON(ejeTorrentera, {
      style: { color: "#07838a", weight: 3, opacity: 0.9, dashArray: "5 6" },
    });
    ejeLayer.bindPopup("Eje aproximado de la torrentera Chullo (media entre límites documentales)");
    if (bandaLayer) {
      // Añadir al feature group de bandas si existe
      bandaLayer.addLayer(ejeLayer);
    } else {
      ejeLayer.addTo(map);
    }
  }

  actualizarInfoPanel();
}

// ------------------------------------------------------------------
// Edificios detectados
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
  if (panel) panel.innerHTML = `<p class="vacio">Edificios eliminados. Ejecuta la detección para volver a cargarlos.</p>`;
}

// ------------------------------------------------------------------
// UI y controles
// ------------------------------------------------------------------
function configurarUI() {
  // Toggle capas
  const toggles = {
    layer-hitos: () => toggleCapa(puntoLayer, "layer-hitos"),
    layer-limites: () => toggleCapa(limiteLayer, "layer-limites"),
    layer-bandas: () => toggleCapa(bandaLayer, "layer-bandas"),
    layer-edificios: () => toggleCapa(edificioLayer, "layer-edificios"),
    layer-satelital: toggleSatelital,
  };

  Object.entries(toggles).forEach(([id, fn]) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", fn);
  });

  // Recalcular bandas
  const btnRecalcular = document.getElementById("btn-recalcular-bandas");
  const inputRojo = document.getElementById("band-rojo");
  const inputAmarillo = document.getElementById("band-amarillo");

  if (btnRecalcular && inputRojo && inputAmarillo) {
    btnRecalcular.addEventListener("click", () => {
      const rojo = parseFloat(inputRojo.value) || 25;
      const amarillo = parseFloat(inputAmarillo.value) || 25;
      CONFIG.rojoM = rojo;
      CONFIG.amarilloM = amarillo;
      if (window.RECALCULAR_BANDAS) {
        bandaLayer = window.RECALCULAR_BANDAS(map, rojo, amarillo);
      }
      // Reclasificar edificios existentes si los hay
      if (edificioLayer && window.EJECUTAR_DETECCION) {
        // Los edificios ya dibujados se reclasifican al recargar su GeoJSON
        // Aquí solo actualizamos la configuración global
      }
      actualizarInfoPanel();
    });
  }

  // Botón detección
  const btnDetect = document.getElementById("btn-run-detect");
  if (btnDetect && window.EJECUTAR_DETECCION) {
    btnDetect.addEventListener("click", () => {
      // Imagen por defecto del sector (si existe)
      const imagen = "data/imagery/chullo/chullo_rgb.tif";
      window.EJECUTAR_DETECCION(imagen, CONFIG.umbralDeteccion || 0.5);
    });
  }

  // Botón detectar edificios (header)
  const btnDetected = document.getElementById("btn-detected");
  if (btnDetected && window.EJECUTAR_DETECCION) {
    btnDetected.addEventListener("click", () => {
      const imagen = "data/imagery/chullo/chullo_rgb.tif";
      window.EJECUTAR_DETECCION(imagen, CONFIG.umbralDeteccion || 0.5);
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
    `<strong>Franjas de proximidad</strong><br>` +
    `Rojo: 0 a ${rojo} m · Amarillo: ${rojo} a ${exterior} m · Verde: &gt; ${exterior} m<br>` +
    `<small>Calculado desde el eje de la torrentera Chullo.</small>`;
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
    `<thead><tr><th>Hito</th><th>Este · m</th><th>Norte · m</th></tr></thead>` +
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
