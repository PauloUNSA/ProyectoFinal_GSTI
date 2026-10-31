const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const jsErrors = [];
  const loadFails = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") jsErrors.push(msg.text());
  });
  page.on("pageerror", (err) => jsErrors.push(err.message));
  page.on("requestfailed", (req) => {
    const url = req.url();
    if (url.includes("tile.openstreetmap.org")) return;
    loadFails.push(`${url} -> ${req.failure()?.errorText || "failed"}`);
  });

  const response = await page.goto("http://127.0.0.1:4173/", {
    waitUntil: "networkidle",
    timeout: 30000,
  });

  await page.waitForTimeout(3000);

  console.log("Status HTTP:", response.status());

  const mapaSucio = {
    mapControls: await page.locator(".map-controls").count(),
    leafletControlLayers: await page.locator(".leaflet-control-layers").count(),
    mapLegend: await page.locator(".map-legend").count(),
  };
  console.log("Elementos que NO deberían estar en el mapa:", JSON.stringify(mapaSucio, null, 2));

  const panelLateral = {
    edificioInfo: await page.locator("#edificio-info").count(),
    fajaInfo: await page.locator("#faja-info").count(),
    detectorPanel: await page.locator("#detector-panel").count(),
    controlesPanel: await page.locator("#controles-panel").count(),
    btnRunDetect: await page.locator("#btn-run-detect").count(),
  };
  console.log("Elementos del panel lateral:", JSON.stringify(panelLateral, null, 2));

  const detectResp = await page.request.get(
    "http://127.0.0.1:4173/api/detect?imagen=data%2Fimagery%2Fchullo%2Fchullo_rgb.tif&salida=outputs%2Fdetection&umbral=0.5"
  );
  const detectBody = await detectResp.json();
  console.log("\nRespuesta /api/detect:", JSON.stringify(detectBody, null, 2));

  const btn = page.locator("#btn-run-detect");
  if ((await btn.count()) > 0) {
    await btn.click();
    await page.waitForTimeout(4000);
    const status = await page.locator("#detect-status").textContent();
    console.log("\nEstado tras clic en deteccion:\n", status);
  }

  await page.screenshot({ path: "chullo-test-screenshot.png", fullPage: true });

  console.log("\n=== ERRORES DE CONSOLA JS ===");
  if (jsErrors.length === 0) {
    console.log("Ninguno. ¡Limpio!");
  } else {
    jsErrors.forEach((e, i) => console.log(`${i + 1}. ${e}`));
  }

  console.log("\n=== FALLAS DE CARGA (sin tiles OSM) ===");
  if (loadFails.length === 0) {
    console.log("Ninguna.");
  } else {
    loadFails.forEach((e, i) => console.log(`${i + 1}. ${e}`));
  }

  const mapaLimpio =
    mapaSucio.mapControls === 0 &&
    mapaSucio.leafletControlLayers === 0 &&
    mapaSucio.mapLegend === 0;

  const panelOk =
    panelLateral.edificioInfo > 0 &&
    panelLateral.fajaInfo > 0 &&
    panelLateral.detectorPanel > 0 &&
    panelLateral.controlesPanel > 0 &&
    panelLateral.btnRunDetect > 0;

  const sinErrores500 = !jsErrors.some((e) => e.includes("500") || e.includes("Failed to fetch"));
  const detectOk = detectResp.status() === 200;

  const pass =
    response.status() === 200 &&
    mapaLimpio &&
    panelOk &&
    jsErrors.length === 0 &&
    sinErrores500 &&
    detectOk;

  console.log("\n=== RESULTADO ===");
  console.log("Mapa limpio:", mapaLimpio ? "OK" : "FALLA");
  console.log("Panel lateral OK:", panelOk ? "OK" : "FALLA");
  console.log("Sin errores JS:", jsErrors.length === 0 ? "OK" : "FALLA");
  console.log("Sin error 500/failed to fetch:", sinErrores500 ? "OK" : "FALLA");
  console.log("Endpoint /api/detect HTTP 200:", detectOk ? "OK" : "FALLA");
  console.log("Resultado final:", pass ? "PASS" : "FAIL");

  await browser.close();
  process.exit(pass ? 0 : 1);
})();
