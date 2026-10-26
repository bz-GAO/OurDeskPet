const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1100,height:850}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{
   window.isTauri=true;window.calls=[];window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   const settings=()=>JSON.parse(localStorage.getItem('storage-config')||'{"enabled":true,"directory":"C:/Test/Conversations"}');
   const read=()=>JSON.parse(localStorage.getItem('storage-docs')||'{}');
   const callbacks=new Map(),events=new Map();let serial=1;
   window.fireTestEvent=(event,payload)=>{for(const callback of events.get(event)||[])callbacks.get(callback)?.({event,payload});};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'dialogue'},currentWebview:{label:'dialogue'}},transformCallback:fn=>{const id=serial++;callbacks.set(id,fn);return id;},unregisterCallback:id=>callbacks.delete(id),invoke:async(cmd,args)=>{
    window.calls.push({cmd,args});
    if(cmd==='plugin:event|listen'){events.set(args.event,[...(events.get(args.event)||[]),args.handler]);return serial++;}
    if(cmd==='chat_storage_settings')return settings();
    if(cmd==='chat_storage_prepare_directory')return settings().directory;
    if(cmd==='plugin:opener|open_path')return null;
    if(cmd==='chat_storage_list')return {records:Object.values(read()).map(d=>d.storage).filter(r=>r.visible&&r.directory===settings().directory),skipped:0};
    if(cmd==='chat_storage_enable'){const next={...settings(),enabled:args.enabled};localStorage.setItem('storage-config',JSON.stringify(next));return next;}
    if(cmd==='chat_storage_save'){
     if(!settings().enabled)throw 'disabled';if(window.failSave)throw 'synthetic write failure';const docs=read(),key=args.directory+'|'+args.id,previous=docs[key];
     if(previous&&previous.storage.revision!==args.expected)throw 'conflict';
     const record={id:args.id,path:args.directory+'/conversation-'+args.id+'.json',directory:args.directory,title:args.request.title,mode:args.request.mode,revision:String(Number(previous?.storage.revision||0)+1),visible:previous?.storage.visible??true};
     docs[key]={...args.request,path:record.path,storage:record};localStorage.setItem('storage-docs',JSON.stringify(docs));return record;
    }
    if(cmd==='chat_storage_read')return read()[settings().directory+'|'+args.id];
    if(cmd==='chat_storage_forget'){const docs=read();docs[settings().directory+'|'+args.id].storage.visible=false;localStorage.setItem('storage-docs',JSON.stringify(docs));return null;}
    if(cmd==='chat_storage_delete'){const docs=read();delete docs[settings().directory+'|'+args.id];localStorage.setItem('storage-docs',JSON.stringify(docs));return null;}
    if(cmd==='chat_storage_rename'){const docs=read(),doc=docs[settings().directory+'|'+args.id];doc.title=args.title;doc.storage.title=args.title;doc.storage.revision=String(Number(doc.storage.revision)+1);localStorage.setItem('storage-docs',JSON.stringify(docs));return doc.storage;}
    if(cmd==='llm_config_status')return {hasApiKey:true,baseUrl:'https://example.test',model:'fake',searchMode:'off'};
    if(cmd==='billing_status'||cmd==='project_settings_pending')return [];
    if(cmd==='chat_stream'){await new Promise(resolve=>setTimeout(resolve,80));window.fireTestEvent('llm-chat-delta',{requestId:args.request.requestId,delta:'已检查设置。'});if(args.request.messages[0].content.includes('模式跳转测试'))window.fireTestEvent('agent-suggest-project',{requestId:args.request.requestId});return 'completed';}
    if(cmd==='chat_export_title')return '开机启动设置检查';
    return null;
   }};
  });
  await page.goto(process.env.CHAT_TEST_URL||'http://127.0.0.1:1420/?view=dialogue');
  await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  await page.getByRole('button',{name:'打开对话目录',exact:true}).click();
  await page.waitForFunction(()=>window.calls.some(c=>c.cmd==='plugin:opener|open_path'&&c.args.path==='C:/Test/Conversations'));
  const input=page.getByLabel('Dialogue input');
  await page.getByLabel('对话保存方式').selectOption('auto');
  await input.fill('请帮我看看这个项目的开机启动设置是否正确，并给出建议');await input.press('Enter');
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')||'{}')).some(d=>d.messages.length===2&&d.messages[1].state==='complete'));
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].title==='开机启动设置检查');
  const firstId=await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('storage-docs')))[0]);
  await input.fill('第二条同一文件');await input.press('Enter');
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].messages.length===4&&Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].messages[3].state==='complete');
  assert.deepEqual(await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('storage-docs')))),[firstId]);
  assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.cmd==='chat_export_title').length),1);
  await page.evaluate(()=>{const docs=JSON.parse(localStorage.getItem('storage-docs'));const doc=Object.values(docs)[0];doc.messages[3].state='cancelled';doc.messages[3].content='unfinished-checkpoint';doc.storage.revision=String(Number(doc.storage.revision)+1);localStorage.setItem('storage-docs',JSON.stringify(docs));});
  await page.reload();await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  await page.locator('.chat-conversation-select').first().click();
  await page.getByText('第二条同一文件',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.calls.find(c=>c.cmd==='restore_chat_history').args.messages.some(m=>m.content==='unfinished-checkpoint')),false);
  assert.equal(await page.locator('.chat-conversation-row[data-active]').count(),1);
  assert.equal(await page.getByLabel('当前对话标题').count(),0);
  assert.equal(await page.locator('.chat-conversation-select[aria-current="page"]').count(),1);
  await page.getByRole('button',{name:/^重命名 /}).click();
  await page.getByLabel('重命名对话').fill('本机保存测试');
  await page.getByLabel('重命名对话').press('Enter');
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].title==='本机保存测试');
  assert.deepEqual(await page.evaluate(()=>Object.keys(JSON.parse(localStorage.getItem('storage-docs')))),[firstId]);
  await page.getByLabel('对话保存方式').selectOption('off');
  const before=await page.evaluate(()=>localStorage.getItem('storage-docs'));
  await input.fill('不保存这一轮');await input.press('Enter');
  await page.waitForFunction(()=>!document.querySelector('button[aria-label="停止生成"]'));
  await page.waitForTimeout(400);
  assert.equal(await page.evaluate(()=>localStorage.getItem('storage-docs')),before);
  await page.getByLabel('对话保存方式').selectOption('auto');
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].messages.length===6);
  await page.evaluate(()=>{window.failSave=true;});
  await input.fill('触发模拟保存失败');await input.press('Enter');
  await page.waitForFunction(()=>!document.querySelector('button[aria-label="停止生成"]'));
  await page.locator('.settings-error').filter({hasText:'synthetic write failure'}).waitFor();
  await page.evaluate(()=>window.fireTestEvent('deskpet-before-quit'));
  await page.waitForFunction(()=>window.calls.some(c=>c.cmd==='chat_storage_flush_done'&&c.args.error!==null));
  assert.equal(await page.evaluate(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0].title),'本机保存测试');
  await page.evaluate(()=>{window.failSave=false;});
  await page.getByRole('button',{name:'重试保存',exact:true}).click();
  await page.evaluate(()=>window.fireTestEvent('deskpet-before-quit'));
  await page.waitForFunction(()=>window.calls.some(c=>c.cmd==='chat_storage_flush_done'&&c.args.error===null));
  const oldDocument=await page.evaluate(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0]);
  await page.evaluate(()=>{localStorage.setItem('storage-config',JSON.stringify({enabled:true,directory:'C:/Second/Conversations'}));window.fireTestEvent('deskpet-chat-storage-changed');});
  await page.waitForFunction(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs'))).length===2);
  assert.deepEqual(await page.evaluate(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0]),oldDocument);
  await page.getByRole('button',{name:'移除 本机保存测试',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'永久删除',exact:true}).click();
  await page.getByText('当前打开的对话不能删除，请先切换到其他对话。',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.calls.filter(c=>c.cmd==='chat_storage_delete').length),0);
  await page.getByRole('button',{name:'新对话',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'开始新对话',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.chat-conversation-select[aria-current="page"]').length===0);
  await page.getByRole('button',{name:'移除 本机保存测试',exact:true}).click();
  await page.getByRole('alertdialog').getByRole('button',{name:'永久删除',exact:true}).click();
  await page.waitForFunction(()=>Object.keys(JSON.parse(localStorage.getItem('storage-docs'))).length===1);
  assert.deepEqual(await page.evaluate(()=>Object.values(JSON.parse(localStorage.getItem('storage-docs')))[0]),oldDocument);
  await page.reload();await page.getByRole('button',{name:'展开侧边栏',exact:true}).click();
  assert.equal(await page.locator('.chat-conversation-select').count(),0);
  const finalInput=page.getByLabel('Dialogue input');
  await finalInput.fill('模式跳转测试：检查项目设置');await finalInput.press('Enter');
  const jump=page.getByRole('button',{name:'跳转',exact:true});await jump.waitFor();await jump.click();
  await page.getByRole('alertdialog').getByRole('button',{name:'跳转',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:'项目助手',exact:true}).getAttribute('aria-pressed'),'true');
  assert.equal(await page.getByLabel('Dialogue input').inputValue(),'模式跳转测试：检查项目设置');
  assert.deepEqual(errors,[]);
  console.log('PASS managed auto-save: directory open, stable identity, title, restart, rename, exit flush, current-record deletion guard and permanent deletion');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
