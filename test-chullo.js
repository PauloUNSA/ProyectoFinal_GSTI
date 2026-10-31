const { chromium } = require("playwright");

/**
 * Test de smoke para Chullo Unificado.
 * Verifica que la pagina carga sin errores de JS y que los elementos clave del DOM existen.
 */
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
    // Ignorar tiles de OpenStreetMap (requieren internet externo)
    if (url.includes("tile.openstreetmap.org")) return;
    loadFails.push(`${url} -> ${req.failure()?.errorText || "failed"}`);
  });

  const response = await page.goto("http://127.0.0.1:4173/", {
    waitUntil: "networkidle",
    timeout: 30000,
  });

  // Dar tiempo a que Leaflet y los modulos JS inicialicen
  await page.waitForTimeout(3000);

  const checks = {
    map: await page.locator("#map").count(),
    edificioInfo: await page.locator("#edificio-info").count(),
    panelInfo: await page.locator("#panel-info").count(),
    btnRunDetect: await page.locator("#btn-run-detect").count(),
    btnDetected: await page.locator("#btn-detected").count(),
    cnnState: await page.locator("#cnn-state").count(),
    mapState: await page.locator("#map-state").count(),
  };

  await page.screenshot({
    path: "chullo-test-screenshot.png",
    fullPage: true,
  });

  console.log("Status HTTP:", response.status());
  console.log("Elementos DOM:", JSON.stringify(checks, null, 2));
  console.log("\nErrores de JS:", jsErrors.length === 0 ? "Ninguno" : jsErrors.join("\n"));
  console.log("Fallas de carga (sin tiles OSM):", loadFails.length === 0 ? "Ninguna" : loadFails.join("\n"));

  const pass =
    response.status() === 200 &&
    checks.map > 0 &&
    jsErrors.length === 0 &&
    loadFails.length === 0;

  console.log("\nResultado:", pass ? "PASS" : "FAIL");

  await browser.close();
  process.exit(pass ? 0 : 1);
})();
