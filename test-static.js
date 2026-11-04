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
  await page.waitForFunction(()=>typeof edificiosGeoJSON!=='undefined' && edificiosGeoJSON?.features?.length===405);
  assert.equal(await page.locator('#btn-run-detect').isDisabled(),true);
  assert.equal(await page.locator('#btn-recalcular-bandas').isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.OBTENER_BANDAS().features.filter(f=>f.properties.clase==='rojo').length),1);
  await page.locator('#layer-edificios').uncheck();await page.locator('#layer-edificios').check();
  assert.deepEqual(api,[]);assert.deepEqual(errors,[]);
  console.log('PASS: demo bajo /dist/, 405 contornos, franjas, controles, sin peticiones API ni errores JS.');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
