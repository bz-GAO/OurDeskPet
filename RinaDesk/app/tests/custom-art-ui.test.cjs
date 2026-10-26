const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.isTauri=true;window.artReads=0;window.regionCalls=[];
   window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'settings'},currentWebview:{label:'settings'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
    if(cmd==='set_pet_region'){window.regionCalls.push(args);return null;}
    if(cmd==='art_custom_list'){window.artReads++;return JSON.parse(localStorage.getItem('test-art-packs')||'[]');}
    if(cmd==='art_custom_save'){
     if(window.failSave)throw new Error('模拟写入失败');
     const saved={...args.request,id:args.request.id||'rina-custom-1-test',code:'CUSTOM-TEST'};
     localStorage.setItem('test-art-packs',JSON.stringify([saved]));return saved;
    }
    if(cmd==='art_custom_rename'){
     const packs=JSON.parse(localStorage.getItem('test-art-packs')||'[]'),pack=packs.find(item=>item.id===args.id);pack.label=args.label;localStorage.setItem('test-art-packs',JSON.stringify(packs));return pack;
    }
    if(cmd==='art_custom_delete'){localStorage.setItem('test-art-packs',JSON.stringify(JSON.parse(localStorage.getItem('test-art-packs')||'[]').filter(item=>item.id!==args.id)));return null;}
    if(cmd==='api_profiles_list')return {revision:'test',path:'test.env',active:'legacy',profiles:[]};
    if(cmd==='extension_status')return {connected:false,available:false,tools:[]};
    if(cmd==='billing_status')return [];
    if(cmd==='chat_storage_settings')return {enabled:true,directory:'test'};
    if(cmd==='chat_settings_get')return {revision:'test',options:{keep:8,trigger:12,summaryTarget:300,summaryCap:500,contextChars:12000,readTimeout:180,searchMode:'auto',searchEnabled:true,searchUrl:'',projectReadEnabled:true,projectSettingsEnabled:true}};
    return 1;
   }};
  });
  const url=process.env.ART_TEST_URL||'http://127.0.0.1:1432/?view=settings';
  await page.route('**/drag-region-test',route=>route.fulfill({contentType:'text/html',body:`
   <style>body{margin:0}.pet-select-button{position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:180px;height:162px}</style>
   <div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;
   const React=(await import('/node_modules/.vite/deps/react.js')).default;
   const {createRoot}=(await import('/node_modules/.vite/deps/react-dom_client.js')).default;
   const {usePetHitRegion}=await import('/src/pet/usePetHitRegion.ts');
   function Test(){const [drag,setDrag]=React.useState(false),[board,setBoard]=React.useState(false);window.setDrag=setDrag;window.setBoard=setBoard;usePetHitRegion(board,drag);return React.createElement(React.Fragment,null,React.createElement('button',{className:'pet-select-button'},'pet'),board&&React.createElement('section',{className:'pet-board-popup',style:{position:'absolute',left:42,top:94,width:196,height:145}},'board'));}
   createRoot(document.getElementById('root')).render(React.createElement(Test));
   </script>`}));
  await page.setViewportSize({width:280,height:410});
  await page.goto(new URL('/drag-region-test',url).href);
  await page.waitForFunction(()=>window.regionCalls.at(-1)?.rects[0].width===180);
  await page.evaluate(()=>window.setDrag(true));
  await page.waitForFunction(()=>window.regionCalls.at(-1)?.dragSpace===true);
  assert.deepEqual(await page.evaluate(()=>window.regionCalls.at(-1).rects[0]),{x:-70,y:180,width:420,height:230});
  await page.setViewportSize({width:420,height:410});
  await page.waitForFunction(()=>window.regionCalls.at(-1)?.viewportWidth===420);
  assert.equal(await page.evaluate(()=>window.regionCalls.at(-1).rects[0].x),0);
  await page.evaluate(()=>window.setDrag(false));
  await page.waitForTimeout(120);
  assert.equal(await page.evaluate(()=>window.regionCalls.at(-1).dragSpace),true,'release keeps the drones visible');
  await page.evaluate(()=>window.setDrag(true));
  await page.waitForTimeout(270);
  assert.equal(await page.evaluate(()=>window.regionCalls.at(-1).dragSpace),true,'a new drag cancels the pending shrink');
  await page.evaluate(()=>window.setDrag(false));
  await page.waitForFunction(()=>window.regionCalls.at(-1)?.dragSpace===false);
  assert.equal(await page.evaluate(()=>window.regionCalls.at(-1).rects[0].width),180);
  await page.evaluate(()=>window.setBoard(true));
  await page.waitForFunction(()=>window.regionCalls.at(-1)?.rects.length===2);
  assert.deepEqual(await page.evaluate(()=>window.regionCalls.at(-1).rects[1]),{x:30,y:82,width:220,height:169},'board region includes animated star clearance');
  await page.setViewportSize({width:1100,height:900});
  await page.goto(url);
  assert.deepEqual(await page.locator('.art-tab .settings-disclosure>summary strong').allTextContents(),['人物','主题','高级特效','音效']);
  assert.deepEqual(await page.locator('.art-tab .settings-disclosure').evaluateAll(items=>items.map(item=>item.open)),[true,false,false,true]);
  const flow=await page.locator('.art-tab .settings-disclosure').evaluateAll(items=>{
   const first=items[0].getBoundingClientRect(),summary=items[0].querySelector('summary').getBoundingClientRect(),body=items[0].querySelector('.settings-disclosure-body').getBoundingClientRect(),next=items[1].getBoundingClientRect();
   return {position:getComputedStyle(items[0].querySelector('summary')).position,summaryBottom:summary.bottom,bodyTop:body.top,firstBottom:first.bottom,nextTop:next.top};
  });
  assert.equal(flow.position,'static');
  assert(flow.bodyTop>=flow.summaryBottom-1,'expanded content must begin below its summary');
  assert(flow.nextTop>=flow.firstBottom-1,'next section must follow the expanded section in document flow');
  await page.locator('.art-catalog button').filter({hasText:'璃奈 · A.L.A.N 像素'}).click();
  const dragDemo=page.getByLabel('璃奈 · A.L.A.N 像素拖动效果').locator('.art-state-demo');
  await dragDemo.locator('.alan-drone-escort[data-phase="move"]').waitFor();
  const droneBounds=await dragDemo.evaluate(node=>{
   const host=node.getBoundingClientRect();
   return [...node.querySelectorAll('.alan-drone')].map(drone=>{const rect=drone.getBoundingClientRect();return {left:rect.left-host.left,right:rect.right-host.left,width:rect.width,hostWidth:host.width};});
  });
  assert.equal(droneBounds.length,2);
  for(const drone of droneBounds){
   assert(drone.left>=-0.5,`drone clipped at left: ${JSON.stringify(drone)}`);
   assert(drone.right<=drone.hostWidth+0.5,`drone clipped at right: ${JSON.stringify(drone)}`);
   assert(drone.width>20,`drone unexpectedly collapsed: ${JSON.stringify(drone)}`);
  }
  await page.locator('.art-tab .settings-disclosure>summary').filter({hasText:'高级特效'}).click();
  const effectDemo=page.locator('.effect-preview').first();
  await effectDemo.locator('.alan-drone-escort[data-phase="move"]').waitFor();
  const effectBounds=await effectDemo.evaluate(node=>{
   const host=node.getBoundingClientRect();
   return [...node.querySelectorAll('.alan-drone')].map(drone=>{const rect=drone.getBoundingClientRect();return {left:rect.left-host.left,right:rect.right-host.left,width:rect.width,hostWidth:host.width};});
  });
  for(const drone of effectBounds){
   assert(drone.left>=-0.5&&drone.right<=drone.hostWidth+0.5,`effect preview clips drone: ${JSON.stringify(drone)}`);
  }
  await page.locator('.art-tab .settings-disclosure>summary').filter({hasText:'音效'}).click();
  assert.equal(await page.locator('.voice-sfx input[type="checkbox"]').first().isChecked(),true,'malformed/legacy bridge payload falls back without crashing settings');
  await page.getByRole('button',{name:'新增方案',exact:false}).click();
  await page.getByLabel('方案名称').fill('本机人物');
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==','base64');
  for(let i=0;i<4;i++)await page.locator('.art-upload input').nth(i).setInputFiles({name:'character.png',mimeType:'image/png',buffer:png});
  // A settings tab switch must preserve the unfinished custom pack.
  await page.getByRole('button',{name:'Chat',exact:true}).click();
  await page.getByRole('button',{name:'美术',exact:true}).click();
  assert.equal(await page.getByLabel('方案名称').inputValue(),'本机人物');
  await page.evaluate(()=>window.failSave=true);
  await page.getByRole('button',{name:'保存方案',exact:true}).click();
  await page.getByRole('alert').getByText('模拟写入失败',{exact:false}).waitFor();
  assert.equal(await page.locator('.art-upload img').count(),4);
  await page.evaluate(()=>window.failSave=false);
  await page.getByRole('button',{name:'保存方案',exact:true}).click();
  await page.getByRole('heading',{name:'本机人物',exact:true}).waitFor();
  await page.getByRole('button',{name:'启用此方案',exact:true}).click();
  await page.reload();
  await page.getByRole('heading',{name:'本机人物',exact:true}).waitFor();
  await page.getByRole('button',{name:'已启用',exact:true}).waitFor();
  assert.equal(await page.getByAltText('固定璃奈板').getAttribute('src'),'/assets/rina/boards/electronic-faithful.svg');
  await page.getByRole('button',{name:'重命名 本机人物',exact:true}).click();
  await page.getByLabel('重命名人物方案').fill('本机人物改名');
  await page.getByRole('button',{name:'确定',exact:true}).click();
  await page.getByRole('heading',{name:'本机人物改名'}).waitFor();
  assert.equal(await page.getByRole('button',{name:/删除/}).count(),1,'only custom packs expose delete');
  assert.equal(await page.getByText('璃奈 · Astromeda（原版）',{exact:true}).count(),0);
  await page.locator('.settings-disclosure>summary').filter({hasText:'主题'}).click();
  await page.getByRole('button',{name:'粉色',exact:true}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.rinaTheme),'rose');
  await page.reload();
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.rinaTheme),'rose');
  await page.locator('.art-catalog button').filter({hasText:'本机人物改名'}).click();
  await page.getByRole('button',{name:'删除',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'确认',exact:true}).click();
  await page.getByText('本机人物改名',{exact:true}).waitFor({state:'detached'});
  assert(await page.evaluate(()=>window.artReads<15),'art reads should not loop');
  if(process.env.ART_SCREENSHOT)await page.screenshot({path:process.env.ART_SCREENSHOT});
  for(const width of [1100,760,560]){await page.setViewportSize({width,height:800});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  assert.deepEqual(errors,[]);
  console.log('PASS custom art: draft retention, save, quick rename, theme persistence, custom-only delete, fixed board');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
