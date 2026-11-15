"use strict";

let edificiosGeoJSON = null;
let detectando = false;

function mostrarInfoEdificios(info) {
  const panel = document.getElementById("edificio-info");
  if (!panel) return;
  if (!info) {
    panel.textContent = "Selecciona un edificio detectado para ver su ficha.";
  } else if (info.total !== undefined) {
    panel.innerHTML = `<strong>${info.total} edificaciones en las franjas</strong><br>` +
      `Rojo: ${info.rojo} · Amarillo: ${info.amarillo}<p>Selecciona un contorno para ver su ficha.</p>`;
  } else {
    const p = info;
    panel.innerHTML = `<div class="chip ${esc(p.clase)}">${esc(p.etiqueta)}</div>` +
      `<p><strong>ID:</strong> ${esc(p.building_id)}<br>` +
      `<strong>Distancia al corredor rojo:</strong> ${Number(p.distance_m).toFixed(2)} m<br>` +
      `<strong>Distancia a la referencia central:</strong> ${Number(p.distance_axis_m).toFixed(2)} m<br>` +
      `<strong>Puntuación CNN:</strong> ${Number(p.confidence).toFixed(3)}</p>` +
      `<p>Se clasifica el contorno completo: si toca el rojo, tiene prioridad roja. La CNN detecta cubiertas; no confirma el uso residencial.</p>`;
  }
}

function dibujarEdificios(mapInstance, geojson) {
  if (edificioLayer) mapInstance.removeLayer(edificioLayer);
  edificiosGeoJSON = geojson;
  const features = (geojson?.features || []).filter(f => ["rojo", "amarillo"].includes(f.properties?.clase));
  edificioLayer = L.geoJSON({type: "FeatureCollection", features}, {
    style: f => ({color: f.properties.color, weight: 2, fillColor: f.properties.color, fillOpacity: 0.55}),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindPopup(`<strong>${esc(p.etiqueta)}</strong><br>Distancia al corredor: ${Number(p.distance_m).toFixed(2)} m<br>Puntuación CNN: ${Number(p.confidence).toFixed(3)}`);
      layer.on("click", () => mostrarInfoEdificios(p));
    },
  });
  if (document.getElementById("layer-edificios")?.checked !== false) edificioLayer.addTo(mapInstance);
  mostrarInfoEdificios({total: features.length, rojo: features.filter(f => f.properties.clase === "rojo").length,
                       amarillo: features.filter(f => f.properties.clase === "amarillo").length});
  return edificioLayer;
}

async function cargarEdificiosGeoJSON(ruta, mapInstance) {
  const resp = await fetch(ruta);
  if (!resp.ok) throw new Error("No se pudo cargar el resultado de la CNN.");
  return dibujarEdificios(mapInstance, await resp.json());
}

function mostrarEstadoDeteccion(manifest) {
  const counts = manifest.counts_by_class || {};
  document.getElementById("detect-status").textContent =
    `Inferencia completada: ${manifest.count} edificaciones en las franjas (rojo: ${counts.rojo || 0}; amarillo: ${counts.amarillo || 0})` +
    `${manifest.arquitectura ? ` · ${manifest.arquitectura}` : ""}. Revisa los contornos en el mapa.`;
}

