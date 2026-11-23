const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  const base = process.env.CHULLO_URL || 'http://127.0.0.1:4173';
  const out = process.env.CHULLO_QA_DIR || path.join(__dirname, 'outputs', 'qa');
  fs.mkdirSync(out, {recursive:true});
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage({viewport:{width:1500,height:1000}});
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));
  try {
    assert.equal((await page.goto(base)).status(),200);
    await page.waitForFunction(() => window.OBTENER_BANDAS?.()?.features?.length === 3);
    await page.waitForFunction(() => document.querySelector('#cnn-state').textContent !== 'Comprobando…');
    const serverStatus = await (await page.request.get(base + '/api/status')).json();
    if (serverStatus.manifest) {
      assert.equal(await page.locator('#cnn-state').textContent(),'Resultados guardados');
      assert.equal(await page.evaluate(() => edificioLayer.getLayers().length),serverStatus.manifest.count);
      for (const [clase, conteo] of Object.entries(serverStatus.manifest.counts_by_class)) {
        assert.equal(await page.locator(`#edificio-info strong.${clase}`).textContent(),String(conteo));
      }
    }
    const geometry = await page.evaluate(() => {
      const bands = window.OBTENER_BANDAS();
      const red = bands.features.filter(f => f.properties.clase === 'rojo');
      const orange = bands.features.find(f => f.properties.clase === 'naranja');
      const axis = bands.features.find(f => f.properties.clase === 'cauce');
      return {redCount:red.length, orange:!!orange.geometry.coordinates.length,
              open:JSON.stringify(axis.geometry.coordinates[0]) !== JSON.stringify(axis.geometry.coordinates.at(-1)),
              layerCount:window.MAP().hasLayer(bandaLayer), satelliteChecked:document.querySelector('#layer-satelital').checked};
    });
    assert.deepEqual(geometry,{redCount:1,orange:true,open:true,layerCount:true,satelliteChecked:true});
    await page.evaluate(() => window.MAP().setView([-16.3901,-71.5516],19));
    await page.waitForTimeout(1800);
    await page.screenshot({path:path.join(out,'franjas-corregidas.png'),fullPage:true});
    if (process.env.CHULLO_PREVIEW) await page.locator('#map').screenshot({path:process.env.CHULLO_PREVIEW});
    assert.equal(await page.locator('#band-amarillo, .map-legend').count(),0);
    assert.equal(await page.locator('#btn-run-detect, #btn-ver-cruce-amarillo, #faja-info, #detector-panel, #panel-info').count(),0);
    assert.equal(await page.locator('.leaflet-franjas-pane path[stroke="#eab308"]').count(),0);
    await page.locator('#layer-bandas').uncheck();
    assert.equal(await page.evaluate(() => window.MAP().hasLayer(bandaLayer)),false);
    await page.locator('#layer-bandas').check();
    // Un fallo de carga debe distinguirse de un resultado con cero contornos.
    await page.route('**/api/status',route => route.fulfill({status:500}));
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#cnn-state').textContent === 'No disponible');
    assert.equal(await page.locator('#edificio-info').textContent(),'No se pudieron cargar los contornos.');
    assert.deepEqual(errors,[]);
    console.log('PASS: geometría única, fajas marginales naranjas, eje oculto, controles y error CNN honesto.');
  } finally {
    await browser.close();
  }
})().catch(err => {console.error(err);process.exitCode=1;});
