const assert = require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
 const server=spawn('python',['-m','http.server','4187','--bind','127.0.0.1'],{stdio:'ignore'});
 let browser;
 try {
  browser=await chromium.launch({headless:true}); const page=await browser.newPage();
  const errors=[];const api=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))api.push(r.url())});
  for(let i=0;i<30;i++){try{await page.goto('http://127.0.0.1:4187/dist/');break;}catch(e){await new Promise(r=>setTimeout(r,200));}}
  const total=(await (await page.request.get('http://127.0.0.1:4187/dist/outputs/detection/manifest.json')).json()).count;
  await page.waitForFunction(n=>edificioLayer?.getLayers().length===n,total);
  assert.equal(await page.locator('#cnn-state').textContent(),'Resultados guardados');
  assert.match(await page.locator('#edificio-info').textContent(),/Amarillo: [1-9]\d*/);
  assert.equal(await page.locator('#btn-run-detect, #btn-ver-cruce-amarillo, #faja-info, #detector-panel, #panel-info').count(),0);
  assert.equal(await page.locator('#band-amarillo').count(),0);
  assert.equal(await page.evaluate(()=>window.OBTENER_BANDAS().features.filter(f=>f.properties.clase==='rojo').length),1);
  for (const [clase,expected] of [['rojo','Rojo · cauce y riberas (aproximado)'],['naranja','Naranja · faja marginal (aproximada)'],['amarillo','Amarillo · alcance simulado de huaicos (aproximado)']]) {
    await page.evaluate(clase=>{
      const layer=edificioLayer.getLayers().find(l=>l.feature.properties.clase===clase);
      layer.openPopup();
    },clase);
    assert.equal(await page.locator('.leaflet-popup-content').textContent(),expected);
    await page.locator('.leaflet-popup-close-button').click();
  }
  const huella = page.locator('.leaflet-huellaHuaico-pane path');
  await huella.first().waitFor({state:'visible'});
  const visible = await huella.count();
  await page.locator('#layer-huaico').uncheck();
  assert.equal(await huella.count(), 0);
  await page.locator('#layer-huaico').check();
  assert.equal(await huella.count(), visible);
  assert.equal((await page.request.get('http://127.0.0.1:4187/dist/huaicos.html')).status(), 200);
  await page.locator('#layer-edificios').uncheck();await page.locator('#layer-edificios').check();
  assert.deepEqual(api,[]);assert.deepEqual(errors,[]);
  console.log(`PASS: demo bajo /dist/, ${total} contornos, franjas, controles, sin peticiones API ni errores JS.`);
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
