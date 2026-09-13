const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:960,height:808}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.isTauri=true;
  window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
  window.testCalls=[];
  window.testSnapshot={revision:'0',path:'test.env',active:'legacy',profiles:[{id:'legacy',name:'现有配置',baseUrl:'https://example.test/v1',model:'old',hasKey:true,ready:true,readOnly:true}]};
  window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'settings'},currentWebview:{label:'settings'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
   window.testCalls.push({cmd,args});
   if(cmd==='plugin:window|get_all_windows')return [];
   if(cmd==='api_profiles_list')return structuredClone(window.testSnapshot);
   if(cmd==='api_profiles_save'){
    const r=args.request;const s=window.testSnapshot;if(r.revision!==s.revision)throw '配置文件已在外部修改';
    s.profiles=s.profiles.filter(p=>p.id!==r.id);s.profiles.push({id:r.id,name:r.name||r.id,baseUrl:r.baseUrl,model:r.model,hasKey:true,ready:true,readOnly:false});s.revision=String(Number(s.revision)+1);return structuredClone(s);
   }
   if(cmd==='api_profiles_activate'){window.testSnapshot.active=args.id;window.testSnapshot.revision=String(Number(window.testSnapshot.revision)+1);return structuredClone(window.testSnapshot);}
   return 1;
  }};
 });
 await page.goto('http://127.0.0.1:1420/?view=settings');
 const beforeArt=await page.evaluate(()=>localStorage.getItem('rinadesk.art-pack'));
 await page.getByRole('button',{name:/Astromeda/}).click();
 assert.equal(await page.evaluate(()=>localStorage.getItem('rinadesk.art-pack')),beforeArt);
 await page.getByRole('button',{name:'启用此方案'}).click();
 assert.equal(await page.evaluate(()=>localStorage.getItem('rinadesk.art-pack')),'rina-astromeda-v1');
 await page.getByRole('button',{name:/冬服/}).click();
 await page.getByRole('button',{name:'启用此方案'}).click();
 await page.getByRole('button',{name:'API 配置',exact:true}).click();
 await page.getByLabel('配置代号').fill('ds');await page.getByLabel('显示名称').fill('测试方案');
 await page.getByLabel('基础地址 URL').fill('https://example.test/v1');await page.getByLabel('模型 Model').fill('demo');await page.getByLabel('API Key',{exact:true}).fill('fake-test-key');
 await page.getByRole('button',{name:'保存配置',exact:true}).click();
 await page.getByRole('button',{name:'使用此配置',exact:true}).waitFor();
 assert.equal(await page.getByLabel('API Key',{exact:true}).inputValue(),'');
 await page.getByRole('button',{name:'使用此配置',exact:true}).click();
 await page.getByRole('button',{name:'当前使用中',exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>window.testSnapshot.active),'ds');
 await page.getByLabel('模型 Model').fill('demo2');await page.getByRole('button',{name:'保存配置',exact:true}).click();
 await page.getByRole('status').waitFor();
 assert.equal(await page.evaluate(()=>window.testCalls.filter(c=>c.cmd==='api_profiles_save').at(-1).args.request.key),null);
 await page.evaluate(()=>{window.testSnapshot.profiles.find(p=>p.id==='ds').model='external';window.testSnapshot.revision='9';window.dispatchEvent(new Event('focus'));});
 await page.waitForFunction(()=>document.querySelector('input[placeholder="模型的准确名称"]').value==='external');
 await page.getByLabel('模型 Model').fill('unsaved');
 await page.evaluate(()=>{window.testSnapshot.revision='10';window.dispatchEvent(new Event('focus'));});
 await page.locator('.settings-warning').waitFor();
 assert.equal(await page.getByLabel('模型 Model').inputValue(),'unsaved');
 assert.equal(await page.getByRole('button',{name:'保存配置',exact:true}).isDisabled(),true);
 page.on('dialog',d=>d.accept());
 await page.getByRole('button',{name:'重新载入',exact:true}).click();
 await page.getByRole('button',{name:'最小化设置',exact:true}).click();
 await page.getByRole('button',{name:'关闭设置',exact:true}).click();
 const calls=await page.evaluate(()=>window.testCalls.map(c=>c.cmd));
 assert(calls.includes('plugin:window|minimize'));assert(calls.includes('plugin:window|close'));assert(!calls.includes('quit_app'));
 assert.deepEqual(errors,[]);
 await page.setViewportSize({width:760,height:640});
 await page.getByRole('button',{name:'保存配置',exact:true}).scrollIntoViewIfNeeded();
 assert.equal(await page.getByRole('button',{name:'保存配置',exact:true}).isVisible(),true);
 await page.setViewportSize({width:280,height:410});
 await page.goto('http://127.0.0.1:1420/');
 await page.locator('.pet-select-button').click();
 const smile=page.getByRole('button',{name:'设置',exact:true});
 assert.equal(await smile.getAttribute('title'),'设置');
 await smile.hover();
 await page.waitForFunction(()=>getComputedStyle(document.querySelector('.board-settings-highlight')).opacity==='1');
 await smile.click();
 await page.waitForFunction(()=>window.testCalls.some(c=>c.cmd==='plugin:webview|create_webview_window'));
 const settingsCreate=await page.evaluate(()=>window.testCalls.find(c=>c.cmd==='plugin:webview|create_webview_window').args.options);
 assert.equal(settingsCreate.label,'settings');assert.equal(settingsCreate.url,'/?view=settings');
 await page.locator('.pet-select-button').click({button:'right'});
 await page.locator('.pet-select-button').click();
 assert.equal(await page.locator('.pet-settings-face').count(),0);
 console.log('PASS: art switch, API add/save/activate, key preservation, external refresh/conflict, window-only controls, small viewport, smile launch, sleep gating; mock IPC with fake credentials.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
