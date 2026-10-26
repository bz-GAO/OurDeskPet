const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.isTauri=true;window.nativeMinimized=false;window.calls=[];window.position={x:100,y:100};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},transformCallback:()=>1,unregisterCallback:()=>{},
    invoke:async(cmd,args)=>{
     window.calls.push({cmd,phase:document.querySelector('[data-phase]')?.dataset.phase});
     if(cmd==='plugin:window|is_minimized')return window.nativeMinimized;
     if(cmd==='plugin:window|is_visible')return true;
     if(cmd==='plugin:window|minimize'){
      if(window.failMinimize)throw Error('native failure');
      window.nativeMinimized=true;window.position={x:-32000,y:-32000};return;
     }
     if(cmd==='plugin:window|current_monitor')return {name:'test',position:{x:0,y:0},size:{width:1000,height:800},scaleFactor:1,workArea:{position:{x:0,y:0},size:{width:1000,height:760}}};
     if(cmd==='plugin:window|outer_position')return window.position;
     if(cmd==='plugin:window|outer_size')return {width:280,height:410};
     if(cmd==='plugin:window|set_position'){
      if(window.failFit)throw Error('fit failure');
      window.position=args.position;return;
     }
     return 1;
    }};
  });
  await page.route('**/restore-test',route=>route.fulfill({contentType:'text/html',body:`<div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;
   const React=(await import('/node_modules/.vite/deps/react.js')).default;
   const {createRoot}=(await import('/node_modules/.vite/deps/react-dom_client.js')).default;
   const {usePetTeleport}=await import('/src/pet/usePetTeleport.ts');
   const {usePetRestore}=await import('/src/pet/usePetRestore.ts');
   const {useKeepPetOnScreen,clampVisiblePetPosition}=await import('/src/pet/useKeepPetOnScreen.ts');window.clampVisiblePetPosition=clampVisiblePetPosition;
   function Test(){const t=usePetTeleport(false,'skin');window.restore=usePetRestore(true,t);useKeepPetOnScreen(true,t.move);return React.createElement('div',{'data-phase':t.phase});}
   window.root=createRoot(document.getElementById('root'));window.root.render(React.createElement(Test));
  </script>`}));
  await page.goto(process.env.RESTORE_TEST_URL||'http://127.0.0.1:1444/restore-test');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.waitForFunction(()=>window.restore);
  const geometry=await page.evaluate(()=>({
   transparentMargin:window.clampVisiblePetPosition({x:-50,y:100},{width:280,height:410},{position:{x:0,y:0},size:{width:1000,height:760}},1),
   tinyOverflow:window.clampVisiblePetPosition({x:-52,y:100},{width:280,height:410},{position:{x:0,y:0},size:{width:1000,height:760}},1),
   scaled:window.clampVisiblePetPosition({x:-63,y:100},{width:350,height:513},{position:{x:0,y:0},size:{width:1250,height:950}},1.25)
  }));
  assert.deepEqual(geometry.transparentMargin,{x:-50,y:100});
  assert.deepEqual(geometry.tinyOverflow,{x:-50,y:100});
  assert.deepEqual(geometry.scaled,{x:-63,y:100});
  await page.waitForTimeout(100);
  await page.evaluate(()=>window.restore.minimize());
  assert.equal(await page.locator('[data-phase]').getAttribute('data-phase'),'hidden');
  await page.waitForTimeout(700);
  assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.cmd==='plugin:window|set_position').length),0);
  await page.evaluate(()=>{window.nativeMinimized=false;window.position={x:900,y:600};document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='in');
  const move=await page.evaluate(()=>window.calls.find(c=>c.cmd==='plugin:window|set_position'));
  assert.equal(move.phase,'hidden');
  await page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='idle');
  await page.waitForTimeout(700);
  assert.equal(await page.locator('[data-phase]').getAttribute('data-phase'),'idle');
  await page.evaluate(()=>{window.failMinimize=true;return window.restore.minimize().catch(()=>{});});
  await page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='idle');
  await page.evaluate(()=>{window.failMinimize=false;return window.restore.minimize();});
  await page.evaluate(()=>{window.failFit=true;window.nativeMinimized=false;window.position={x:900,y:600};document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='idle');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>{window.failFit=false;return window.restore.minimize();});
  await page.evaluate(()=>{window.nativeMinimized=false;window.position={x:100,y:100};document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.querySelector('[data-phase]').dataset.phase==='idle');
  assert.deepEqual(errors,[]);console.log('PASS restore: visible-pet bounds, DPI rounding, concealed minimize, sentinel ignored, hidden placement, appear only, no replay and failure recovery');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
