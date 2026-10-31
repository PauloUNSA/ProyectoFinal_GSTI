"use strict";

/* ============================================================
   Chullo Unificado - detection.js
   Detección obligatoria de edificios con CNN (Mask R-CNN).
   Se ejecuta sobre imagen satelital y clasifica cada edificio
   por su distancia al cauce (línea obtenida uniendo los límites
   documentales de ANA), usando franjas con valores reales de ANA.
   ============================================================ */

let edificioLayer = null;
let edificiosGeoJSON = null;
let detectando = false;

const COLORES_EDIFICIO = {
  rojo: "#dc2626",
  amarillo: "#eab308",
  verde: "#16a34a",
  desconocido: "#66788b",
};

// Clasificar un edificio por su distancia al cauce, usando franjas ANA
function clasificarEdificio(distanciaM, rojoM, amarilloM) {
  const exterior = rojoM + amarilloM;
  if (distanciaM === null || distanciaM === undefined || !isFinite(distanciaM)) {
    return { clase: "desconocido", etiqueta: "Sin evaluación", color: COLORES_EDIFICIO.desconocido };
  }
  if (distanciaM <= rojoM) {
    return { clase: "rojo", etiqueta: "Rojo · dentro faja documental ANA", color: COLORES_EDIFICIO.rojo };
  }
  if (distanciaM <= rojoM + amarilloM) {
    return { clase: "amarillo", etiqueta: "Amarillo · franja de seguridad", color: COLORES_EDIFICIO.amarillo };
  }
  return { clase: "verde", etiqueta: "Verde · fuera de franjas ANA", color: COLORES_EDIFICIO.verde };
}

// Calcular distancia mínima desde un edificio (GeoJSON geometry) a la línea del cauce
function distanciaAlCauce(geometria, cauceCoords) {
  if (!cauceCoords || cauceCoords.length < 2) return null;

  // Para cada coordenada del edificio, calcular distancia al segmento más cercano del cauce
  // Aproximación: distancia euclidiana en grados (suficiente para visualización)
  let minDist = Infinity;

  const obtenerCoords = (geom) => {
    if (!geom) return [];
    if (geom.type === "Point") return [[geom.coordinates[0], geom.coordinates[1]]];
    if (geom.type === "MultiPoint") return geom.coordinates.map(c => [c[0], c[1]]);
    if (geom.type === "LineString") return geom.coordinates;
    if (geom.type === "MultiLineString") return geom.coordinates.flat();
    if (geom.type === "Polygon") return geom.coordinates.flat();
    if (geom.type === "MultiPolygon") return geom.coordinates.flat(2);
    return [];
  };

  const edificioCoords = obtenerCoords(geometria);

  for (const [lon, lat] of edificioCoords) {
    for (let i = 0; i < cauceCoords.length - 1; i++) {
      const [lon1, lat1] = cauceCoords[i];
      const [lon2, lat2] = cauceCoords[i + 1];
      const d = distanciaPuntoASegmento(lon, lat, lon1, lat1, lon2, lat2);
      if (d < minDist) minDist = d;
    }
  }

  if (minDist === Infinity) return null;
  // Convertir grados a metros aproximados (latitud de Arequipa ~ -16.4°)
  const mPorGradoLat = 111000;
  const mPorGradoLon = 111000 * Math.cos((-16.4 * Math.PI) / 180);
  // Promedio de conversión
  return minDist * ((mPorGradoLat + mPorGradoLon) / 2);
}

function distanciaPuntoASegmento(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (dx === 0 && dy === 0) {
    return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
  }
  const t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy);
  const tClamped = Math.max(0, Math.min(1, t));
  const closestX = x1 + tClamped * dx;
  const closestY = y1 + tClamped * dy;
  return Math.sqrt((px - closestX) ** 2 + (py - closestY) ** 2);
}

