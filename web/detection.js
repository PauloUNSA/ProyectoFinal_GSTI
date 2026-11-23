"use strict";

const zonasCubiertas = {
  rojo: "el área aproximada del cauce o de las riberas",
  naranja: "alguna de las fajas marginales reconstruidas a partir de los límites de la ANA",
  amarillo: "el área que podrían alcanzar los huaicos según la simulación de INGEMMET",
};
const resultadosVersion = "20261123-cruce-a7270";

function dibujarEdificios(mapInstance, geojson) {
  if (edificioLayer) mapInstance.removeLayer(edificioLayer);
  const features = (geojson?.features || []).filter(f => Object.hasOwn(zonasCubiertas, f.properties?.clase));
  edificioLayer = L.geoJSON({type: "FeatureCollection", features}, {
    style: f => ({color: f.properties.clase === "amarillo" ? "#7c4a06" : f.properties.color, weight: 2, fillColor: f.properties.color, fillOpacity: f.properties.clase === "amarillo" ? 0.68 : 0.55}),
    onEachFeature: (f, layer) => {
      layer.bindPopup(`<strong>${esc(f.properties.etiqueta)}</strong>`,
        {autoPanPadding: [12, 12], maxWidth: 300});
    },
  });
  if (document.getElementById("layer-edificios")?.checked !== false) edificioLayer.addTo(mapInstance);
  const conteos = {rojo: 0, naranja: 0, amarillo: 0};
  for (const feature of features) conteos[feature.properties.clase]++;
  document.getElementById("edificio-info").innerHTML = Object.entries(zonasCubiertas)
    .map(([clase, zona]) => {
      const cantidad = conteos[clase];
      const detecciones = cantidad === 1 ? "posible edificación que toca" : "posibles edificaciones que tocan";
      return `<p>Hay <strong class="${clase}">${cantidad}</strong> ${detecciones} ${zona}.</p>`;
    }).join("");
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
