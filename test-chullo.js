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
      await page.waitForFunction(total => edificiosGeoJSON?.features?.length === total, serverStatus.manifest.count);
      assert.equal(await page.evaluate(() => edificioLayer.getLayers().length),serverStatus.manifest.count);
    }
    const geometry = await page.evaluate(() => {
      const bands = window.OBTENER_BANDAS();
      const red = bands.features.filter(f => f.properties.clase === 'rojo');
      const yellow = bands.features.find(f => f.properties.clase === 'amarillo');
      const axis = bands.features.find(f => f.properties.clase === 'cauce');
      return {redCount:red.length, yellowRings:yellow.geometry.coordinates.length,
              open:JSON.stringify(axis.geometry.coordinates[0]) !== JSON.stringify(axis.geometry.coordinates.at(-1)),
              layerCount:window.MAP().hasLayer(bandaLayer), satelliteChecked:document.querySelector('#layer-satelital').checked};
    });
    assert.deepEqual(geometry,{redCount:1,yellowRings:2,open:true,layerCount:true,satelliteChecked:true});
    await page.evaluate(() => window.MAP().setView([-16.3901,-71.5516],19));
    await page.waitForTimeout(1800);
    await page.screenshot({path:path.join(out,'franjas-corregidas.png'),fullPage:true});
    if (process.env.CHULLO_PREVIEW) await page.locator('#map').screenshot({path:process.env.CHULLO_PREVIEW});
    await page.locator('#band-amarillo').fill('30');
    await page.locator('#btn-recalcular-bandas').click();
    await page.waitForFunction(() => window.OBTENER_BANDAS().metadata.amarillo_m === 30);
    assert.match(await page.locator('#panel-info').textContent(),/30 m/);
    await page.locator('#layer-bandas').uncheck();
    assert.equal(await page.evaluate(() => window.MAP().hasLayer(bandaLayer)),false);
    await page.locator('#layer-bandas').check();
    // Prueba de UI con un fallo explícito: nunca debe mostrar éxito/0 edificios.
    await page.route('**/api/detect?*',route => route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({estado:'error',error:'Imagen de prueba inválida'})}));
    await page.locator('#btn-run-detect').click();
    await page.waitForFunction(() => document.querySelector('#cnn-state').textContent === 'Error CNN');
    assert.match(await page.locator('#detect-status').textContent(),/Imagen de prueba inválida/);
    assert.equal(await page.locator('#btn-run-detect').isEnabled(),true);
    assert.equal(await page.locator('#btn-recalcular-bandas').isEnabled(),true);
    assert.deepEqual(errors,[]);
    console.log('PASS: geometría única, hueco amarillo, eje abierto, controles y error CNN honesto.');
  } finally {
    await browser.close();
  }
})().catch(err => {console.error(err);process.exitCode=1;});
