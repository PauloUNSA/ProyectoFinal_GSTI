"use strict";

/* ============================================================
   Chullo Unificado - detection.js
   Interfaz de detección de edificios con CNN (Mask R-CNN).
   Llama al endpoint /api/detect del servidor local.
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

// Clasificar un edificio por su distancia al eje de la torrentera
function clasificarEdificio(distanciaM, rojoM, amarilloM) {
  const exterior = rojoM + amarilloM;
  if (distanciaM === null || distanciaM === undefined || !isFinite(distanciaM)) {
    return { clase: "desconocido", etiqueta: "Sin evaluación", color: COLORES_EDIFICIO.desconocido };
  }
  if (distanciaM <= rojoM) {
    return { clase: "rojo", etiqueta: "Rojo · proximidad inmediata", color: COLORES_EDIFICIO.rojo };
  }
  if (distanciaM <= rojoM + amarilloM) {
    return { clase: "amarillo", etiqueta: "Amarillo · proximidad intermedia", color: COLORES_EDIFICIO.amarillo };
  }
  return { clase: "verde", etiqueta: "Verde · mayor distancia", color: COLORES_EDIFICIO.verde };
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

  const capas = geojson.features.map(f => {
    const props = f.properties || {};
    const distancia = props.distance_m !== undefined ? props.distance_m : null;
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
      `<small>La proximidad no determina peligro ni permiso para construir.</small>` +
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

  // Ajustar vista a los edificios si hay pocos
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
      <strong>Edificios detectados: ${info.total}</strong><br>
      <small>Límite rojo: ${info.rojoM} m · Ancho amarillo: ${info.amarilloM} m</small>
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
      La distancia se mide desde el punto más cercano del edificio al eje de la torrentera.
      Verde no significa seguro ni edificable.
    </p>
  `;
}

// Ejecutar detección CNN vía API del servidor
async function ejecutarDeteccion(imagenPath, umbral = 0.5) {
  if (detectando) {
    alert("Ya hay una detección en curso. Espera a que termine.");
    return;
  }

  detectando = true;
  const btn = document.getElementById("btn-run-detect");
  const status = document.getElementById("detect-status");
  const mapaEstado = document.getElementById("cnn-state");

  if (btn) { btn.disabled = true; btn.textContent = "Procesando…"; }
  if (status) status.innerHTML = `<p>Ejecutando detector CNN… esto puede tardar varios minutos.</p>`;
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

    // Cargar el GeoJSON de edificios generado
    const salida = resultado.salida || "outputs/detection";
    const geojsonResp = await fetch(`${salida}/buildings.geojson`);
    if (!geojsonResp.ok) {
      throw new Error("No se pudo leer buildings.geojson generado");
    }
    const geojson = await geojsonResp.json();

    const cfg = window.CONFIG_BANDAS ? window.CONFIG_BANDAS() : { rojoM: 25, amarilloM: 25 };
    dibujarEdificios(map, geojson, cfg.rojoM, cfg.amarilloM);

    if (status) status.innerHTML = `<p style="color:var(--green)">Detección completada: ${resultado.manifest ? resultado.manifest.count : "N/A"} edificios.</p>`;
    if (mapaEstado) { mapaEstado.textContent = "Detectado"; mapaEstado.className = "ready"; }

    return resultado;
  } catch (err) {
    console.error(err);
    if (status) status.innerHTML = `<p style="color:#dc2626">Error: ${err.message}</p>`;
    if (mapaEstado) { mapaEstado.textContent = "Error"; mapaEstado.className = "error"; }
    alert(`Error en la detección: ${err.message}`);
  } finally {
    detectando = false;
    if (btn) { btn.disabled = false; btn.textContent = "Ejecutar detección sobre imagen del sector"; }
  }
}

// Cargar un archivo GeoJSON de edificios previamente generado
async function cargarEdificiosGeoJSON(ruta, mapInstance) {
  try {
    const resp = await fetch(ruta);
    if (!resp.ok) throw new Error(`No se pudo cargar ${ruta}`);
    const geojson = await resp.json();
    const cfg = window.CONFIG_BANDAS ? window.CONFIG_BANDAS() : { rojoM: 25, amarilloM: 25 };
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
