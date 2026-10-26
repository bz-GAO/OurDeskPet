import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import {displayConfigPath} from './displayConfigPath';
import './ChatSettings.css';
import {useConfirmDialog} from './ConfirmDialog';
import {ChatStorageSettings} from './ChatStorageSettings';
import {SettingsDisclosure} from './SettingsDisclosure';
type Options={keep:number;trigger:number;summaryTarget:number;summaryCap:number;contextChars:number;readTimeout:number;searchMode:string;searchEnabled:boolean;searchUrl:string;projectReadEnabled:boolean;projectSettingsEnabled:boolean};
type Snapshot={revision:string;options:Options;hasKey:boolean;searchAvailable:boolean;accountSearchAvailable:boolean;searchBackend:string};
const light={keep:8,trigger:12,summaryTarget:300,summaryCap:500,contextChars:12000};
const balanced={keep:12,trigger:20,summaryTarget:600,summaryCap:1000,contextChars:24000};
const defaults:Options={...light,readTimeout:180,searchMode:'auto',searchEnabled:true,searchUrl:'https://api.tavily.com',projectReadEnabled:false,projectSettingsEnabled:false};
const same=(a:Options,b:typeof light)=>Object.entries(b).every(([k,v])=>a[k as keyof Options]===v);
export function ChatSettings({onDirtyChange}:{onDirtyChange:(dirty:boolean)=>void}){
 const {confirm,dialog}=useConfirmDialog();
 const [snapshot,setSnapshot]=useState<Snapshot|null>(null),[draft,setDraft]=useState<Options>(defaults);
 const [key,setKey]=useState(''),[clearKey,setClearKey]=useState(false),[dirty,setDirty]=useState(false),[conflict,setConflict]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [custom,setCustom]=useState(false);const state=useRef({dirty,busy,snapshot});state.current={dirty,busy,snapshot};
 useEffect(()=>onDirtyChange(dirty),[dirty,onDirtyChange]);
 const load=useCallback(async(force=false)=>{
  if(state.current.busy)return;
  try{const next=isTauri()?await invoke<Snapshot>('chat_settings_get'):{revision:'preview',options:defaults,hasKey:false,searchAvailable:false,accountSearchAvailable:false,searchBackend:'未配置'};
   if(state.current.busy)return;
   if(state.current.dirty&&!force){if(next.revision!==state.current.snapshot?.revision)setConflict(true);return;}
   setSnapshot(next);setDraft(next.options);setCustom(!same(next.options,light)&&!same(next.options,balanced));setDirty(false);setConflict(false);setKey('');setClearKey(false);setError('');
  }catch(e){setError(String(e));}
 },[]);
 useEffect(()=>{void load();const refresh=()=>void load();window.addEventListener('focus',refresh);const timer=setInterval(refresh,4000);return()=>{window.removeEventListener('focus',refresh);clearInterval(timer);};},[load]);
 function change<K extends keyof Options>(name:K,value:Options[K]){setDraft(d=>({...d,[name]:value}));setDirty(true);setMessage('');}
 async function save(){if(!snapshot||busy)return;state.current.busy=true;setBusy(true);setError('');setMessage('');
  try{const next=await invoke<Snapshot>('chat_settings_save',{request:{revision:snapshot.revision,options:draft,key:key.trim()||null,clearKey}});setSnapshot(next);setDraft(next.options);setKey('');setClearKey(false);setDirty(false);setConflict(false);setMessage('已保存，下次发送时生效。');}
  catch(e){setError(String(e));}finally{state.current.busy=false;setBusy(false);}
 }
 const preset=custom?'custom':same(draft,light)?'light':same(draft,balanced)?'balanced':'custom';
 const tavilyAvailable=Boolean(key.trim()||(snapshot?.hasKey&&!clearKey));const searchReady=Boolean(snapshot?.accountSearchAvailable||tavilyAvailable);
 return <form className="chat-settings" onSubmit={e=>{e.preventDefault();void save();}}>
  {dialog}
  <fieldset disabled={busy||!snapshot}>
   <section className="chat-memory-panel" aria-labelledby="chat-memory-title">
    <div className="chat-memory-row"><strong id="chat-memory-title">对话记忆</strong><select aria-label="上下文预设" value={preset} onChange={e=>{setCustom(e.target.value==='custom');if(e.target.value!=='custom'){setDraft(d=>({...d,...(e.target.value==='light'?light:balanced)}));setDirty(true);setMessage('');}}}><option value="light">轻量 · {light.keep}轮</option><option value="balanced">均衡 · {balanced.keep}轮</option><option value="custom">自定义</option></select></div>
    {preset==='custom'&&<div className="chat-memory-custom"><div className="chat-setting-fields">{([{key:'keep',label:'原文保留轮数',min:2,max:32},{key:'trigger',label:'开始整理轮数',min:draft.keep+1,max:48},{key:'summaryTarget',label:'摘要目标字数',min:100,max:2000},{key:'summaryCap',label:'摘要字数上限',min:draft.summaryTarget,max:2000},{key:'contextChars',label:'上下文字符预算',min:4000,max:100000}] as const).map(f=><label key={f.key}>{f.label}<input required type="number" min={f.min} max={f.max} step="1" value={draft[f.key]} onChange={e=>change(f.key,e.target.valueAsNumber||0)}/></label>)}</div></div>}
   </section>
   <SettingsDisclosure title="对话保存位置"><ChatStorageSettings/></SettingsDisclosure>
   <SettingsDisclosure title="联网搜索"><label>默认模式<select aria-label="默认联网模式" value={draft.searchMode} onChange={e=>change('searchMode',e.target.value)}><option value="auto">自动判断</option><option value="off">不联网</option><option value="required">必须搜索</option></select></label>

   <label className="chat-toggle"><input type="checkbox" checked={draft.searchEnabled} onChange={e=>change('searchEnabled',e.target.checked)}/>启用搜索服务</label>
   <label>{snapshot?.accountSearchAvailable?'Tavily 备用密钥':'Tavily 密钥'}<input type="password" autoComplete="new-password" aria-label="搜索密钥" value={key} disabled={clearKey} placeholder={snapshot?.hasKey?'已保存':'可选'} onChange={e=>{setKey(e.target.value);setDirty(true);setMessage('');}}/></label>
   {snapshot?.hasKey&&<label className="chat-toggle"><input type="checkbox" checked={clearKey} onChange={e=>{setClearKey(e.target.checked);setDirty(true);}}/>保存时移除已存密钥</label>}
   {draft.searchMode==='required'&&(!draft.searchEnabled||!searchReady)&&<p className="settings-warning">必须搜索需要可用的搜索来源。</p>}
   </SettingsDisclosure>
   <SettingsDisclosure title="项目助手">
   <label className="chat-toggle"><input type="checkbox" checked={draft.projectReadEnabled} onChange={e=>change('projectReadEnabled',e.target.checked)}/>允许只读访问项目源码</label>
   <label className="chat-toggle"><input type="checkbox" checked={draft.projectSettingsEnabled} onChange={e=>change('projectSettingsEnabled',e.target.checked)}/>允许助手提出安全设置修改</label>
   </SettingsDisclosure>
   <SettingsDisclosure title="高级"><div className="chat-setting-fields"><label>等待新回复的时间（秒）<input type="number" min="15" max="600" required value={draft.readTimeout} onChange={e=>change('readTimeout',e.target.valueAsNumber||0)}/></label></div></SettingsDisclosure>
  </fieldset>
  {conflict&&<div className="settings-warning">配置已在别处修改，草稿已保留。<button type="button" onClick={async()=>{if(await confirm('放弃当前 Chat 设置草稿并重新载入？'))void load(true);}}>重新载入</button></div>}
  {error&&<p role="alert" className="settings-error">{error}</p>}{message&&<p role="status" className="settings-success">{message}</p>}
  <div className="api-actions"><button className="settings-primary" type="submit" disabled={busy||!dirty||conflict||!snapshot||!isTauri()}>{busy?'保存中…':'保存 Chat 设置'}</button><button type="button" disabled={busy||!dirty} onClick={async()=>{if(await confirm('放弃尚未保存的 Chat 设置？'))void load(true);}}>撤销修改</button></div>
 </form>;
}
export function GeneralSettings(){
 const [status,setStatus]=useState<{enabled:boolean;supported:boolean}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=useCallback(()=>{if(isTauri())void invoke<{enabled:boolean;supported:boolean}>('startup_get').then(value=>{setStatus(value);setError('');}).catch(e=>setError(String(e)));else setStatus({enabled:false,supported:false});},[]);
 useEffect(()=>{load();let alive=true;let off:(()=>void)|undefined;window.addEventListener('focus',load);if(isTauri())void listen('deskpet-startup-changed',load).then(fn=>{if(alive)off=fn;else fn();}).catch(()=>{});return()=>{alive=false;window.removeEventListener('focus',load);off?.();};},[load]);
 async function change(enabled:boolean){setBusy(true);setError('');try{setStatus(await invoke('startup_set',{enabled}));}catch(e){setError(String(e));}finally{setBusy(false);}}
 return <div className="general-settings"><div className="setting-row"><strong>开机启动</strong><input type="checkbox" aria-label="开机启动" checked={status?.enabled??false} disabled={busy||!status?.supported} onChange={e=>void change(e.target.checked)}/></div>{error&&<p className="settings-error" role="alert">{error}</p>}<SettingsDisclosure title="诊断"><DiagnosticsPanel/></SettingsDisclosure></div>;
}

