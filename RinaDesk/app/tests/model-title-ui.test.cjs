const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const scenario of ['success','manual','failure']){
   const page=await browser.newPage();
   await page.addInitScript(()=>{
    window.isTauri=true;window.calls=[];
    window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
    const callbacks=new Map(),events=new Map();let serial=1;
    window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'dialogue'},currentWebview:{label:'dialogue'}},transformCallback:fn=>{const id=serial++;callbacks.set(id,fn);return id;},unregisterCallback:()=>{},invoke:async(cmd,args)=>{
     window.calls.push(cmd);
     if(cmd==='plugin:event|listen'){events.set(args.event,[...(events.get(args.event)||[]),args.handler]);return serial++;}
     if(cmd==='llm_config_status')return {hasApiKey:true,model:'fake',searchMode:'off'};
     if(cmd==='billing_status'||cmd==='project_settings_pending')return [];
     if(cmd==='chat_storage_settings')return {enabled:false,directory:'fixture'};
     if(cmd==='chat_storage_list')return {records:[],skipped:0};
     if(cmd==='chat_stream'){
      for(const id of events.get('llm-chat-delta')||[])callbacks.get(id)({payload:{requestId:args.request.requestId,delta:'这是一个完整的回复。'}});
      return 'completed';
     }
     if(cmd==='chat_export_title')return new Promise((resolve,reject)=>{window.finishTitle=()=>resolve('模型概括的标题');window.failTitle=()=>reject('test failure');});
     return null;
    }};
   });
   await page.goto(process.env.CHAT_TEST_URL||'http://127.0.0.1:1444/?view=dialogue');
   await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
   const input=page.getByLabel('Dialogue input'),title=page.getByLabel('当前对话标题');
   await input.fill('请帮我看看这个项目的设置');await input.press('Enter');
   await page.waitForFunction(()=>Boolean(window.finishTitle));
   const fallback=await title.inputValue();
   if(scenario==='manual')await title.fill('我的标题');
   await page.evaluate(fail=>fail?window.failTitle():window.finishTitle(),scenario==='failure');
   if(scenario==='success')await page.waitForFunction(()=>document.querySelector('input[aria-label="当前对话标题"]').value==='模型概括的标题');
   else {await page.waitForTimeout(100);assert.equal(await title.inputValue(),scenario==='manual'?'我的标题':fallback);}
   await input.fill('继续');await input.press('Enter');
   await page.waitForTimeout(250);
   assert.equal(await page.evaluate(()=>window.calls.filter(cmd=>cmd==='chat_export_title').length),1);
   await page.close();
  }
  console.log('PASS model titles: asynchronous replacement, manual rename wins, failure fallback, once per session');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
