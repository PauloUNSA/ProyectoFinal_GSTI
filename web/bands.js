"use strict";

/* ============================================================
   Chullo Unificado - bands.js
   Franjas de proximidad (rojo/amarillo) basadas en los límites
   documentales de faja marginal.
   
   Estructura: |x(I)y(D)x|
   - I, D = líneas de límites documentales (izquierda y derecha)
   - y = franja roja entre I y D (faja documental, centrada en el cauce)
   - x = franja amarilla fuera de I y D (franja de seguridad)
   - | = límites exteriores (distancia configurable)
   
   Separa generación de GeoJSON de dibujo en el mapa.
   ============================================================ */

let bandasGeoJSON = null;
let bandaLayer = null;

const COLORES = {
  rojo: "#dc2626",
  amarillo: "#eab308",
  verde: "#16a34a",
  cauce: "#07838a",
};

// 1 grado latitud ≈ 111,000 m. Ajustado por latitud de Arequipa (~-16.4°).
function metrosAGrados(metros, latitud = -16.4) {
  const mPorGradoLat = 111000;
  const mPorGradoLon = 111000 * Math.cos((latitud * Math.PI) / 180);
  return { lat: metros / mPorGradoLat, lon: metros / mPorGradoLon };
}

// Calcula los puntos normales (perpendiculares) a un segmento de línea
function puntosNormales(lon1, lat1, lon2, lat2, metros) {
  const { lat: dLat, lon: dLon } = metrosAGrados(metros);
  const dx = lon2 - lon1;
  const dy = lat2 - lat1;
  const largo = Math.sqrt(dx * dx + dy * dy);
  if (largo === 0) return null;
  const nx = (-dy / largo) * dLon;
  const ny = (dx / largo) * dLat;
  return {
    d: [lon1 + nx, lat1 + ny],
    i: [lon1 - nx, lat1 - ny],
  };
}

// Genera un buffer que sigue exactamente el curso de una línea (segmento a segmento)
// Devuelve coordenadas de un polígono cerrado que envuelve la línea por ambos lados
function bufferLineaSeguido(coordenadas, metros) {
  if (!coordenadas || coordenadas.length < 2) return null;

  const izq = [];
  const der = [];

  for (let i = 0; i < coordenadas.length - 1; i++) {
    const [lon1, lat1] = coordenadas[i];
    const [lon2, lat2] = coordenadas[i + 1];
    const n = puntosNormales(lon1, lat1, lon2, lat2, metros);
    if (!n) continue;
    izq.push(n.i);
    der.push(n.d);
  }

  // Para cerrar el polígono: izquierda hacia adelante, luego derecha hacia atrás
  const coords = [];
  for (let i = 0; i < izq.length; i++) {
    coords.push(izq[i]);
  }
  for (let i = der.length - 1; i >= 0; i--) {
    coords.push(der[i]);
  }
  if (coords.length > 0) {
    coords.push(coords[0]);
  }

  return coords.length >= 4 ? [coords] : null;
}

// Calcular línea del cauce (promedio punto a punto de los dos límites documentales)
function calcularLineaCauce(limites) {
  if (!limites || !limites.features || limites.features.length < 2) return null;

  const derecha = limites.features.find(f => f.properties.bank === "Derecha");
  const izquierda = limites.features.find(f => f.properties.bank === "Izquierda");

  if (!derecha || !izquierda) return null;

  const coordsD = derecha.geometry.coordinates;
  const coordsI = izquierda.geometry.coordinates;

  const n = Math.min(coordsD.length, coordsI.length);
  const cauceCoords = [];
  for (let i = 0; i < n; i++) {
    const lon = (coordsD[i][0] + coordsI[i][0]) / 2;
    const lat = (coordsD[i][1] + coordsI[i][1]) / 2;
    cauceCoords.push([lon, lat]);
  }

  return cauceCoords.length >= 2 ? cauceCoords : null;
}

