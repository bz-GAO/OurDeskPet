const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:240,height:200}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/rest-effect-test',route=>route.fulfill({contentType:'text/html',body:`<div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;
   const React=(await import('/node_modules/.vite/deps/react.js')).default;import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
   const {PetRestVisual}=await import('/src/components/PetRestVisual.tsx');
   function Test(){const [sleeping,setSleeping]=React.useState(false);window.setSleeping=setSleeping;const src=sleeping?'/assets/rina/alan-pixel-v1/sleep.png':'/assets/rina/alan-pixel-v1/idle.png';return React.createElement(PetRestVisual,{src,sleeping,effect:'pixel-mask'});}
   ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Test));
  </script>`}));
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.goto(process.env.REST_EFFECT_TEST_URL||'http://127.0.0.1:1444/rest-effect-test');
  await page.waitForFunction(()=>window.setSleeping);
  await page.evaluate(()=>window.setSleeping(true));
  await page.locator('.pet-rest-fx[data-direction="sleep"]').waitFor();
  assert.match(await page.locator('.pet-rest-from').getAttribute('src'),/idle\.png$/);
  assert.match(await page.locator('.pet-rest-to').getAttribute('src'),/sleep\.png$/);
  assert.equal(await page.locator('.pet-rest-strip').count(),7);assert.equal(await page.locator('.pet-rest-fx i').count(),18);
  await page.waitForTimeout(900);assert.equal(await page.locator('.pet-rest-fx').count(),0);assert.match(await page.locator('.pet-image').getAttribute('src'),/sleep\.png$/);
  await page.evaluate(()=>window.setSleeping(false));await page.locator('.pet-rest-fx[data-direction="wake"]').waitFor();
  await page.waitForTimeout(900);assert.equal(await page.locator('.pet-rest-fx').count(),0);assert.match(await page.locator('.pet-image').getAttribute('src'),/idle\.png$/);
  await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>window.setSleeping(true));await page.waitForTimeout(50);
  assert.equal(await page.locator('.pet-rest-fx').count(),0);assert.match(await page.locator('.pet-image').getAttribute('src'),/sleep\.png$/);assert.deepEqual(errors,[]);
  console.log('PASS: pixel-mask sleep/wake swap, bounded glitch layers and reduced-motion bypass');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
