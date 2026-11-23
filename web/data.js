"use strict";

window.CONFIG = {rojoM: 4, amarilloM: 0};

window.CARGAR_REFERENCIAS = async function () {
  const respuesta = await fetch("layers/referencias-visor-cayma.geojson");
  if (!respuesta.ok) throw new Error("No se pudieron cargar las referencias de Cayma.");
  const {features} = await respuesta.json();
  const coleccion = categoria => ({
    type: "FeatureCollection",
    features: features.filter(f => f.properties.categoria === categoria),
  });
  window.CHULLO_DATA = coleccion("hito");
  window.CHULLO_BOUNDARIES = coleccion("limite");
  window.CHULLO_VERTICES = coleccion("vertice");
  document.getElementById("ana-count").textContent = `${window.CHULLO_DATA.features.length} hitos en Cayma`;
};
