"use strict";

/* ============================================================
   Chullo Unificado - bands.js
   Franjas de proximidad (rojo/amarillo/verde) desde la línea del cauce.
   Separa generación de GeoJSON de dibujo en el mapa para evitar recursión.
   ============================================================ */

let bandasGeoJSON = null;
let bandaLayer = null;

const COLORES = {
  rojo: "#dc2626",
  amarillo: "#eab308",
  verde: "#16a34a",
  eje: "#07838a",
};

// 1 grado latitud ≈ 111,000 m. Ajustado por latitud de Arequipa (~-16.4°).
function metrosAGrados(metros, latitud = -16.4) {
  const mPorGradoLat = 111000;
  const mPorGradoLon = 111000 * Math.cos((latitud * Math.PI) / 180);
  return { lat: metros / mPorGradoLat, lon: metros / mPorGradoLon };
}

// Buffer aproximado alrededor de una línea (rectángulos por segmento)
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

  if (puntos.length > 0) {
    puntos.push(puntos[0]);
  }

  return puntos.length >= 4 ? [puntos] : null;
}

// Generar GeoJSON de franjas (solo datos, no dibuja)
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
        etiqueta: "Rojo · faja documental ANA (0–4 m)",
        distancia_m: rojoM,
        color: COLORES.rojo,
      },
    });
  }

  if (amarilloBuff) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: amarilloBuff },
      properties: {
        clase: "amarillo",
        etiqueta: "Amarillo · franja de seguridad (4–24 m)",
        distancia_m: rojoM + amarilloM,
        color: COLORES.amarillo,
      },
    });
  }

  features.push({
    type: "Feature",
    geometry: { type: "LineString", coordinates: coords },
    properties: {
      clase: "eje",
      etiqueta: "Línea del cauce (unión de límites ANA)",
      color: COLORES.eje,
    },
  });

  return {
    type: "FeatureCollection",
    features,
    metadata: { rojo_m: rojoM, amarillo_m: amarilloM, exterior_m: rojoM + amarilloM },
  };
}

// Dibujar bandas en el mapa (solo dibuja, no recalcula — evita recursión)
function dibujarBandas(mapInstance, bandas) {
  if (bandaLayer) {
    mapInstance.removeLayer(bandaLayer);
    bandaLayer = null;
  }

  if (!bandas || !bandas.features || bandas.features.length === 0) return null;

  const capas = bandas.features.map(f => {
    const { clase, color } = f.properties;
    let estilo;

    if (clase === "eje") {
      estilo = { color: COLORES.eje, weight: 3, opacity: 0.9, dashArray: "6 8" };
    } else if (clase === "rojo") {
      estilo = { color: COLORES.rojo, weight: 1, fillColor: COLORES.rojo, fillOpacity: 0.25 };
    } else {
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

// Generar + dibujar (llamado una vez al iniciar o al cambiar umbrales manualmente)
function recalcularBandas(mapInstance, eje, rojoM, amarilloM) {
  if (!eje) {
    console.warn("No hay línea del cauce para calcular bandas");
    return null;
  }

  bandasGeoJSON = generarBandas(eje, rojoM, amarilloM);
  return dibujarBandas(mapInstance, bandasGeoJSON);
}

window.GENERAR_BANDAS = generarBandas;
window.DIBUJAR_BANDAS = dibujarBandas;
window.RECALCULAR_BANDAS = recalcularBandas;
window.OBTENER_BANDAS = () => bandasGeoJSON;
