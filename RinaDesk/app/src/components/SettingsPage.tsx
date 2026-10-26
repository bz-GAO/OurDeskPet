import {displayConfigPath} from './displayConfigPath';
import {BOARD,boardStarPosition} from './boardGeometry';
import {ChatSettings,GeneralSettings} from './ChatSettings';
import {BillingStatus} from './BillingStatus';
import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {ArtPicker} from './ArtPicker';
import {ExtensionsPage} from '../extensions/ExtensionsPage';
import './SettingsPage.css';
import {useConfirmDialog} from './ConfirmDialog';
import {SettingsDisclosure} from './SettingsDisclosure';
import {GetApiButton} from './GetApiButton';

type Profile={id:string;name:string;baseUrl:string;model:string;hasKey:boolean;ready:boolean;readOnly:boolean};
type Snapshot={revision:string;path:string;active:string;profiles:Profile[]};
type Draft={id:string;name:string;baseUrl:string;model:string;key:string};
const empty=():Draft=>({id:'',name:'',baseUrl:'',model:'',key:''});
const preview:Snapshot={revision:'preview',path:'浏览器预览 · 配置不会写入',active:'legacy',profiles:[]};

export function SettingsPage(){
 const {confirm,dialog}=useConfirmDialog();
 const allowClose=useRef(false);
 const closeApproved=useCallback(async()=>{allowClose.current=true;try{await getCurrentWindow().close();}catch(e){allowClose.current=false;setError(String(e));}},[]);
 const [section,setSection]=useState<'settings'|'extensions'>('settings');
 useEffect(()=>{
  if(!isTauri())return;
  let disposed=false;let off:(()=>void)|undefined;
  void import('@tauri-apps/api/event').then(async ({listen})=>{
    const fn=await listen('deskpet-open-yaki',()=>setSection('extensions'));
    if(disposed)fn();else off=fn;
  }).catch(()=>{});
  return()=>{disposed=true;off?.();};
 },[]);
 const [tab,setTab]=useState('art');
 const [chatDirty,setChatDirty]=useState(false);
 const [billingDirty,setBillingDirty]=useState(false);
 const [artDirty,setArtDirty]=useState(false);
 const artDirtyRef=useRef(false);artDirtyRef.current=artDirty;
 const billingDirtyRef=useRef(false);billingDirtyRef.current=billingDirty;
 const chatDirtyRef=useRef(false);chatDirtyRef.current=chatDirty;
 const [data,setData]=useState<Snapshot|null>(null);
 const [draft,setDraft]=useState<Draft>(empty);
 const [editing,setEditing]=useState<string|null>(null);
 const [dirty,setDirty]=useState(false);
 const [changed,setChanged]=useState(false);
 const [busy,setBusy]=useState(false);
 const [message,setMessage]=useState('');
 const [error,setError]=useState('');
 const dirtyRef=useRef(false);dirtyRef.current=dirty;
 const dataRef=useRef(data);dataRef.current=data;
 const editingRef=useRef(editing);editingRef.current=editing;
 const busyRef=useRef(busy);busyRef.current=busy;
 const load=useCallback(async()=>{
  if(busyRef.current)return;
  try{
   const next=isTauri()?await invoke<Snapshot>('api_profiles_list'):preview;
   if(busyRef.current)return;
   if(dirtyRef.current && dataRef.current && next.revision!==dataRef.current.revision){setChanged(true);return;}
   if(!dirtyRef.current && (!dataRef.current || next.revision!==dataRef.current.revision)){
    const p=next.profiles.find(p=>p.id===(dataRef.current?editingRef.current:next.active));
    setEditing(p?.id??null);setDraft(p?{id:p.id,name:p.name,baseUrl:p.baseUrl,model:p.model,key:''}:empty());
   }
   setData(next);
  }catch(e){setError(String(e));}
 },[]);
 useEffect(()=>{void load();const refresh=()=>void load();window.addEventListener('focus',refresh);const timer=setInterval(refresh,4000);return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);};},[load]);
 useEffect(()=>{
  if(!isTauri())return;let disposed=false;let off:(()=>void)|undefined;
  void getCurrentWindow().onCloseRequested(event=>{if(!allowClose.current&&(dirtyRef.current||chatDirtyRef.current||billingDirtyRef.current||artDirtyRef.current)){event.preventDefault();void confirm('放弃尚未保存的设置并关闭？').then(async accepted=>{if(!accepted||disposed)return;await closeApproved();});}}).then(fn=>{if(disposed)fn();else off=fn;}).catch(console.error);
  return()=>{disposed=true;off?.();};
 },[confirm,closeApproved]);
 const selected=data?.profiles.find(p=>p.id===editing);
 async function discard(){return !(dirty||chatDirty||billingDirty||artDirty)||await confirm('放弃尚未保存的设置？');}
 async function edit(p?:Profile){if(dirty&&!await confirm('放弃尚未保存的 API 草稿？'))return;setEditing(p?.id??null);setDraft(p?{id:p.id,name:p.name,baseUrl:p.baseUrl,model:p.model,key:''}:empty());setDirty(false);setMessage('');setError('');}
 function change(field:keyof Draft,value:string){setDraft(d=>({...d,[field]:value}));setDirty(true);setMessage('');}
 async function save(){
  if(!data)return;busyRef.current=true;setBusy(true);setError('');setMessage('');
  try{const next=await invoke<Snapshot>('api_profiles_save',{request:{...draft,revision:data.revision,create:editing===null,key:draft.key.trim()||null}});setData(next);setEditing(draft.id.trim().toLowerCase());setDraft(d=>({...d,id:d.id.trim().toLowerCase(),key:''}));setDirty(false);setChanged(false);setMessage('已保存。点击“使用此配置”可切换下一次请求。');}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function activate(){
  if(!data||!selected)return;busyRef.current=true;setBusy(true);setError('');
  try{const next=await invoke<Snapshot>('api_profiles_activate',{id:selected.id,revision:data.revision});setData(next);setChanged(false);setMessage('已切换，下次请求生效；正在进行的回复继续使用原配置。');}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function close(){if(!await discard())return;if(isTauri())await closeApproved();}
 return <main className="settings-page">
  {dialog}
  <section className="settings-board" aria-label="璃奈板设置">
   <img className="settings-frame" src="/assets/rina/boards/electronic-faithful.svg" alt="" draggable={false}/>
   <svg className="settings-white-screen" viewBox={BOARD.viewBox} aria-hidden="true"><path d={BOARD.screen} fill="white"/></svg>
   <svg className="settings-drag-surface" viewBox={BOARD.viewBox} aria-label="拖动璃奈板移动设置窗口">
    <path data-tauri-drag-region d={`${BOARD.shell} ${BOARD.screen}`} fillRule="evenodd"/>
   </svg>
   <nav className="settings-stars" aria-label="设置窗口操作">
    <button type="button" style={boardStarPosition(0)} title={section==='settings'?'扩展工具':'返回设置'} aria-label={section==='settings'?'扩展工具':'返回设置'} onClick={()=>setSection(s=>s==='settings'?'extensions':'settings')}><span>{section==='settings'?'＋':'‹'}</span></button>
    <button type="button" style={boardStarPosition(1)} title="最小化设置" aria-label="最小化设置" onClick={()=>{if(isTauri())void getCurrentWindow().minimize();}}><span>−</span></button>
    <button type="button" style={boardStarPosition(2)} title="关闭设置" aria-label="关闭设置" onClick={()=>void close()}><span>×</span></button>
   </nav>
   <div className="settings-screen">
    <header><div><span className="settings-eyebrow">RINA DESK</span><h1>{section==='settings'?'设置':'扩展工具'}</h1></div></header>
    <ExtensionsPage hidden={section!=='extensions'}/>
    <div className="settings-main" hidden={section!=='settings'}>
    <nav className="settings-tabs" aria-label="设置分类">{[{id:'art',label:'美术'},{id:'api',label:'API 配置'},{id:'chat',label:'Chat'},{id:'general',label:'通用'}].map(t=><button key={t.id} type="button" aria-current={tab===t.id?'page':undefined} onClick={()=>setTab(t.id)}>{t.label}</button>)}</nav>
    <div className="settings-scroll" data-tab={tab}>
     <div className="art-tab" hidden={tab!=='art'}><ArtPicker onDirtyChange={setArtDirty}/></div>
     <div hidden={tab!=='chat'}><ChatSettings onDirtyChange={setChatDirty}/></div>
     {tab==='general'&&<GeneralSettings/>}
     <div className="api-tab" hidden={tab!=='api'}>
      <SettingsDisclosure title="账户用量" defaultOpen><BillingStatus onDirtyChange={setBillingDirty}/></SettingsDisclosure>
      <SettingsDisclosure title="API 配置">
      <div className="api-group-heading"><strong>Chat / Tomo</strong><GetApiButton/></div>
      {changed&&<div className="settings-warning">配置文件已在外部修改，草稿已保留。<button disabled={busy} onClick={async()=>{if(await discard()){dirtyRef.current=false;setDirty(false);setChanged(false);setEditing(null);setDraft(empty());void load();}}}>重新载入</button></div>}
      {error&&<p className="settings-error" role="alert">{error}</p>}
      {message&&<p className="settings-success" role="status">{message}</p>}
      <div className="api-layout"><aside className="api-profiles" aria-label="已保存的 API 配置">
       {data?.profiles.map(p=><button type="button" key={p.id} aria-pressed={editing===p.id} disabled={busy} onClick={()=>edit(p)}><strong>{p.name}</strong><span>{p.id===data.active?'使用中':p.ready?p.model:'待补全'}</span></button>)}
       <button type="button" className="api-add" aria-pressed={Boolean(data)&&editing===null} disabled={busy} onClick={()=>edit()}>＋ 添加配置</button>
      </aside><form className="api-editor" onSubmit={e=>{e.preventDefault();void save();}}>
       <h2>{selected?.readOnly?'现有配置':editing?'编辑配置':'添加 API'}</h2>
       {selected?.readOnly?<dl><dt>基础地址</dt><dd>{selected.baseUrl}</dd><dt>模型</dt><dd>{selected.model||'未设置'}</dd><dt>密钥</dt><dd>{selected.hasKey?'已设置（不回显）':'未设置'}</dd></dl>:<>
        <div className="api-fields"><label>配置代号<input required pattern="[a-z0-9_]{1,40}" maxLength={40} placeholder="ds / qwen" value={draft.id} disabled={busy||editing!==null} onChange={e=>change('id',e.target.value.toLowerCase())}/></label><label>显示名称<input maxLength={80} placeholder="例如 DeepSeek" value={draft.name} disabled={busy} onChange={e=>change('name',e.target.value)}/></label>
        <label className="field-wide">基础地址 URL<input type="url" required placeholder="https://api.example.com/v1" value={draft.baseUrl} disabled={busy} onChange={e=>change('baseUrl',e.target.value)}/></label>
        <label>模型 Model<input required placeholder="模型的准确名称" value={draft.model} disabled={busy} onChange={e=>change('model',e.target.value)}/></label>
        <label>API Key<input type="password" autoComplete="new-password" required={!selected?.hasKey} placeholder={selected?.hasKey?'已设置；留空保留原密钥':'输入密钥'} value={draft.key} disabled={busy} onChange={e=>change('key',e.target.value)}/></label></div>
       </>}
       <div className="api-actions">{!selected?.readOnly&&<button className="settings-primary" type="submit" disabled={busy||!data||!isTauri()||changed}>{busy?'处理中…':'保存配置'}</button>}{selected&&<button type="button" disabled={busy||dirty||changed||!selected.ready||data?.active===selected.id} onClick={()=>void activate()}>{data?.active===selected.id?'当前使用中':'使用此配置'}</button>}</div>
      </form></div>
      <details className="api-file"><summary>配置文件与手动编辑</summary><p>{data ? displayConfigPath(data.path) : '正在读取配置位置…'}</p><code>OURDESKPET_ACTIVE_PROFILE=ds<br/>OURDESKPET_PROFILE_DS_NAME=DeepSeek<br/>OURDESKPET_PROFILE_DS_BASE_URL=…<br/>OURDESKPET_PROFILE_DS_API_KEY=…<br/>OURDESKPET_PROFILE_DS_MODEL=…</code></details>
      </SettingsDisclosure>
     </div>
    </div>
    </div>
   </div>
  </section>
 </main>;
}
