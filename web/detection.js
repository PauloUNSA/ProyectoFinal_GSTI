"use strict";

let edificiosGeoJSON = null;
let detectando = false;
const clasesCubiertas = ["rojo", "naranja", "amarillo"];
const resultadosVersion = "20261123-cruce-a7270";

function mostrarInfoEdificios(info) {
  const panel = document.getElementById("edificio-info");
  if (!panel) return;
  if (!info) {
    panel.textContent = "Selecciona un contorno candidato para ver su ficha.";
  } else if (info.total !== undefined) {
    panel.innerHTML = `<strong>${info.total} contornos candidatos en las zonas analizadas</strong><br>` +
      `Rojo: ${info.rojo} · Naranja: ${info.naranja} · Amarillo: ${info.amarillo}<p>Selecciona un contorno para ver su ficha.</p>`;
  } else {
    const p = info;
    panel.innerHTML = `<div class="chip ${esc(p.clase)}">${esc(p.etiqueta)}</div>` +
      `<p><strong>ID:</strong> ${esc(p.building_id)}<br>` +
      `<strong>Distancia al cauce/riberas aproximados:</strong> ${Number(p.distance_m).toFixed(2)} m<br>` +
      `<strong>Puntuación del detector:</strong> ${Number(p.confidence).toFixed(3)} (no es una probabilidad calibrada)</p>` +
      `<p>Se cruza el contorno completo. La prioridad es rojo, naranja y amarillo. La CNN propone cubiertas. El amarillo indica un cruce aproximado con el área simulada de huaicos.</p>`;
  }
}

function dibujarEdificios(mapInstance, geojson) {
  if (edificioLayer) mapInstance.removeLayer(edificioLayer);
  edificiosGeoJSON = geojson;
  const features = (geojson?.features || []).filter(f => clasesCubiertas.includes(f.properties?.clase));
  const mapa = mapInstance.getContainer();
  const leyenda = mapa.parentElement.querySelector(".map-legend");
  const espacioLeyenda = leyenda
    ? Math.max(12, leyenda.getBoundingClientRect().bottom - mapa.getBoundingClientRect().top + 12)
    : 12;
  edificioLayer = L.geoJSON({type: "FeatureCollection", features}, {
    style: f => ({color: f.properties.clase === "amarillo" ? "#7c4a06" : f.properties.color, weight: 2, fillColor: f.properties.color, fillOpacity: f.properties.clase === "amarillo" ? 0.68 : 0.55}),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindPopup(`<strong>${esc(p.etiqueta)}</strong><br>Distancia al rojo aproximado: ${Number(p.distance_m).toFixed(2)} m<br>Puntuación del detector: ${Number(p.confidence).toFixed(3)}<br>Contorno candidato pendiente de revisión.`,
        {autoPanPaddingTopLeft: [12, espacioLeyenda], maxWidth: 300});
      layer.on("click", () => mostrarInfoEdificios(p));
    },
  });
  if (document.getElementById("layer-edificios")?.checked !== false) edificioLayer.addTo(mapInstance);
  const counts = Object.fromEntries(clasesCubiertas.map(clase => [clase, 0]));
  for (const feature of features) counts[feature.properties.clase]++;
  mostrarInfoEdificios({total: features.length, ...counts});
  const boton = document.getElementById("btn-ver-cruce-amarillo");
  const mejoresCruces = edificioLayer.getLayers().filter(layer => layer.feature.properties.clase === "amarillo");
  mejoresCruces.sort((a, b) => b.feature.properties.confidence - a.feature.properties.confidence);
  boton.hidden = !mejoresCruces.length;
  boton.onclick = () => {
    const capa = mejoresCruces[0];
    if (!capa) return;
    if (!mapInstance.hasLayer(edificioLayer)) {
      document.getElementById("layer-edificios").checked = true;
      edificioLayer.addTo(mapInstance);
    }
    mapInstance.setView(capa.getBounds().getCenter(), 19, {animate: false});
    mostrarInfoEdificios(capa.feature.properties);
    capa.openPopup();
    document.getElementById("map").scrollIntoView({block: "center"});
  };
  return edificioLayer;
}

async function cargarEdificiosGeoJSON(ruta, mapInstance) {
  const resp = await fetch(ruta);
  if (!resp.ok) throw new Error("No se pudo cargar el resultado de la CNN.");
  return dibujarEdificios(mapInstance, await resp.json());
}

function mostrarEstadoDeteccion(manifest) {
  const counts = manifest.counts_by_class || {};
  const cobertura = manifest.zonas?.huella_cobertura_imagen_pct;
  const detalle = Number.isFinite(cobertura)
    ? ` La imagen abarca el ${cobertura.toLocaleString("es-PE")}% de la zona amarilla.`
    : " Esta corrida previa abarca cauce y fajas marginales.";
  document.getElementById("detect-status").textContent =
    `Inferencia completada: ${manifest.count} candidatos. Rojo: ${counts.rojo || 0} · Naranja: ${counts.naranja || 0}` +
    (Number.isFinite(cobertura) ? ` · Amarillo: ${counts.amarillo || 0}.` : ".") + detalle;
}

async function cargarEstadoDetector() {
  const estado = document.getElementById("cnn-state");
  try {
    if (window.CHULLO_STATIC) {
      const resp = await fetch(`outputs/detection/manifest.json?v=${resultadosVersion}`);
      if (!resp.ok) throw new Error("No se pudo cargar el manifiesto publicado.");
      const manifest = await resp.json();
      await cargarEdificiosGeoJSON(`outputs/detection/buildings.geojson?v=${resultadosVersion}`, window.MAP());
      mostrarEstadoDeteccion(manifest);
      estado.textContent = "Resultados guardados";
      const notaModelo = document.getElementById("modelo-nota");
      if (notaModelo && manifest.arquitectura) {
        notaModelo.textContent = `Resultados guardados de ${manifest.arquitectura} (${manifest.modelo}). Requiere revisión de contornos: puede omitir edificios o unir techos. La proximidad no determina peligro ni permiso para construir.`;
      }
      estado.className = "ready";
      document.getElementById("btn-run-detect").disabled = true;
      document.getElementById("btn-run-detect").textContent = "Nuevas inferencias: ejecutar servidor Python";
      const note = document.createElement("p");
      note.className = "note";
      note.textContent = `Demo pública: explora los resultados de una corrida del modelo sobre las zonas de Chullo. Aquí no se ejecuta una CNN nueva. Para probar la inferencia, sigue el README del repositorio.`;
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
    if (data.manifest) {
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
  const status = document.getElementById("detect-status");
  const estado = document.getElementById("cnn-state");
  btn.disabled = true;
  btn.textContent = "Procesando CNN…";
  status.textContent = "Buscando cubiertas en el cauce, las fajas marginales y la huella de huaicos… Puede tardar varios minutos.";
  estado.textContent = "Procesando…";
  estado.className = "warning";
  try {
    // Sin umbral explícito, el servidor usa el recomendado para el modelo activo.
    const query = new URLSearchParams({imagen: imagenPath, amarillo: 0});
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
    btn.textContent = "Ejecutar detección CNN sobre imagen del sector";
  }
}

window.DIBUJAR_EDIFICIOS = dibujarEdificios;
window.EJECUTAR_DETECCION = ejecutarDeteccion;
window.CARGAR_EDIFICIOS_GEOJSON = cargarEdificiosGeoJSON;
window.CARGAR_ESTADO_DETECTOR = cargarEstadoDetector;
window.MOSTRAR_INFO_EDIFICIOS = mostrarInfoEdificios;