type ToolDiagnostic={path:string|null;state:string;version:string|null;protocol:string};
type Diagnostics={appVersion:string;buildTime:string;sourceRevision:string;executablePath:string;configPath:string;yaki:ToolDiagnostic;tomo:ToolDiagnostic};
function DiagnosticsPanel(){
 const [data,setData]=useState<Diagnostics|null>(null),[error,setError]=useState(''),[copied,setCopied]=useState(false);
 const load=useCallback(()=>{if(!isTauri())return;void invoke<Diagnostics>('diagnostics_get').then(value=>{setData(value);setError('');}).catch(e=>setError(String(e)));},[]);
 useEffect(()=>{load();window.addEventListener('focus',load);return()=>window.removeEventListener('focus',load);},[load]);
 const rows=data?[['版本',data.appVersion],['构建',`${data.buildTime} · ${data.sourceRevision}`],['程序',displayConfigPath(data.executablePath)],['配置',displayConfigPath(data.configPath)],['RinaYaki',`${data.yaki.state} · ${data.yaki.protocol}${data.yaki.version?` · ${data.yaki.version}`:''}${data.yaki.path?`\n${displayConfigPath(data.yaki.path)}`:''}`],['RinaTomo',`${data.tomo.state} · ${data.tomo.protocol}${data.tomo.path?`\n${displayConfigPath(data.tomo.path)}`:''}`]]:[];
 async function copy(){if(!data)return;try{await navigator.clipboard.writeText(rows.map(([name,value])=>`${name}: ${value}`).join('\n'));setCopied(true);window.setTimeout(()=>setCopied(false),1500);}catch{setError('复制失败。');}}
 return <section className="diagnostics-panel" aria-label="运行诊断"><div className="diagnostics-heading"><strong>运行诊断</strong><div><button type="button" onClick={load}>刷新</button><button type="button" disabled={!data} onClick={()=>void copy()}>{copied?'已复制':'复制'}</button></div></div>
  {data&&<dl>{rows.map(([name,value])=><div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>}
  {!data&&!error&&<p className="settings-note">读取中…</p>}{error&&<p className="settings-error" role="alert">{error}</p>}
 </section>;
}
