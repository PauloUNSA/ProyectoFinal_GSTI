"use strict";

// La API usa la misma geometría UTM que clasifica los contornos de la CNN.
let bandasGeoJSON = null;
let bandaLayer = null;
let huaicoLayer = null;

async function generarBandas(limites, rojoM, amarilloM) {
  if (!limites) throw new Error("Faltan los límites documentales.");
  if (window.CHULLO_STATIC) {
    if (Number(amarilloM) !== 0) throw new Error("El ancho fijo se retiró. El alcance simulado de huaicos se carga en una capa propia.");
    const resp = await fetch("layers/bandas-proximidad.geojson");
    if (!resp.ok) throw new Error("No se pudieron cargar las zonas publicadas.");
    return resp.json();
  }
  const resp = await fetch(`/api/bands?amarillo=${encodeURIComponent(amarilloM)}`);
  const bandas = await resp.json();
  if (!resp.ok) throw new Error(bandas.error || "No se pudieron calcular las zonas.");
  return bandas;
}

function dibujarBandasEnMapa(mapInstance, bandas) {
  if (bandaLayer) mapInstance.removeLayer(bandaLayer);
  bandasGeoJSON = bandas;
  const pane = "franjas";
  if (!mapInstance.getPane(pane)) mapInstance.createPane(pane).style.zIndex = 350;
  // Mostrar únicamente las zonas; el eje central se conserva para mediciones,
  // pero no se dibuja porque puede confundirse con una carretera.
  const capas = bandas.features.filter(f => ["rojo", "naranja"].includes(f.properties.clase)).map(f => {
    const clase = f.properties.clase;
    const estilo = {color: f.properties.color, weight: 2, fillColor: f.properties.color, fillOpacity: clase === "rojo" ? 0.3 : 0.45};
    return L.geoJSON(f, {style: estilo, pane}).bindPopup(f.properties.etiqueta);
  });
  bandaLayer = L.featureGroup(capas);
  if (document.getElementById("layer-bandas")?.checked !== false) bandaLayer.addTo(mapInstance);
  return bandaLayer;
}

async function recalcularBandas(mapInstance, limites, rojoM, amarilloM) {
  return dibujarBandasEnMapa(mapInstance, await generarBandas(limites, rojoM, amarilloM));
}

async function cargarHuellaHuaico(mapInstance) {
  const resp = await fetch("layers/huella-huaico-chullo-a7270.geojson");
  if (!resp.ok) throw new Error("No se pudo cargar la huella de huaicos de INGEMMET.");
  const geojson = await resp.json();
  const pane = mapInstance.createPane("huellaHuaico");
  pane.style.zIndex = 340;
  huaicoLayer = L.geoJSON(geojson, {
    pane,
    style: {color: "#eab308", weight: 2, fillColor: "#fde047", fillOpacity: 0.31},
  }).bindPopup(
    '<strong>Alcance simulado de huaicos</strong><br>Contorno aproximado del anexo 4, INGEMMET (2022). Reúne las tres categorías de peligro de la fuente.<br><a href="huaicos.html">Ver el método y el plano original</a>'
  );
  if (document.getElementById("layer-huaico").checked) huaicoLayer.addTo(mapInstance);
}

window.GENERAR_BANDAS = generarBandas;
window.DIBUJAR_BANDAS = dibujarBandasEnMapa;
window.RECALCULAR_BANDAS = recalcularBandas;
window.OBTENER_BANDAS = () => bandasGeoJSON;
