const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1000,height:800}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.isTauri=true;window.testCalls=[];
  window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
  window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'dialogue'},currentWebview:{label:'dialogue'}},transformCallback:()=>1,unregisterCallback:()=>{},invoke:async(cmd,args)=>{
   window.testCalls.push({cmd,args});
   if(cmd==='chat_storage_settings')return {enabled:true,directory:'C:\\TestData\\Conversations'};
   if(cmd==='chat_storage_list')return {records:[],skipped:0};
   if(cmd==='billing_balance'){
    if(args.account.startsWith('bailian:')&&window.holdAliyun)await new Promise(resolve=>{window.releaseAliyun=resolve;});
    return args.account.startsWith('deepseek:')?{values:[['CNY',window.testBalance??'12.34']],updatedAt:'2026-10-13T12:00:00Z',message:''}:{values:[],updatedAt:'',message:'余额查询未连接'};
   }
   if(cmd==='billing_status'&&window.delayBilling){window.delayBilling=false;await new Promise(resolve=>{window.releaseBilling=resolve;});}
   if(cmd==='billing_status')return [
    {id:'deepseek:sample',label:'DeepSeek',day:'2026-10-13',incomplete:false,balance:{values:[['CNY','12.34']],updatedAt:'2026-10-13T12:00:00Z',message:''},today:{amount_micro:window.testAmount??23456,calls:3,unknown:0,tokens:1200},history:[
     {day:'2026-10-07',amount_micro:0,calls:0,unknown:0,tokens:0},{day:'2026-10-08',amount_micro:1000,calls:1,unknown:0,tokens:100},{day:'2026-10-09',amount_micro:2000,calls:1,unknown:0,tokens:100},{day:'2026-10-10',amount_micro:3000,calls:1,unknown:0,tokens:100},{day:'2026-10-11',amount_micro:4000,calls:1,unknown:0,tokens:100},{day:'2026-10-12',amount_micro:5000,calls:1,unknown:0,tokens:100},{day:'2026-10-13',amount_micro:23456,calls:3,unknown:0,tokens:1200}
    ]},
    {id:window.changedAccount?'bailian:replacement':'bailian:sample',label:'阿里云百炼',active:true,day:'2026-10-13',incomplete:false,billingConnected:localStorage.getItem('test-billing-connected')==='1',balance:{values:[],updatedAt:'',message:'余额查询未连接'},today:{amount_micro:0,calls:1,unknown:1,tokens:0},history:[]},
    {id:'bailian:'+('a'.repeat(64)),label:'阿里云百炼 · 本机记录',active:false,day:'2026-10-13',incomplete:false,billingConnected:false,balance:{values:[],updatedAt:'',message:'对应 API 配置已变更'},today:{amount_micro:78000,calls:2,unknown:0,tokens:300},history:[]}
   ];
   if(cmd==='llm_config_status')return {hasApiKey:true,model:'test-model',searchMode:'off'};
   if(cmd==='chat_settings_get')return {revision:'test',hasKey:false,searchAvailable:false,accountSearchAvailable:false,searchBackend:'未配置',options:{keep:8,trigger:12,summaryTarget:300,summaryCap:500,contextChars:12000,readTimeout:180,searchMode:'off',searchEnabled:false,searchUrl:'https://api.tavily.com',projectReadEnabled:false,projectSettingsEnabled:false}};
   if(cmd==='api_profiles_list')return {revision:'test',path:'test.env',active:'legacy',profiles:[]};
   if(cmd==='project_settings_pending')return [];
   if(cmd==='extension_status')return {connected:false,available:false,tools:[]};
   if(cmd==='plugin:window|get_all_windows')return [];
   return 1;
  }};
 });
 const testUrl=process.env.BILLING_TEST_URL||'http://127.0.0.1:1420/?view=dialogue';
 await page.goto(testUrl);
 const card=page.getByRole('region',{name:'API 账户状态'});
 await card.getByText('¥ 12.34',{exact:true}).waitFor();
 assert.equal(await card.getByText('¥ 0.02',{exact:true}).count(),1);
 assert.equal(await card.getByText('估算',{exact:true}).count(),0);
 assert.equal(await card.getByRole('button',{name:'展开用量统计'}).count(),0);
 await card.getByRole('button',{name:'打开账务控制台',exact:true}).click();
 assert(await page.evaluate(()=>window.testCalls.some(c=>c.cmd==='plugin:opener|open_url'&&c.args.url==='https://platform.deepseek.com/usage')));
 await card.getByLabel('计费账户').selectOption('bailian:sample');
 await card.getByText('余额查询未连接',{exact:true}).waitFor();
 await card.getByRole('button',{name:'打开账务控制台',exact:true}).click();
 assert(await page.evaluate(()=>window.testCalls.some(c=>c.cmd==='plugin:opener|open_url'&&c.args.url==='https://billing-cost.console.aliyun.com/fortune/billing-account')));
 assert.equal(await card.getByText('暂不可用',{exact:true}).count(),1);
 await card.getByLabel('计费账户').selectOption('deepseek:sample');
 await card.getByRole('button',{name:'刷新账户状态'}).click();
 await page.waitForFunction(()=>window.testCalls.some(c=>c.cmd==='billing_balance'&&c.args.force===true));
 // A blocked provider must not delay another provider's updated cloud balance.
 await page.evaluate(()=>{window.holdAliyun=true;window.testBalance='56.78';});
 await card.getByRole('button',{name:'刷新账户状态'}).click();
 await page.waitForFunction(()=>typeof window.releaseAliyun==='function');
 await card.getByText('¥ 56.78',{exact:true}).waitFor();
 await page.evaluate(()=>{window.holdAliyun=false;window.releaseAliyun();});
 // Events during a slow account query must trigger one fresh local usage read.
 await page.getByRole('button',{name:'刷新账户状态'}).waitFor({state:'visible'});
 const before=await page.evaluate(()=>{const n=window.testCalls.filter(c=>c.cmd==='billing_status').length;window.delayBilling=true;window.dispatchEvent(new Event('focus'));return n;});
 await page.waitForFunction(()=>typeof window.releaseBilling==='function');
 await page.evaluate(()=>{window.dispatchEvent(new Event('focus'));window.releaseBilling();});
 await page.waitForFunction(n=>window.testCalls.filter(c=>c.cmd==='billing_status').length>=n+2,before);
 await page.evaluate(()=>{window.testAmount=1;document.dispatchEvent(new Event('visibilitychange'));});
 await card.getByText('¥ 0.00',{exact:true}).waitFor();
 for(const width of [1000,700,560]){
  await page.setViewportSize({width,height:800});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow');
 }
 await page.setViewportSize({width:1000,height:800});
 if(process.env.BILLING_TEST_SCREENSHOT)await page.screenshot({path:process.env.BILLING_TEST_SCREENSHOT});
 await page.goto(new URL('?view=settings',testUrl).toString());
 await page.getByRole('button',{name:'API 配置',exact:true}).click();
 const settingCard=page.getByRole('region',{name:'API 账户状态'});
 await settingCard.getByText('¥ 0.023456',{exact:true}).waitFor();
 assert.equal(await settingCard.getByText('估算',{exact:true}).count(),0);
 assert.equal(await settingCard.getByText('余额每 10 分钟更新；花费随调用累计，按本机日期跨天归零。',{exact:true}).count(),0);
 const settingLayout=await settingCard.evaluate(element=>{
  const style=getComputedStyle(element),wrapper=getComputedStyle(element.parentElement);
  return {radius:style.borderRadius,background:style.backgroundColor,width:element.getBoundingClientRect().width,parentWidth:element.parentElement.getBoundingClientRect().width-parseFloat(wrapper.paddingLeft)-parseFloat(wrapper.paddingRight),marginBottom:getComputedStyle(element.closest('.settings-disclosure')).marginBottom};
 });
 assert.equal(settingLayout.radius,'9px');
 assert.equal(settingLayout.background,'rgb(238, 240, 245)');
 assert(Math.abs(settingLayout.width-settingLayout.parentWidth)<1,'settings billing card should fill its settings row');
 assert(parseFloat(settingLayout.marginBottom)>=7,'account disclosure needs separation from the next section');
 await settingCard.getByRole('button',{name:'展开用量统计'}).click();
 await settingCard.getByLabel('近 7 天用量统计').waitFor();
 assert.equal(await settingCard.locator('.billing-history-day').count(),7);
 assert.equal(await settingCard.getByText('¥ 0.038456',{exact:true}).count(),1);
 assert.equal(await settingCard.getByText('8 次',{exact:true}).count(),1);
 if(process.env.BILLING_SETTINGS_SCREENSHOT)await settingCard.screenshot({path:process.env.BILLING_SETTINGS_SCREENSHOT});
 for(const width of [1000,700,560]){
  await page.setViewportSize({width,height:800});
  assert(await settingCard.locator('dl').evaluate(node=>[...node.children].every(row=>{
   const label=row.querySelector('dt').getBoundingClientRect(),value=row.querySelector('dd').getBoundingClientRect();
   return label.right+5<=value.left&&value.right<=node.getBoundingClientRect().right+1;
  })),'billing labels and amounts must not overlap at narrow widths');
 }
 await page.setViewportSize({width:1000,height:800});
 await settingCard.getByLabel('计费账户').selectOption('bailian:sample');
 await settingCard.getByText('查询阿里云余额',{exact:true}).click();
 await settingCard.getByRole('button',{name:'配置授权 ↗',exact:true}).click();
 assert(await page.evaluate(()=>window.testCalls.some(c=>c.cmd==='plugin:opener|open_url'&&c.args.url==='https://ram.console.aliyun.com/')));
 await settingCard.getByLabel('AccessKey ID',{exact:true}).fill('fakeid');
 await settingCard.getByLabel('AccessKey Secret',{exact:true}).fill('fake-secret');
 await page.getByRole('button',{name:'美术',exact:true}).click();
 await page.getByRole('button',{name:'API 配置',exact:true}).click();
 assert.equal(await settingCard.getByLabel('AccessKey ID',{exact:true}).inputValue(),'fakeid');
 await settingCard.getByRole('button',{name:'连接查询',exact:true}).click();
 await page.waitForFunction(()=>window.testCalls.some(c=>c.cmd==='billing_connection_save'));
 await page.waitForFunction(()=>document.querySelector('.billing-connection input[type=password]').value==='');
 await settingCard.getByLabel('AccessKey ID',{exact:true}).fill('unsaved-account');
 await settingCard.getByLabel('AccessKey Secret',{exact:true}).fill('unsaved-secret');
 await page.evaluate(()=>{window.changedAccount=true;window.dispatchEvent(new Event('focus'));});
 await settingCard.getByLabel('计费账户').selectOption('bailian:replacement');
 await settingCard.getByText('查询阿里云余额',{exact:true}).click();
 assert.equal(await settingCard.getByLabel('AccessKey ID',{exact:true}).inputValue(),'');
 assert.equal(await settingCard.getByLabel('AccessKey Secret',{exact:true}).inputValue(),'');
 // A fresh page sees persisted connection metadata, not an empty credential form.
 await page.evaluate(()=>localStorage.setItem('test-billing-connected','1'));
 await page.reload();
 await page.getByRole('button',{name:'API 配置',exact:true}).click();
 await settingCard.getByLabel('计费账户').selectOption('bailian:sample');
 await settingCard.getByText('余额查询已连接',{exact:true}).click();
 assert.equal(await settingCard.getByLabel('AccessKey Secret',{exact:true}).count(),0);
 await settingCard.getByRole('button',{name:'更新授权',exact:true}).click();
 await settingCard.getByLabel('AccessKey Secret',{exact:true}).fill('unsaved-replacement');
 await settingCard.getByRole('button',{name:'取消',exact:true}).click();
 assert.equal(await settingCard.getByLabel('AccessKey Secret',{exact:true}).count(),0);
 const balanceCallsBeforeArchive=await page.evaluate(()=>window.testCalls.filter(c=>c.cmd==='billing_balance').length);
 await settingCard.getByLabel('计费账户').selectOption('bailian:'+('a'.repeat(64)));
 await settingCard.getByText('对应 API 配置已变更',{exact:true}).waitFor();
 assert.equal(await settingCard.locator('.billing-connection').count(),0,'archived local usage must not expose cloud authorization');
 assert.equal(await page.evaluate(()=>window.testCalls.filter(c=>c.cmd==='billing_balance').length),balanceCallsBeforeArchive,'archived local usage must not query cloud balance');
 assert.deepEqual(errors,[]);
 console.log('PASS billing card: compact/detail precision, reduced labels, provider switching, refresh, settings layout and account draft isolation');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
