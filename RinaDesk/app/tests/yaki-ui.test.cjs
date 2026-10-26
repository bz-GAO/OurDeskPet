const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:950}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.isTauri=true;
   window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   window.previewCalls=[];window.pendingPreviews=[];window.holdPreview=false;
   window.testJob={job:'fixture/job',projectName:'字幕测试',source:{source:'fixture.mp4',title:'测试'},state:{status:'awaiting_style',stage:'refinement'},prepared:{key:'test',speakers:{a:{start_ms:0,length_ms:1000,text:'第一句'},b:{start_ms:1000,length_ms:1000,text:'第二句'}}}};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'settings'},currentWebview:{label:'settings'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
    if(cmd==='chat_storage_settings')return {enabled:false,directory:'C:\\TestData\\Conversations'};
    if(cmd==='chat_storage_list')return {records:[],skipped:0};
    if(cmd==='plugin:window|get_all_windows')return [];
    if(cmd==='billing_status'||cmd==='project_settings_pending')return [];
    if(cmd==='chat_settings_get')return {revision:'0',hasKey:false,options:{keep:8,trigger:12,summaryTarget:300,summaryCap:500,contextChars:12000,readTimeout:180,searchMode:'auto',searchEnabled:false,projectReadEnabled:false,projectSettingsEnabled:false}};
    if(cmd==='api_profiles_list')return {revision:'0',path:'fixture.env',active:'',profiles:[]};
    if(cmd==='rinatomo_status')throw 'Not connected';
    if(cmd==='extension_status')return {id:'rinayaki',connected:true,available:true,embeddedReady:true,path:'fixture/yaki',tools:[{id:'video',name:'视频翻译',available:true,embeddedReady:true}]};
    if(cmd==='extension_select_destination')return 'fixture';
    if(cmd==='extension_yaki_action'){
     const {action,request}=args;
     if(action==='settings')return {settings:{defaultProjectDir:''}};
     if(action==='style_options')return {defaultFont:'font-a',fonts:[{label:'字体甲',value:'font-a'},{label:'字体乙',value:'font-b'}],presets:[{label:'默认',value:'#000000'},{label:'蓝色',value:'#616D87'}]};
     if(action==='scan')return {directory:'fixture',canCreate:true,jobs:[structuredClone(window.testJob)]};
     if(action==='status')return structuredClone(window.testJob);
     if(action==='style_preview'){
      window.previewCalls.push(request);
      const image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=#'+encodeURIComponent(JSON.stringify(request));
      if(window.holdPreview)return new Promise(resolve=>window.pendingPreviews.push(()=>resolve({image})));
      return {image};
     }
     throw 'Unexpected action '+action;
    }
    return 1;
   }};
  });
  await page.goto(process.env.YAKI_TEST_URL||'http://127.0.0.1:1420/?view=settings');
  await page.waitForTimeout(500);
  assert.deepEqual(errors,[]);
  await page.getByRole('button',{name:'扩展工具',exact:true}).click();
  await page.getByRole('button',{name:'视频翻译',exact:true}).click();
  await page.getByRole('button',{name:'选择项目文件夹'}).click();
  await page.getByRole('button',{name:/字幕测试/}).click();
  await page.getByRole('button',{name:'继续 · 字幕样式'}).click();
  const picture=page.getByAltText('字幕字体预览');
  await picture.waitFor();
  assert.equal(await page.getByLabel('字体',{exact:true}).inputValue(),'font-a');
  await page.evaluate(()=>{window.holdPreview=true;});
  await page.getByLabel('字体',{exact:true}).selectOption('font-b');
  await page.waitForFunction(()=>window.pendingPreviews.length===1);
  assert.equal(await picture.count(),0); // Never leave a stale font visible.
  await page.getByLabel('描边颜色',{exact:true}).selectOption('#616D87');
  await page.waitForFunction(()=>window.pendingPreviews.length===2);
  await page.evaluate(()=>window.pendingPreviews[1]());
  await picture.waitFor();const latest=await picture.getAttribute('src');
  await page.evaluate(()=>window.pendingPreviews[0]());
  assert.equal(await picture.getAttribute('src'),latest);
  assert.deepEqual(await page.evaluate(()=>window.previewCalls.at(-1)),{text:'第一句',font:'font-b',color:'#616D87'});
  await page.evaluate(()=>{window.holdPreview=false;});
  await page.getByLabel('说话人',{exact:true}).selectOption('b');
  await page.waitForFunction(()=>window.previewCalls.at(-1).text==='第二句');
  assert.equal(await page.getByLabel('字体',{exact:true}).inputValue(),'font-a');
  await page.getByLabel('十六进制描边颜色').fill('bad');
  assert.equal(await page.getByRole('button',{name:'继续 · 导出成片'}).isDisabled(),true);
  await page.evaluate(()=>{window.testJob.state={status:'running',stage:'download',completed:42,total:100};});
  await page.getByRole('button',{name:'返回进度'}).click();
  await page.waitForFunction(()=>document.querySelector('progress[aria-label="读取视频"]').value===42);
  await page.evaluate(()=>{window.testJob.state.total=0;});
  await page.waitForFunction(()=>!document.querySelector('progress[aria-label="读取视频"]').hasAttribute('value'));
  assert.deepEqual(errors,[]);
  console.log('PASS: shared font options, preview refresh/stale responses, speaker styles, invalid color and determinate/indeterminate download progress; mock IPC only.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