// Generar GeoJSON de franjas desde los límites documentales
// Estructura: |x(I)y(D)x|
// - I, D = líneas de límites documentales (izquierda y derecha)
// - y = franja roja ajustadísima a cada límite (faja documental, centrada en I y D)
// - x = franja amarilla fuera de cada límite (franja de seguridad)
// - | = límites exteriores (distancia configurable)
// El rojo se dibuja justo sobre cada línea límite, no en el medio del cauce.
// El amarillo se dibuja primero (fondo), luego el rojo encima (primer plano).
function generarBandas(limites, rojoM, amarilloM) {
  if (!limites || !limites.features) return null;

  const derecha = limites.features.find(f => f.properties.bank === "Derecha");
  const izquierda = limites.features.find(f => f.properties.bank === "Izquierda");

  if (!derecha || !izquierda) return null;

  const coordsD = derecha.geometry.coordinates;
  const coordsI = izquierda.geometry.coordinates;

  // Rojo: buffer de rojoM alrededor de CADA línea límite (derecha e izquierda por separado)
  // Esto deja el rojo justo sobre los márgenes I y D, no en el medio del cauce.
  const rojoBuffD = bufferLineaSeguido(coordsD, rojoM);
  const rojoBuffI = bufferLineaSeguido(coordsI, rojoM);

  // Amarillo: buffer de (rojoM + amarilloM) alrededor de CADA línea límite (fuera de I y D)
  const exteriorBuffD = bufferLineaSeguido(coordsD, rojoM + amarilloM);
  const exteriorBuffI = bufferLineaSeguido(coordsI, rojoM + amarilloM);

  const features = [];

  // Amarillo primero (fondo): buffers exteriores alrededor de cada límite
  if (exteriorBuffD) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: exteriorBuffD },
      properties: {
        clase: "amarillo",
        etiqueta: "Amarillo · franja de seguridad (" + rojoM + "–" + (rojoM + amarilloM) + " m)",
        distancia_m: rojoM + amarilloM,
        color: COLORES.amarillo,
        orden: 1,
      },
    });
  }
  if (exteriorBuffI) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: exteriorBuffI },
      properties: {
        clase: "amarillo",
        etiqueta: "Amarillo · franja de seguridad (" + rojoM + "–" + (rojoM + amarilloM) + " m)",
        distancia_m: rojoM + amarilloM,
        color: COLORES.amarillo,
        orden: 1,
      },
    });
  }

  // Rojo después (primer plano): buffers ajustados a cada límite límite (I y D)
  if (rojoBuffD) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: rojoBuffD },
      properties: {
        clase: "rojo",
        etiqueta: "Rojo · faja documental (0–" + rojoM + " m) · margen derecho",
        distancia_m: rojoM,
        color: COLORES.rojo,
        orden: 2,
      },
    });
  }
  if (rojoBuffI) {
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: rojoBuffI },
      properties: {
        clase: "rojo",
        etiqueta: "Rojo · faja documental (0–" + rojoM + " m) · margen izquierdo",
        distancia_m: rojoM,
        color: COLORES.rojo,
        orden: 2,
      },
    });
  }

  // Línea del cauce (referencia del río, se dibuja al final)
  const cauceCoords = calcularLineaCauce(limites);
  if (cauceCoords) {
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: cauceCoords },
      properties: {
        clase: "cauce",
        etiqueta: "Línea del cauce (referencia del río)",
        color: COLORES.cauce,
        orden: 3,
      },
    });
  }

  // Ordenar por orden para dibujar amarillo primero, rojo después, cauce al final
  features.sort((a, b) => a.properties.orden - b.properties.orden);

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

    if (clase === "cauce") {
      estilo = { color: COLORES.cauce, weight: 2, opacity: 0.9, dashArray: "6 8" };
    } else if (clase === "rojo") {
      estilo = { color: COLORES.rojo, weight: 2, fillColor: COLORES.rojo, fillOpacity: 0.35 };
    } else {
      estilo = { color: COLORES.amarillo, weight: 2, fillColor: COLORES.amarillo, fillOpacity: 0.18 };
    }

    const layer = L.geoJSON(f, { style: estilo });
    layer.bindPopup(
      `<strong>${f.properties.etiqueta}</strong><br>` +
      (f.properties.distancia_m !== undefined
        ? `Límite exterior: ${f.properties.distancia_m} m`
        : "Línea de referencia del cauce")
    );
    return layer;
  });

  bandaLayer = L.featureGroup(capas).addTo(mapInstance);
  return bandaLayer;
}

// Generar + dibujar (llamado una vez al iniciar o al cambiar umbrales manualmente)
function recalcularBandas(mapInstance, limites, rojoM, amarilloM) {
  if (!limites) {
    console.warn("No hay límites de faja para calcular bandas");
    return null;
  }

  bandasGeoJSON = generarBandas(limites, rojoM, amarilloM);
  return dibujarBandas(mapInstance, bandasGeoJSON);
}

window.GENERAR_BANDAS = generarBandas;
window.DIBUJAR_BANDAS = dibujarBandas;
window.RECALCULAR_BANDAS = recalcularBandas;
window.OBTENER_BANDAS = () => bandasGeoJSON;