// Dibujar edificios detectados en el mapa
function dibujarEdificios(mapInstance, geojson, rojoM, amarilloM) {
  if (edificioLayer) {
    mapInstance.removeLayer(edificioLayer);
    edificioLayer = null;
  }

  if (!geojson || !geojson.features || geojson.features.length === 0) {
    mostrarInfoEdificios(null);
    return;
  }

  // Obtener línea del cauce para calcular distancias
  const cauce = window.OBTENER_CAUCE ? window.OBTENER_CAUCE() : null;
  const cauceCoords = cauce ? cauce.geometry.coordinates : null;

  const capas = geojson.features.map(f => {
    const props = f.properties || {};
    const distancia = cauceCoords ? distanciaAlCauce(f.geometry, cauceCoords) : (props.distance_m !== undefined ? props.distance_m : null);
    const clasificacion = clasificarEdificio(distancia, rojoM, amarilloM);
    const color = clasificacion.color;

    const estilo = {
      color,
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.5,
    };

    const layer = L.geoJSON(f, { style: estilo });

    const confianza = props.confidence !== undefined ? props.confidence : null;
    const distanciaTxt = distancia !== null ? distancia.toFixed(2) + " m" : "Sin datos";
    const confianzaTxt = confianza !== null ? confianza.toFixed(3) : "N/A";

    layer.bindPopup(
      `<div style="font:14px/1.5 system-ui,sans-serif;max-width:300px">` +
      `<strong style="color:${color}">${clasificacion.etiqueta}</strong><br>` +
      `Edificio <strong>${props.building_id || props.id || "N/A"}</strong><br>` +
      `Distancia al cauce: <strong>${distanciaTxt}</strong><br>` +
      `Puntuación CNN: <strong>${confianzaTxt}</strong><br>` +
      `<small>La proximidad usa los valores reales de ANA, no criterios ilustrativos.</small>` +
      `</div>`
    );

    layer.on("click", () => {
      mostrarInfoEdificios({
        id: props.building_id || props.id || "N/A",
        distancia,
        clasificacion,
        confianza,
        fuente: props.source_id || "CNN",
        observado: props.observed_at || "N/A",
      });
    });

    return layer;
  });

  edificioLayer = L.featureGroup(capas).addTo(mapInstance);
  edificiosGeoJSON = geojson;

  if (capas.length > 0 && capas.length <= 50) {
    const grupo = L.featureGroup(capas);
    mapInstance.fitBounds(grupo.getBounds(), { padding: [40, 40], maxZoom: 17 });
  }

  mostrarInfoEdificios({
    total: geojson.features.length,
    rojoM,
    amarilloM,
  });

  return edificioLayer;
}

// Mostrar resumen de edificios en el panel lateral
function mostrarInfoEdificios(info) {
  const panel = document.getElementById("edificio-info");
  if (!panel) return;

  if (!info) {
    panel.innerHTML = `<p class="vacio">No hay edificios detectados cargados.</p>`;
    return;
  }

  if (info.total !== undefined) {
    panel.innerHTML = `
      <strong>Edificios detectados (CNN): ${info.total}</strong><br>
      <small>Faja documental rojo: ${info.rojoM} m · Franja seguridad amarillo: ${info.amarilloM} m</small>
      <p class="vacio">Selecciona un edificio en el mapa para ver su ficha detallada.</p>
    `;
    return;
  }

  const chipClass = info.clasificacion.clase;
  const distanciaTxt = info.distancia !== null ? info.distancia.toFixed(2) + " m" : "Sin datos";
  const confianzaTxt = info.confianza !== null ? info.confianza.toFixed(3) : "N/A";

  panel.innerHTML = `
    <div class="chip ${chipClass}">${info.clasificacion.etiqueta}</div>
    <div style="margin-top:8px"><strong>ID:</strong> ${info.id}</div>
    <div><strong>Distancia al cauce:</strong> ${distanciaTxt}</div>
    <div><strong>Puntuación CNN:</strong> ${confianzaTxt}</div>
    <div><strong>Fuente:</strong> ${info.fuente}</div>
    <div><strong>Fecha observación:</strong> ${info.observado}</div>
    <p style="margin-top:10px;font-size:14px;color:#536259">
      La distancia se mide desde el punto más cercano del edificio a la línea del cauce
      (unión de los límites documentales de ANA). Verde no significa seguro ni edificable.
    </p>
  `;
}

