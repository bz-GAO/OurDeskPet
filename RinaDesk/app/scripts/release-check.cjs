const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createServer}=require('node:net');
const {chromium}=require('playwright');
(async()=>{
 const config=JSON.parse(fs.readFileSync('src-tauri/tauri.conf.json','utf8'));
 assert.equal(config.identifier,'com.bzgao.ourdeskpet');
 assert.equal(config.mainBinaryName,'OurDeskPet');
 assert.deepEqual(fs.readdirSync('public/assets/rina').sort(),['alan-pixel-v1','boards','icon.svg']);
 assert.deepEqual(fs.readdirSync('public/assets/rina/boards'),['electronic-faithful.svg']);
 const port=await new Promise(resolve=>{const server=createServer();server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));});});
 const base=`http://127.0.0.1:${port}`;
 const vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{stdio:['ignore','ignore','inherit']});
 let browser;
 try{
  let ready=false;for(let i=0;i<100;i++){try{if((await fetch(base)).ok){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  if(!ready)throw new Error('Release UI preview did not start.');
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1080,height:900}}),errors=[],missing=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('response',response=>{if(response.status()===404&&response.request().resourceType()==='image')missing.push(response.url());});
  await page.addInitScript(()=>{
   window.isTauri=true;
   window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
   window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'settings'},currentWebview:{label:'settings'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
    if(cmd==='art_custom_list'||cmd==='billing_status'||cmd==='project_settings_pending')return [];
    if(cmd==='chat_storage_settings')return {enabled:false,directory:'example/Conversations'};
    if(cmd==='api_profiles_list')return {revision:'fixture',path:'fixture.env',active:'',profiles:[]};
    if(cmd==='chat_settings_get')return {revision:'fixture',options:{keep:8,trigger:12,summaryTarget:300,summaryCap:500,contextChars:12000,readTimeout:180,searchMode:'auto',searchEnabled:false,projectReadEnabled:false,projectSettingsEnabled:false}};
    if(cmd==='extension_status')return {id:'rinayaki',connected:true,available:true,embeddedReady:true,path:'fixture/yaki',version:'0.1.0',tools:[{id:'video',name:'视频翻译',available:true,embeddedReady:true},{id:'live',name:'实时翻译',available:true,embeddedReady:true}]};
    if(cmd==='extension_yaki_action'){if(args.action==='settings')return {settings:{defaultProjectDir:'fixture/output'}};if(args.action==='jobs')return {jobs:[]};return {};}
    return 1;
   }};
  });
  await page.goto(base+'/?view=settings');
  await page.locator('.art-catalog').waitFor();
  assert.equal(await page.locator('.art-catalog button:not(.art-add)').count(),1);
  assert.equal(await page.getByRole('button',{name:'已启用',exact:true}).isDisabled(),true);
  assert.equal(await page.locator('.art-catalog button').first().getAttribute('aria-pressed'),'true');
  assert((await page.locator('.art-catalog button').first().innerText()).includes('A.L.A.N 像素'));
  assert.equal(await page.getByRole('button',{name:/新增方案/}).count(),1,'user-created characters remain supported');
  await page.getByRole('button',{name:'扩展工具',exact:true}).click();
  await page.getByRole('button',{name:'视频翻译',exact:true}).waitFor();
  assert.equal(await page.locator('.extensions-add-tab,.extensions-manage').count(),0);
  assert.equal(await page.getByRole('button',{name:'实时翻译',exact:true}).count(),1);
  assert.equal(await page.getByRole('button',{name:'QQ Bot',exact:true}).count(),1);
  assert.deepEqual(missing,[]);assert.deepEqual(errors,[]);
  console.log('PASS release: independent app identity, single default pixel pack, custom import, built-in tools and no missing art');
 }finally{if(browser)await browser.close();vite.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
