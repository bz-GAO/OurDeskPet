const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const renderer=fs.readFileSync(path.join(__dirname,'../src/components/PetTeleportEffect.tsx'),'utf8');
 assert.match(renderer,/function LegacyScanlineEffect/);
 assert.match(renderer,/ACTIVE_TELEPORT_EFFECT:TeleportEffectStyle='quantum'/);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error(e.message);});
  await page.route('**/teleport-test',route=>route.fulfill({contentType:'text/html',body:`<div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';
   RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;
   const React=(await import('/node_modules/.vite/deps/react.js')).default;
   import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';
   const {createRoot}=ReactDOM;
   const {usePetTeleport}=await import('/src/pet/usePetTeleport.ts');
   const {PetView}=await import('/src/components/PetView.tsx');
   function Test(){const [blocked,setBlocked]=React.useState(false);const [skin,setSkin]=React.useState('one');const api=usePetTeleport(blocked,skin);window.api=api;window.block=setBlocked;window.skin=setSkin;return React.createElement('div',{'data-phase':api.phase},React.createElement(PetView,{controller:{state:'idle',view:{image:'/assets/rina/rina-idle-v1.png'},follow:()=>{},idle:()=>{}},teleportPhase:api.phase}));}
   window.moves=[];createRoot(document.getElementById('root')).render(React.createElement(Test));
  </script>`}));
  await page.goto(process.env.TELEPORT_TEST_URL||'http://127.0.0.1:1444/teleport-test');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.waitForFunction(()=>window.api);
  await page.waitForTimeout(50);
  const phase=()=>page.locator('[data-phase]').getAttribute('data-phase');
  const idle=()=>page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='idle');
  await page.evaluate(()=>{void window.api.move(async()=>window.moves.push('first'));});
  await page.waitForTimeout(100);assert.equal(await phase(),'out');assert.deepEqual(await page.evaluate(()=>window.moves),[]);
  assert.equal(await page.locator('[data-teleport-effect]').getAttribute('data-teleport-effect'),'quantum');
  assert.equal(await page.locator('.pet-quantum-fx').count(),1);
  assert.equal(await page.locator('.pet-teleport-fx-legacy').count(),0);
  await page.screenshot({path:process.env.TELEPORT_SCREENSHOT||'teleport-integrated.png'});
  await page.waitForTimeout(700);assert.equal(await phase(),'in');assert.deepEqual(await page.evaluate(()=>window.moves),['first']);await idle();
  await page.evaluate(()=>{void window.api.move(async()=>window.moves.push('cancelled'));window.api.cancel();});
  await page.waitForTimeout(800);assert.equal(await phase(),'idle');assert.deepEqual(await page.evaluate(()=>window.moves),['first']);
  await page.evaluate(()=>{void window.api.move(async()=>{throw Error('simulated native failure');});});await page.waitForTimeout(800);await idle();
  await page.evaluate(()=>{void window.api.move(async()=>window.moves.push('skin-cancel'));window.skin('two');});await page.waitForTimeout(800);await idle();
  await page.evaluate(()=>{void window.api.move(async()=>window.moves.push('drag-cancel'));window.block(true);});await page.waitForTimeout(800);await idle();
  assert.deepEqual(await page.evaluate(()=>window.moves),['first']);
  await page.evaluate(()=>window.block(false));await page.waitForTimeout(30);
  await page.evaluate(()=>{void window.api.move(async()=>window.moves.push('queued-first'));void window.api.move(async()=>window.moves.push('obsolete'));void window.api.move(async()=>window.moves.push('latest'));});
  await page.waitForTimeout(2800);await idle();assert.deepEqual(await page.evaluate(()=>window.moves),['first','queued-first','latest']);
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>window.api.move(async()=>window.moves.push('reduced')));assert.equal(await phase(),'idle');
  assert.equal(await page.evaluate(()=>window.moves.at(-1)),'reduced');assert.deepEqual(errors,[]);
  console.log('PASS: move timing, failure recovery, cancellation, skin/drag interruption, latest queue and reduced motion');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
