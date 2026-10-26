import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {openUrl} from '@tauri-apps/plugin-opener';
import type {MouseEvent} from 'react';
import './RinaTomoPage.css';
import {GetApiButton} from '../../components/GetApiButton';

import {fromSnapshot,mergeDraft,parseIds,parseNightTime,parseNonNegativeNumber,parsePositiveInteger,preview,serviceControls} from './tomoState';
import type {Draft,Group,RinaTomoSnapshot} from './tomoState';

export default function RinaTomoPage(){
 const [snapshot,setSnapshot]=useState<RinaTomoSnapshot>(preview);
 const [draft,setDraft]=useState<Draft>(()=>fromSnapshot(preview));
 const [featureDirty,setFeatureDirty]=useState(false),[llmDirty,setLlmDirty]=useState(false);
 const [permissionDirty,setPermissionDirty]=useState(false),[startupDirty,setStartupDirty]=useState(false),[notifyDirty,setNotifyDirty]=useState(false);
 const [loginDismissed,setLoginDismissed]=useState(false),[launchingLogin,setLaunchingLogin]=useState(false);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
 const dirty=useRef({features:false,llm:false,permissions:false,autoStart:false,notifications:false});
 dirty.current={features:featureDirty,llm:llmDirty,permissions:permissionDirty,autoStart:startupDirty,notifications:notifyDirty};
 const working=useRef(false),polling=useRef(false),mounted=useRef(true),epoch=useRef(0);
 const accept=useCallback((next:RinaTomoSnapshot,applied?:Group)=>{
  if(!mounted.current)return;
  const pending={...dirty.current};
  if(applied)pending[applied]=false;
  setSnapshot(next);
  setDraft(current=>mergeDraft(current,next,pending));
 },[]);
 const refresh=useCallback(async()=>{
  if(working.current||polling.current)return;
  polling.current=true;const revision=epoch.current;
  try{const next=isTauri()?await invoke<RinaTomoSnapshot>('rinatomo_status'):preview;if(mounted.current&&revision===epoch.current)accept(next);}
  catch(e){if(mounted.current&&revision===epoch.current)setError(String(e));}
  finally{polling.current=false;}
 },[accept]);
 useEffect(()=>{mounted.current=true;void refresh();const timer=setInterval(()=>void refresh(),2000);return()=>{mounted.current=false;epoch.current++;clearInterval(timer);};},[refresh]);
 useEffect(()=>{
  if(snapshot.login?.required||snapshot.state==='online')setLaunchingLogin(false);
  if(!snapshot.login?.required)setLoginDismissed(false);
 },[snapshot.login?.required,snapshot.state]);
 useEffect(()=>{
  if(launchingLogin&&!busy&&snapshot.available&&!snapshot.running&&!snapshot.login?.required&&snapshot.state!=='online'){
   setLaunchingLogin(false);
   setError('Tomo 启动未完成，请检查 QQ / NapCat 配置。');
  }
 },[launchingLogin,busy,snapshot.available,snapshot.running,snapshot.login?.required,snapshot.state]);
 function openSetup(event:MouseEvent<HTMLAnchorElement>,url:string){
  if(!isTauri())return;
  event.preventDefault();
  void openUrl(url).catch(()=>setError('暂时无法打开页面，请稍后重试。'));
 }
 async function perform(operation:()=>Promise<void>){
  if(working.current)return false;
  working.current=true;epoch.current++;setBusy(true);setError('');setMessage('');
  try{await operation();return true;}catch(e){if(mounted.current)setError(String(e));return false;}
  finally{working.current=false;if(mounted.current){setBusy(false);void refresh();}}
 }
 async function action(name:'start'|'pause'|'shutdown'|'show'|'refreshLogin'){
  await perform(async()=>accept(await invoke<RinaTomoSnapshot>('rinatomo_action',{action:name})));
 }
 async function launch(){
  setLoginDismissed(false);setLaunchingLogin(true);
  const completed=await perform(async()=>{
   await invoke('rinatomo_launch');
   let next:RinaTomoSnapshot|undefined;
   for(let attempt=0;attempt<48;attempt++){
    await new Promise(resolve=>setTimeout(resolve,250));
    next=await invoke<RinaTomoSnapshot>('rinatomo_status');
    if(next.available)break;
   }
   if(!next?.available)throw new Error('RinaTomo 启动超时，请检查本机运行环境。');
   accept(next);
   if(next.state!=='online'&&!next.running)next=await invoke<RinaTomoSnapshot>('rinatomo_action',{action:'start'});
   accept(next);
  });
  if(!completed&&mounted.current)setLaunchingLogin(false);
 }
 async function update(payload:object,done:()=>void){
  await perform(async()=>{
   const next=await invoke<RinaTomoSnapshot>('rinatomo_update',{requestBody:payload});
   const group=Object.keys(payload)[0] as Group;
   if(mounted.current){dirty.current[group]=false;accept(next,group);done();setMessage('已同步到 RinaTomo。');}
  });
 }
 function saveFeatures(){void update({features:{ping:draft.features.ping,echo:draft.features.echo}},()=>setFeatureDirty(false));}
 function saveLlm(){
  try{
   const timeoutSeconds=parseNonNegativeNumber(draft.llm.timeoutSeconds,'请求超时');
   if(timeoutSeconds<=0)throw new Error('请求超时必须大于 0。');
   void update({llm:{
    enabled:draft.llm.enabled,
    minReplyInterval:parseNonNegativeNumber(draft.llm.minReplyInterval,'最小回复间隔'),
    timeoutSeconds,
    maxTokens:parsePositiveInteger(draft.llm.maxTokens,'最大回复 token'),
    dailyTokenBudget:parsePositiveInteger(draft.llm.dailyTokenBudget,'每日 token 预算'),
    maxInputChars:parsePositiveInteger(draft.llm.maxInputChars,'输入字符上限'),
    maxConcurrentRequests:parsePositiveInteger(draft.llm.maxConcurrentRequests,'最大并发请求'),
   }},()=>setLlmDirty(false));
  }catch(e){setError(String(e));}
 }
 function savePermissions(){try{void update({permissions:{adminUsers:parseIds(draft.permissions.adminUsers,'管理员 QQ'),privateWhitelist:parseIds(draft.permissions.privateWhitelist,'允许私聊'),enabledGroups:parseIds(draft.permissions.enabledGroups,'启用群聊')}},()=>setPermissionDirty(false));}catch(e){setError(String(e));}}
 function saveNotifications(){
  try{
   const nightStart=parseNightTime(draft.notifications.nightStart,'休眠开始时间');
   const nightEnd=parseNightTime(draft.notifications.nightEnd,'休眠结束时间');
   if(nightStart===nightEnd)throw new Error('休眠开始与结束时间不能相同。');
   void update({notifications:{
    enabled:draft.notifications.enabled,
    nightSleepEnabled:draft.notifications.nightSleepEnabled,
    nightStart,nightEnd,
    events:{
     translation:draft.notifications.events.translation,
     chatReply:draft.notifications.events.chatReply,
     loginFailure:draft.notifications.events.loginFailure,
    },
   }},()=>setNotifyDirty(false));
  }catch(e){setError(String(e));}
 }
 function changeNotify<K extends keyof Draft['notifications']>(key:K,value:Draft['notifications'][K]){setDraft(v=>({...v,notifications:{...v.notifications,[key]:value}}));setNotifyDirty(true);}
 function changeNotifyEvent(key:'translation'|'chatReply'|'loginFailure',value:boolean){setDraft(v=>({...v,notifications:{...v.notifications,events:{...v.notifications.events,[key]:value}}}));setNotifyDirty(true);}
 function changeLlm<K extends keyof Draft['llm']>(key:K,value:Draft['llm'][K]){setDraft(v=>({...v,llm:{...v.llm,[key]:value}}));setLlmDirty(true);}
 const online=snapshot.state==='online';
 const controls=serviceControls(snapshot);
 const login=snapshot.login??preview.login;
 return <section className="tomo-page" aria-label="QQ Bot">
  {(!snapshot.available||snapshot.napcat==='未连接')&&<p className="tomo-setup-links">
   {([{label:'获取／修复 Tomo',url:'https://github.com/bz-GAO/OurDeskPet/releases'},{label:'安装 NapCat',url:'https://napneko.github.io/guide/boot/Shell'},{label:'下载 QQ',url:'https://im.qq.com/pcqq/index.shtml'}] as const).map(item=><a key={item.label} href={item.url} target="_blank" rel="noreferrer" onClick={event=>openSetup(event,item.url)}>{item.label} ↗</a>)}
  </p>}
  <div className="tomo-status-grid"><div><span>NapCat</span><strong>{snapshot.napcat}</strong></div><div><span>QQ</span><strong>{snapshot.qq}</strong></div><div><span>状态</span><strong className={online?'is-online':''}>{online?'在线':'离线'}</strong></div></div>
  <div className="tomo-actions">{snapshot.available?<button className="tomo-primary" disabled={busy||!controls.canStart} onClick={()=>void action(online?'pause':'start')}>{controls.closing?'正在关闭…':online?'暂停':'启动'}</button>:<button className="tomo-primary" disabled={busy||!isTauri()} onClick={()=>void launch()}>{busy?'正在启动…':'启动 Tomo'}</button>}{controls.showShutdown&&<button className="tomo-danger" disabled={busy||!controls.canShutdown} onClick={()=>void action('shutdown')}>关闭服务</button>}</div>
  {(error||controls.error)&&<p className="tomo-error" role="alert">{error||controls.error}</p>}{message&&<p className="tomo-success" role="status">{message}</p>}
  <div className="tomo-stage">
   {!snapshot.available?<div className="tomo-empty"><strong>RinaTomo 控制器未运行</strong><span>打开后即可在这里同步状态、功能与权限。</span></div>:<div className="tomo-settings">
    <fieldset disabled={busy}><legend>对话功能</legend>
     <label><input type="checkbox" checked={draft.features.ping} onChange={e=>{setDraft(v=>({...v,features:{...v.features,ping:e.target.checked}}));setFeatureDirty(true);}}/>ping → pong 连通验证</label>
     <label><input type="checkbox" checked={draft.features.echo} onChange={e=>{setDraft(v=>({...v,features:{...v.features,echo:e.target.checked}}));setFeatureDirty(true);}}/>复读所有消息（仅联调）</label>
     <div className="tomo-apply"><span>{featureDirty?'● 有未应用的更改':'✓ 已同步'}</span><button disabled={busy||!featureDirty} onClick={saveFeatures}>应用功能</button></div>
    </fieldset>
    <fieldset disabled={busy}><legend>大模型服务</legend>
     <GetApiButton/>
     <div className="tomo-switch"><span>服务状态</span><label><input type="radio" name="tomo-llm" checked={draft.llm.enabled} onChange={()=>changeLlm('enabled',true)}/>开启</label><label><input type="radio" name="tomo-llm" checked={!draft.llm.enabled} onChange={()=>changeLlm('enabled',false)}/>关闭</label></div>
     <p className="tomo-model">当前模型：{snapshot.llm?.effectiveModel||'未配置'}</p>
     <p className="tomo-model">今日 token 用量：{snapshot.llm?.usage?`${snapshot.llm.usage.used} / ${snapshot.llm.usage.dailyLimit}（余 ${snapshot.llm.usage.remaining}）`:'—'}</p>
     <label className="tomo-field"><span>最小回复间隔</span><span className="tomo-unit"><input type="number" min="0" step="0.1" list="tomo-interval-options" value={draft.llm.minReplyInterval} onChange={e=>changeLlm('minReplyInterval',e.target.value)}/><em>秒</em></span></label>
     <datalist id="tomo-interval-options"><option value="0"/><option value="1"/><option value="5"/><option value="10"/></datalist>
     {([['timeoutSeconds','请求超时（秒）'],['maxTokens','最大回复 token'],['dailyTokenBudget','每日 token 预算'],['maxInputChars','输入字符上限'],['maxConcurrentRequests','最大并发请求']] as const).map(([key,label])=><label className="tomo-field" key={key}><span>{label}</span><input type="number" min="1" value={draft.llm[key]} onChange={e=>changeLlm(key,e.target.value)}/></label>)}
     <div className="tomo-apply"><span>{llmDirty?'● 有未应用的更改':'✓ 已同步'}</span><button disabled={busy||!llmDirty} onClick={saveLlm}>应用大模型设置</button></div>
    </fieldset>
    <fieldset disabled={busy}><legend>权限范围</legend>
     {([['adminUsers','管理员 QQ'],['privateWhitelist','允许私聊'],['enabledGroups','启用群聊']] as const).map(([key,label])=><label className="tomo-field" key={key}><span>{label}</span><input value={draft.permissions[key]} onChange={e=>{setDraft(v=>({...v,permissions:{...v.permissions,[key]:e.target.value}}));setPermissionDirty(true);}}/></label>)}
     <div className="tomo-apply"><span>{permissionDirty?'● 有未应用的更改':'✓ 已同步'}</span><button disabled={busy||!permissionDirty} onClick={savePermissions}>应用权限</button></div>
    </fieldset>
    <fieldset disabled={busy}><legend>启动行为</legend><label><input type="checkbox" checked={draft.autoStart} onChange={e=>{setDraft(v=>({...v,autoStart:e.target.checked}));setStartupDirty(true);}}/>打开控制面板后自动启动 Bot</label><div className="tomo-apply"><span>{startupDirty?'● 有未应用的更改':'✓ 已同步'}</span><button disabled={busy||!startupDirty} onClick={()=>void update({autoStart:draft.autoStart},()=>setStartupDirty(false))}>应用</button></div></fieldset>
    <fieldset disabled={busy}><legend>通知与深夜休眠</legend>
     <label className="tomo-notify-master"><input type="checkbox" checked={draft.notifications.enabled} onChange={e=>changeNotify('enabled',e.target.checked)}/><span><strong>管理员通知</strong><small>仅发送到管理员白名单</small></span></label>
     <div className="tomo-notify-events" role="group" aria-label="通知事件" aria-disabled={!draft.notifications.enabled}>
      <label><input type="checkbox" disabled={!draft.notifications.enabled} checked={draft.notifications.events.translation} onChange={e=>changeNotifyEvent('translation',e.target.checked)}/>翻译任务完成 / 失败</label>
      <label><input type="checkbox" disabled={!draft.notifications.enabled} checked={draft.notifications.events.chatReply} onChange={e=>changeNotifyEvent('chatReply',e.target.checked)}/>聊天回复完成</label>
      <label><input type="checkbox" disabled={!draft.notifications.enabled} checked={draft.notifications.events.loginFailure} onChange={e=>changeNotifyEvent('loginFailure',e.target.checked)}/>登录失效</label>
     </div>
     <label className="tomo-notify-master"><input type="checkbox" checked={draft.notifications.nightSleepEnabled} onChange={e=>changeNotify('nightSleepEnabled',e.target.checked)}/><span><strong>深夜休眠</strong><small>期间停止服务，通知不排队</small></span></label>
     <div className="tomo-night-range" data-disabled={!draft.notifications.nightSleepEnabled}>
      <span className="tomo-night-label">休眠时段</span>
      <label><span>开始</span><input aria-label="休眠开始时间" type="time" disabled={!draft.notifications.nightSleepEnabled} value={draft.notifications.nightStart} onChange={e=>changeNotify('nightStart',e.target.value)}/></label>
      <span className="tomo-night-separator" aria-hidden="true">至</span>
      <label><span>结束</span><input aria-label="休眠结束时间" type="time" disabled={!draft.notifications.nightSleepEnabled} value={draft.notifications.nightEnd} onChange={e=>changeNotify('nightEnd',e.target.value)}/></label>
     </div>
     <div className="tomo-apply"><span>{notifyDirty?'● 有未应用的更改':'✓ 已同步'}</span><button disabled={busy||!notifyDirty} onClick={saveNotifications}>应用通知</button></div>
    </fieldset>
    <button className="tomo-open-panel" disabled={busy} onClick={()=>void action('show')}>打开RinaTomo</button>
   </div>}
    {(launchingLogin||(snapshot.available&&login.required))&&!loginDismissed&&<div className="tomo-login" role="dialog" aria-label="扫码登录 QQ">
    <button className="tomo-login-close" aria-label="关闭登录层" onClick={()=>setLoginDismissed(true)}>×</button>
     <strong>扫码登录 QQ</strong><span>{launchingLogin?'正在启动 RinaTomo 并等待二维码…':login.message||'正在等待 NapCat 生成二维码…'}</span>
    {login.qrcodeDataUrl?<img src={login.qrcodeDataUrl} alt="QQ 登录二维码"/>:<div className="tomo-qr-wait">二维码生成中…</div>}
     {!launchingLogin&&<div><button disabled={busy} onClick={()=>{setLoginDismissed(false);void action('refreshLogin');}}>刷新</button></div>}
   </div>}
  </div>
 </section>;
}
