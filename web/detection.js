"use strict";

const clasesCubiertas = ["rojo", "naranja", "amarillo"];
const resultadosVersion = "20261123-cruce-a7270";

function dibujarEdificios(mapInstance, geojson) {
  if (edificioLayer) mapInstance.removeLayer(edificioLayer);
  const features = (geojson?.features || []).filter(f => clasesCubiertas.includes(f.properties?.clase));
  const mapa = mapInstance.getContainer();
  const leyenda = mapa.parentElement.querySelector(".map-legend");
  const espacioLeyenda = leyenda
    ? Math.max(12, leyenda.getBoundingClientRect().bottom - mapa.getBoundingClientRect().top + 12)
    : 12;
  edificioLayer = L.geoJSON({type: "FeatureCollection", features}, {
    style: f => ({color: f.properties.clase === "amarillo" ? "#7c4a06" : f.properties.color, weight: 2, fillColor: f.properties.color, fillOpacity: f.properties.clase === "amarillo" ? 0.68 : 0.55}),
    onEachFeature: (f, layer) => {
      layer.bindPopup(`<strong>${esc(f.properties.etiqueta)}</strong>`,
        {autoPanPaddingTopLeft: [12, espacioLeyenda], maxWidth: 300});
    },
  });
  if (document.getElementById("layer-edificios")?.checked !== false) edificioLayer.addTo(mapInstance);
  const counts = Object.fromEntries(clasesCubiertas.map(clase => [clase, 0]));
  for (const feature of features) counts[feature.properties.clase]++;
  document.getElementById("edificio-info").innerHTML =
    `<strong>${features.length} contornos candidatos</strong><br>` +
    `Rojo: ${counts.rojo} · Naranja: ${counts.naranja} · Amarillo: ${counts.amarillo}`;
}

async function cargarEdificiosGeoJSON(ruta, mapInstance) {
  const resp = await fetch(ruta);
  if (!resp.ok) throw new Error("No se pudo cargar el resultado de la CNN.");
  dibujarEdificios(mapInstance, await resp.json());
}

async function cargarEstadoDetector() {
  const estado = document.getElementById("cnn-state");
  const resumen = document.getElementById("edificio-info");
  try {
    let ruta = `outputs/detection/buildings.geojson?v=${resultadosVersion}`;
    if (!window.CHULLO_STATIC) {
      const resp = await fetch("/api/status");
      if (!resp.ok) throw new Error("No se pudo consultar el estado de la detección.");
      const {manifest} = await resp.json();
      if (!manifest) {
        estado.textContent = "Sin resultados";
        resumen.textContent = "No hay contornos guardados.";
        return;
      }
      ruta = "/outputs/detection/buildings.geojson";
    }
    await cargarEdificiosGeoJSON(ruta, window.MAP());
    estado.textContent = "Resultados guardados";
    estado.className = "ready";
  } catch {
    estado.textContent = "No disponible";
    estado.className = "error";
    resumen.textContent = "No se pudieron cargar los contornos.";
  }
}

window.CARGAR_ESTADO_DETECTOR = cargarEstadoDetector;
