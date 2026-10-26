const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:820}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.isTauri=true;window.pendingProposal=null;window.turns=[];window.decisions=[];
   window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'dialogue'},currentWebview:{label:'dialogue'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
    if(cmd==='chat_storage_settings')return {enabled:false,directory:'C:\\TestData\\Conversations'};
    if(cmd==='chat_storage_list')return {records:[],skipped:0};
    if(cmd==='llm_config_status')return {hasApiKey:true,baseUrl:'https://api.deepseek.com',model:'test',modelOptions:['test'],promptSource:'test',searchAvailable:true,searchBackend:'DeepSeek',contextChars:12000,searchMode:'off',projectReadEnabled:false};
    if(cmd==='billing_status'||cmd==='chat_export_list'||cmd==='project_settings_pending')return cmd==='project_settings_pending'&&window.pendingProposal?[structuredClone(window.pendingProposal)]:[];
    if(cmd==='chat_export_title')return '测试对话';
    if(cmd==='chat_stream'){
     window.turns.push(args.request.turnId);
     if(window.turns.length===1||window.turns.length===3)window.pendingProposal={id:'proposal-'+window.turns.length,session:args.request.sessionId,turn:args.request.turnId,page:'设置 → 通用',changes:[{key:'startupEnabled',label:'开机启动',before:true,after:false}]};
     return 'completed';
    }
    if(cmd==='project_settings_decide'){window.decisions.push(args);window.pendingProposal=null;return args.apply?'已修改':'已取消';}
    return 1;
   }};
  });
  await page.goto(process.env.PROJECT_SETTINGS_TEST_URL||'http://127.0.0.1:1420/?view=dialogue');
  await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  const badge=page.locator('.chat-current-conversation .chat-mode-badge');
  assert.equal(await badge.evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(255, 240, 229)');
  await page.getByRole('button',{name:'项目助手',exact:true}).click();
  assert.equal(await badge.getAttribute('data-mode'),'project');
  assert.equal(await badge.evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(253, 235, 238)');
  const input=page.getByLabel('Dialogue input');
  await input.fill('关闭开机启动');await input.press('Enter');
  const modal=page.getByRole('alertdialog',{name:'设置修改确认'});await modal.waitFor();
  assert.equal(await page.evaluate(()=>window.decisions.length),0);
  assert.equal(await modal.evaluate(node=>node.matches(':modal')),true);
  assert.equal(await page.evaluate(()=>document.activeElement.textContent),'取消');
  const position=await modal.boundingBox();assert(Math.abs(position.x+position.width/2-550)<2);assert(Math.abs(position.y+position.height/2-410)<2);
  if(process.env.CONFIRM_TEST_SCREENSHOT)await page.screenshot({path:process.env.CONFIRM_TEST_SCREENSHOT});
  await modal.getByRole('button',{name:'确认修改'}).click();
  const card=page.locator('.project-settings-result');await card.getByText('已修改',{exact:true}).waitFor();
  assert.equal(await modal.count(),0);assert.equal(await page.evaluate(()=>window.decisions.length),1);
  const firstAnchor=await card.evaluate(node=>node.parentElement.previousElementSibling?.getAttribute('data-role'));
  assert.equal(firstAnchor,'assistant');
  await input.fill('继续一个新问题');await input.press('Enter');
  await page.waitForFunction(()=>document.querySelectorAll('.dialogue-message[data-role="assistant"]').length===2);
  const placement=await card.evaluate(node=>{
   const thread=node.closest('.dialogue-thread'),assistants=[...thread.querySelectorAll('.dialogue-message[data-role="assistant"]')];
   return {afterFirst:node.parentElement.previousElementSibling===assistants[0],nextRole:node.parentElement.nextElementSibling?.getAttribute('data-role')};
  });
  assert.deepEqual(placement,{afterFirst:true,nextRole:'user'});
  await input.fill('取消这次修改');await input.press('Enter');await modal.waitFor();await page.keyboard.press('Escape');
  await page.waitForFunction(()=>window.decisions.length===2);
  assert.equal(await page.evaluate(()=>window.decisions.at(-1).apply),false);
  assert.equal(await page.locator('.project-settings-result').count(),2);
  await page.getByRole('button',{name:'新对话',exact:true}).click();await page.getByRole('button',{name:'开始新对话',exact:true}).click();
  assert.equal(await page.locator('.project-settings-result').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: settings proposal stays with its originating turn, uses concise copy, and clears with a new conversation');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
