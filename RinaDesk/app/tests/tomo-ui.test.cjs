const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:560,height:620}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.isTauri=true;window.tomoCalls=[];window.tomoLaunched=false;window.tomoStarted=false;
   window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   const offline={protocolVersion:1,provider:'rinatomo',available:false,owner:null,running:false,paused:false,state:'offline',napcat:'未连接',qq:'等待启动',shuttingDown:false,shutdownError:'',features:{ping:true,echo:false},llm:{enabled:false,effectiveModel:'未配置',minReplyInterval:0,timeoutSeconds:30,maxTokens:512,dailyTokenBudget:200000,maxInputChars:2000,maxConcurrentRequests:2},permissions:{adminUsers:[],privateWhitelist:[],enabledGroups:[]},autoStart:false,notifications:{enabled:true,nightSleepEnabled:true,nightStart:'22:00',nightEnd:'08:00',events:{translation:true,chatReply:false,loginFailure:true}},login:{required:false,message:'',qrcodeDataUrl:''}};
   const ready={...offline,available:true};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'settings'},currentWebview:{label:'settings'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
    window.tomoCalls.push({cmd,args});
    if(cmd==='rinatomo_launch'){window.tomoLaunched=true;return null;}
    if(cmd==='rinatomo_status')return window.tomoStarted?{...ready,running:true,login:{required:true,message:'请扫码',qrcodeDataUrl:''}}:window.tomoLaunched?ready:offline;
    if(cmd==='rinatomo_action'&&args.action==='start'){window.tomoStarted=true;return {...ready,running:true,login:{required:true,message:'请扫码',qrcodeDataUrl:''}};}
    return ready;
   }};
  });
  const url=process.env.TOMO_TEST_URL;
  await page.route('**/tomo-ui-test',route=>route.fulfill({contentType:'text/html',body:`<style>html,body,#root{margin:0;width:100%;height:100%}</style><div id="root"></div><script type="module">
   import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;
   const React=(await import('/node_modules/.vite/deps/react.js')).default;
   const {createRoot}=(await import('/node_modules/.vite/deps/react-dom_client.js')).default;
   const Page=(await import('/src/extensions/rinatomo/RinaTomoPage.tsx')).default;
   createRoot(document.getElementById('root')).render(React.createElement(Page));
  </script>`}));
  await page.goto(url);
  await page.waitForTimeout(500);
  if(errors.length)throw new Error(`Tomo test page failed: ${errors.join(' | ')}`);
  await page.getByRole('button',{name:'启动 Tomo',exact:true}).click();
  await page.getByRole('dialog',{name:'扫码登录 QQ'}).waitFor();
  await page.getByText('请扫码',{exact:true}).waitFor();
  const calls=await page.evaluate(()=>window.tomoCalls.map(call=>call.cmd+(call.args?.action?`:${call.args.action}`:'')));
  assert.equal(calls.filter(call=>call==='rinatomo_launch').length,1);
  assert.equal(calls.filter(call=>call==='rinatomo_action:start').length,1,'one click starts the Tomo pipeline');
  await page.getByRole('button',{name:'关闭登录层'}).click();
  const layout=await page.evaluate(()=>{
   const row=document.querySelector('.tomo-night-range'),inputs=[...row.querySelectorAll('input[type=time]')];
   const bounds=row.getBoundingClientRect(),rects=inputs.map(input=>input.getBoundingClientRect());
   return {rowRight:bounds.right,widths:rects.map(rect=>rect.width),rights:rects.map(rect=>rect.right),overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};
  });
  assert(layout.widths.every(width=>width>80));
  assert(layout.rights.every(right=>right<=layout.rowRight+1));
  assert.equal(layout.overflow,0,'Tomo settings must not overflow horizontally');
  assert.deepEqual(errors,[]);
  console.log('PASS Tomo: one-click launch reaches QR login and compact settings stay aligned');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