// Ejecutar detección CNN vía API del servidor (obligatorio)
async function ejecutarDeteccion(imagenPath, umbral = 0.5) {
  if (detectando) {
    alert("Ya hay una detección en curso. Espera a que termine.");
    return;
  }

  detectando = true;
  const btn = document.getElementById("btn-run-detect");
  const btnHeader = document.getElementById("btn-detected");
  const status = document.getElementById("detect-status");
  const mapaEstado = document.getElementById("cnn-state");

  if (btn) { btn.disabled = true; btn.textContent = "Procesando CNN…"; }
  if (btnHeader) { btnHeader.disabled = true; btnHeader.textContent = "Procesando CNN…"; }
  if (status) status.innerHTML = `<p>Ejecutando detector CNN sobre imagen satelital… esto puede tardar varios minutos.</p>`;
  if (mapaEstado) { mapaEstado.textContent = "Procesando…"; mapaEstado.className = "warning"; }

  try {
    const query = new URLSearchParams({
      imagen: imagenPath,
      salida: "outputs/detection",
      umbral: umbral,
    }).toString();

    const resp = await fetch(`/api/detect?${query}`, { method: "GET" });
    const resultado = await resp.json();

    if (resultado.estado !== "completado") {
      throw new Error(resultado.error || "Error en la detección");
    }

    const salida = resultado.salida || "outputs/detection";
    const geojsonResp = await fetch(`${salida}/buildings.geojson`);
    if (!geojsonResp.ok) {
      throw new Error("No se pudo leer buildings.geojson generado");
    }
    const geojson = await geojsonResp.json();

    const cfg = window.OBTENER_CONFIG ? window.OBTENER_CONFIG() : { rojoM: 4, amarilloM: 20 };
    dibujarEdificios(map, geojson, cfg.rojoM, cfg.amarilloM);

    if (status) status.innerHTML = `<p style="color:var(--green)">Detección CNN completada: ${resultado.manifest ? resultado.manifest.count : "N/A"} edificios.</p>`;
    if (mapaEstado) { mapaEstado.textContent = "CNN activo"; mapaEstado.className = "ready"; }

    return resultado;
  } catch (err) {
    console.error(err);
    if (status) status.innerHTML = `<p style="color:#dc2626">Error: ${err.message}</p>`;
    if (mapaEstado) { mapaEstado.textContent = "Error CNN"; mapaEstado.className = "error"; }
    alert(`Error en la detección CNN: ${err.message}`);
  } finally {
    detectando = false;
    if (btn) { btn.disabled = false; btn.textContent = "Ejecutar detección CNN sobre imagen del sector"; }
    if (btnHeader) { btnHeader.disabled = false; btnHeader.textContent = "Detectar edificios (CNN)"; }
  }
}

// Cargar un archivo GeoJSON de edificios previamente generado
async function cargarEdificiosGeoJSON(ruta, mapInstance) {
  try {
    const resp = await fetch(ruta);
    if (!resp.ok) throw new Error(`No se pudo cargar ${ruta}`);
    const geojson = await resp.json();
    const cfg = window.OBTENER_CONFIG ? window.OBTENER_CONFIG() : { rojoM: 4, amarilloM: 20 };
    const cauce = window.OBTENER_CAUCE ? window.OBTENER_CAUCE() : null;
    // Recalcular distancias usando la línea del cauce
    return dibujarEdificios(mapInstance, geojson, cfg.rojoM, cfg.amarilloM);
  } catch (e) {
    console.error("Error cargando edificios:", e);
    return null;
  }
}

// Exportar
window.DIBUJAR_EDIFICIOS = dibujarEdificios;
window.EJECUTAR_DETECCION = ejecutarDeteccion;
window.CARGAR_EDIFICIOS_GEOJSON = cargarEdificiosGeoJSON;
window.MOSTRAR_INFO_EDIFICIOS = mostrarInfoEdificios;
window.CLASIFICAR_EDIFICIO = clasificarEdificio;
window.DISTANCIA_AL_CAUCE = distanciaAlCauce;
