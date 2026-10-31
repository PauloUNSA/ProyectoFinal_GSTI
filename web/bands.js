"use strict";

/* ============================================================
   Chullo Unificado - bands.js
   Franjas de proximidad (semáforo rojo/amarillo/verde)
   Calculadas desde el eje de la torrentera.
   ============================================================ */

let bandasGeoJSON = null;
let mapaBandas = new Map(); // distancia -> color

const COLORES = {
  rojo: "#dc2626",
  amarillo: "#eab308",
  verde: "#16a34a",
  eje: "#07838a",
};

// Generar buffers circulares en grados (aproximación para visualización en Leaflet WGS84)
// 1 grado latitud ≈ 111,000 m. Ajustamos por latitud de Arequipa (~-16.4°).
function metrosAGrados(metros, latitud = -16.4) {
  const mPorGradoLat = 111000;
  const mPorGradoLon = 111000 * Math.cos((latitud * Math.PI) / 180);
  return { lat: metros / mPorGradoLat, lon: metros / mPorGradoLon };
}

// Crear un polígono de buffer simple alrededor de una línea (aproximación por puntos)
// Para cada segmento, crear rectángulo con extremos redondeados (casquete)
function bufferLinea(coordenadas, metros) {
  const { lat: dLat, lon: dLon } = metrosAGrados(metros);
  const puntos = [];

  for (let i = 0; i < coordenadas.length - 1; i++) {
    const [lon1, lat1] = coordenadas[i];
    const [lon2, lat2] = coordenadas[i + 1];

    const dx = lon2 - lon1;
    const dy = lat2 - lat1;
    const largo = Math.sqrt(dx * dx + dy * dy);

    if (largo === 0) continue;

    const nx = (-dy / largo) * dLon;
    const ny = (dx / largo) * dLat;

    puntos.push([lon1 + nx, lat1 + ny]);
    puntos.push([lon1 - nx, lat1 - ny]);
    puntos.push([lon2 - nx, lat2 - ny]);
    puntos.push([lon2 + nx, lat2 + ny]);
  }

  // Cerrar polígono
  if (puntos.length > 0) {
    puntos.push(puntos[0]);
  }

  return puntos.length >= 4 ? [puntos] : null;
}

// Generar GeoJSON de franjas (roja, amarilla) desde el eje
function generarBandas(eje, rojoM, amarilloM) {
  if (!eje || !eje.geometry || !eje.geometry.coordinates) return null;

  const coords = eje.geometry.coordinates;
  const rojoBuff = bufferLinea(coords, rojoM);
  const amarilloBuff = bufferLinea(coords, rojoM + amarilloM);

  const features = [];

  if (rojoBuff) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: rojoBuff },
      properties: {
        clase: "rojo",
        etiqueta: "Rojo · proximidad inmediata",
        distancia_m: rojoM,
        color: COLORES.rojo,
      },
    });
  }

  if (amarilloBuff && rojoBuff) {
    // Zona amarilla = buffer exterior menos buffer interior (aproximación visual)
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: amarilloBuff },
      properties: {
        clase: "amarillo",
        etiqueta: "Amarillo · proximidad intermedia",
        distancia_m: rojoM + amarilloM,
        color: COLORES.amarillo,
      },
    });
  }

  // Línea del eje
  features.push({
    type: "Feature",
    geometry: { type: "LineString", coordinates: coords },
    properties: {
      clase: "eje",
      etiqueta: "Eje de la torrentera",
      color: COLORES.eje,
    },
  });

  return {
    type: "FeatureCollection",
    features,
    metadata: { rojo_m: rojoM, amarillo_m: amarilloM, exterior_m: rojoM + amarilloM },
  };
}

// Dibujar bandas en el mapa
function dibujarBandas(mapInstance, bandas) {
  if (bandaLayer) {
    mapInstance.removeLayer(bandaLayer);
    bandaLayer = null;
  }

  if (!bandas || !bandas.features || bandas.features.length === 0) return;

  const capas = bandas.features.map(f => {
    const { clase, color } = f.properties;
    let estilo;

    if (clase === "eje") {
      estilo = { color: COLORES.eje, weight: 3, opacity: 0.9, dashArray: "5 6" };
    } else if (clase === "rojo") {
      estilo = { color: COLORES.rojo, weight: 1, fillColor: COLORES.rojo, fillOpacity: 0.25 };
    } else {
      // amarillo: solo el anillo exterior (visual simplificado)
      estilo = { color: COLORES.amarillo, weight: 1, fillColor: COLORES.amarillo, fillOpacity: 0.12 };
    }

    const layer = L.geoJSON(f, { style: estilo });
    layer.bindPopup(
      `<strong>${f.properties.etiqueta}</strong><br>` +
      (f.properties.distancia_m !== undefined
        ? `Límite exterior: ${f.properties.distancia_m} m`
        : "Eje de referencia de la torrentera")
    );
    return layer;
  });

  bandaLayer = L.featureGroup(capas).addTo(mapInstance);
  return bandaLayer;
}

// Recalcular y redibujar bandas con nuevos umbrales
function recalcularBandas(mapInstance, rojoM, amarilloM) {
  const eje = window.OBTENER_EJE ? window.OBTENER_EJE() : null;
  if (!eje) {
    console.warn("No hay eje de torrentera disponible para calcular bandas");
    return null;
  }

  CONFIG.rojoM = rojoM;
  CONFIG.amarilloM = amarilloM;

  bandasGeoJSON = generarBandas(eje, rojoM, amarilloM);
  return dibujarBandas(mapInstance, bandasGeoJSON);
}

// Exportar
window.GENERAR_BANDAS = generarBandas;
window.DIBUJAR_BANDAS = dibujarBandas;
window.RECALCULAR_BANDAS = recalcularBandas;
window.OBTENER_BANDAS = () => bandasGeoJSON;
window.CONFIG_BANDAS = () => ({ rojoM: CONFIG.rojoM, amarilloM: CONFIG.amarilloM });