async function cargarEstadoDetector() {
  const estado = document.getElementById("cnn-state");
  try {
    if (window.CHULLO_STATIC) {
      const resp = await fetch("outputs/detection/manifest.json");
      if (!resp.ok) throw new Error("No se pudo cargar el manifiesto publicado.");
      const manifest = await resp.json();
      await cargarEdificiosGeoJSON("outputs/detection/buildings.geojson", window.MAP());
      mostrarEstadoDeteccion(manifest);
      estado.textContent = "Resultados guardados";
      estado.className = "ready";
      document.getElementById("btn-run-detect").disabled = true;
      document.getElementById("btn-run-detect").textContent = "Nuevas inferencias: ejecutar servidor Python";
      document.getElementById("band-amarillo").disabled = true;
      document.getElementById("btn-recalcular-bandas").disabled = true;
      const note = document.createElement("p");
      note.className = "note";
      note.textContent = `Demo pública: explora las franjas y las ${manifest.count} detecciones guardadas. Aquí no se ejecuta una CNN nueva. Para probar la inferencia, sigue el README del repositorio.`;
      const link = document.createElement("a");
      link.href = "https://github.com/PauloUNSA/ProyectoFinal_GSTI#despliegue";
      link.textContent = " Ver instrucciones de despliegue";
      note.append(link);
      document.getElementById("detector-panel").append(note);
      return;
    }
    const resp = await fetch("/api/status");
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "No se pudo consultar el detector.");
    estado.textContent = data.cnn_disponible ? "Listo · modelo local" : "No disponible";
    estado.title = data.modelo || estado.title;
    const nota = document.getElementById("modelo-nota");
    if (nota && data.modelo) nota.textContent = `Modelo activo: ${data.modelo}. Requiere revisión de contornos: puede omitir edificios o unir techos. La proximidad no determina peligro ni permiso para construir.`;
    estado.className = data.cnn_disponible ? "ready" : "error";
    const btn = document.getElementById("btn-run-detect");
    btn.disabled = !data.cnn_disponible;
    if (data.error) document.getElementById("detect-status").textContent = data.error;
    if (data.manifest && data.manifest.zonas.amarillo_m === window.CONFIG.amarilloM) {
      await cargarEdificiosGeoJSON("/outputs/detection/buildings.geojson", window.MAP());
      mostrarEstadoDeteccion(data.manifest);
    }
  } catch (err) {
    estado.textContent = "No disponible";
    estado.className = "error";
    document.getElementById("detect-status").textContent = err.message;
  }
}

async function ejecutarDeteccion(imagenPath = "data/imagery/chullo/chullo_rgb.tif", umbral = null) {
  if (detectando) return;
  detectando = true;
  const btn = document.getElementById("btn-run-detect");
  const recalc = document.getElementById("btn-recalcular-bandas");
  const status = document.getElementById("detect-status");
  const estado = document.getElementById("cnn-state");
  btn.disabled = true;
  recalc.disabled = true;
  btn.textContent = "Procesando CNN…";
  status.textContent = "Analizando la imagen del corredor rojo y amarillo… Puede tardar varios minutos.";
  estado.textContent = "Procesando…";
  estado.className = "warning";
  try {
    // Sin umbral explícito, el servidor usa el recomendado para el modelo activo.
    const query = new URLSearchParams({imagen: imagenPath, amarillo: window.CONFIG.amarilloM});
    if (umbral !== null) query.set("umbral", umbral);
    const resp = await fetch(`/api/detect?${query}`);
    const resultado = await resp.json();
    if (!resp.ok || resultado.estado !== "completado") throw new Error(resultado.error || "No se completó la inferencia CNN.");
    await cargarEdificiosGeoJSON(resultado.geojson, window.MAP());
    mostrarEstadoDeteccion(resultado.manifest);
    estado.textContent = "Inferencia completada";
    estado.className = "ready";
    return resultado;
  } catch (err) {
    status.textContent = `No se completó la inferencia: ${err.message}`;
    estado.textContent = "Error CNN";
    estado.className = "error";
    return null;
  } finally {
    detectando = false;
    btn.disabled = false;
    recalc.disabled = false;
    btn.textContent = "Ejecutar detección CNN sobre imagen del sector";
  }
}

window.DIBUJAR_EDIFICIOS = dibujarEdificios;
window.EJECUTAR_DETECCION = ejecutarDeteccion;
window.CARGAR_EDIFICIOS_GEOJSON = cargarEdificiosGeoJSON;
window.CARGAR_ESTADO_DETECTOR = cargarEstadoDetector;
window.MOSTRAR_INFO_EDIFICIOS = mostrarInfoEdificios;
