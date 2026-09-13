import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {ArtPicker} from './ArtPicker';
import './SettingsPage.css';

type Profile={id:string;name:string;baseUrl:string;model:string;hasKey:boolean;ready:boolean;readOnly:boolean};
type Snapshot={revision:string;path:string;active:string;profiles:Profile[]};
type Draft={id:string;name:string;baseUrl:string;model:string;key:string};
const empty=():Draft=>({id:'',name:'',baseUrl:'',model:'',key:''});
const preview:Snapshot={revision:'preview',path:'浏览器预览 · 配置不会写入',active:'legacy',profiles:[]};

export function SettingsPage(){
 const [tab,setTab]=useState('art');
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
   if(!dirtyRef.current && dataRef.current && next.revision!==dataRef.current.revision){
    const p=next.profiles.find(p=>p.id===editingRef.current);
    setEditing(p?.id??null);setDraft(p?{id:p.id,name:p.name,baseUrl:p.baseUrl,model:p.model,key:''}:empty());
   }
   setData(next);
  }catch(e){setError(String(e));}
 },[]);
 useEffect(()=>{void load();const refresh=()=>void load();window.addEventListener('focus',refresh);const timer=setInterval(refresh,4000);return()=>{clearInterval(timer);window.removeEventListener('focus',refresh);};},[load]);
 useEffect(()=>{
  if(!isTauri())return;let disposed=false;let off:(()=>void)|undefined;
  void getCurrentWindow().onCloseRequested(event=>{if(dirtyRef.current&&!window.confirm('放弃尚未保存的 API 草稿并关闭设置？'))event.preventDefault();}).then(fn=>{if(disposed)fn();else off=fn;}).catch(console.error);
  return()=>{disposed=true;off?.();};
 },[]);
 const selected=data?.profiles.find(p=>p.id===editing);
 function discard(){return !dirty||window.confirm('放弃尚未保存的 API 草稿？');}
 function edit(p?:Profile){if(!discard())return;setEditing(p?.id??null);setDraft(p?{id:p.id,name:p.name,baseUrl:p.baseUrl,model:p.model,key:''}:empty());setDirty(false);setMessage('');setError('');}
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
 async function close(){if(!discard())return;if(isTauri()){dirtyRef.current=false;await getCurrentWindow().close();}}
 return <main className="settings-page">
  <section className="settings-board" aria-label="璃奈板设置">
   <img className="settings-frame" data-tauri-drag-region title="拖动璃奈板移动窗口" src="/assets/rina/boards/electronic-faithful.svg" alt="" draggable={false}/>
   <svg className="settings-white-screen" viewBox="235 30 1070 900" aria-hidden="true"><path d="M497 219 768 310 1038 219 1159 281V334L1207 364V743L1086 867H440L331 743V364L374 334V281Z" fill="white"/></svg>
   <nav className="settings-stars" aria-label="设置窗口操作">
    <button type="button" disabled title="预留入口" aria-label="预留入口"/>
    <button type="button" title="最小化设置" aria-label="最小化设置" onClick={()=>{if(isTauri())void getCurrentWindow().minimize();}}><span>−</span></button>
    <button type="button" title="关闭设置" aria-label="关闭设置" onClick={()=>void close()}><span>×</span></button>
   </nav>
   <div className="settings-screen">
    <header><div><span className="settings-eyebrow">RINA DESK</span><h1>设置</h1></div><span className="settings-caption">让这里更像你的桌面</span></header>
    <nav className="settings-tabs" aria-label="设置分类">{[{id:'art',label:'人物与美术'},{id:'api',label:'API 配置'},{id:'general',label:'通用'}].map(t=><button key={t.id} type="button" aria-current={tab===t.id?'page':undefined} onClick={()=>setTab(t.id)}>{t.label}</button>)}</nav>
    <div className="settings-scroll" data-tab={tab}>
     {tab==='art'&&<ArtPicker/>}
     {tab==='general'&&<><div className="setting-row"><div><strong>开机启动</strong><p>预留 · 后续支持登录 Windows 后启动桌宠</p></div><input type="checkbox" disabled aria-label="开机启动（尚未开放）"/></div><p className="settings-note">目前不会更改 Windows 的启动设置。</p></>}
     {tab==='api'&&<>
      <p className="settings-note">支持 OpenAI 兼容接口。保存配置后再启用，切换无需重启。</p>
      {changed&&<div className="settings-warning">配置文件已在外部修改，草稿已保留。<button disabled={busy} onClick={()=>{if(discard()){dirtyRef.current=false;setDirty(false);setChanged(false);setEditing(null);setDraft(empty());void load();}}}>重新载入</button></div>}
      {error&&<p className="settings-error" role="alert">{error}</p>}
      {message&&<p className="settings-success" role="status">{message}</p>}
      <div className="api-layout"><aside className="api-profiles" aria-label="已保存的 API 配置">
       {data?.profiles.map(p=><button type="button" key={p.id} aria-pressed={editing===p.id} disabled={busy} onClick={()=>edit(p)}><strong>{p.name}</strong><span>{p.id===data.active?'使用中':p.ready?p.model:'待补全'}</span></button>)}
       <button type="button" className="api-add" disabled={busy} onClick={()=>edit()}>＋ 添加配置</button>
      </aside><form className="api-editor" onSubmit={e=>{e.preventDefault();void save();}}>
       <h2>{selected?.readOnly?'现有配置':editing?'编辑配置':'添加 API'}</h2>
       {selected?.readOnly?<><p className="settings-note">兼容原来的环境配置。可继续使用，或新增 ds、qwen 等独立方案。</p><dl><dt>基础地址</dt><dd>{selected.baseUrl}</dd><dt>模型</dt><dd>{selected.model||'未设置'}</dd><dt>密钥</dt><dd>{selected.hasKey?'已设置（不回显）':'未设置'}</dd></dl></>:<>
        <div className="api-fields"><label>配置代号<input required pattern="[a-z0-9_]{1,40}" maxLength={40} placeholder="ds / qwen" value={draft.id} disabled={busy||editing!==null} onChange={e=>change('id',e.target.value.toLowerCase())}/></label><label>显示名称<input maxLength={80} placeholder="例如 DeepSeek" value={draft.name} disabled={busy} onChange={e=>change('name',e.target.value)}/></label>
        <label className="field-wide">基础地址 URL<input type="url" required placeholder="https://api.example.com/v1" value={draft.baseUrl} disabled={busy} onChange={e=>change('baseUrl',e.target.value)}/></label>
        <label>模型 Model<input required placeholder="模型的准确名称" value={draft.model} disabled={busy} onChange={e=>change('model',e.target.value)}/></label>
        <label>API Key<input type="password" autoComplete="new-password" required={!selected?.hasKey} placeholder={selected?.hasKey?'已设置；留空保留原密钥':'输入密钥'} value={draft.key} disabled={busy} onChange={e=>change('key',e.target.value)}/></label></div>
       </>}
       <div className="api-actions">{!selected?.readOnly&&<button className="settings-primary" type="submit" disabled={busy||!data||!isTauri()||changed}>{busy?'处理中…':'保存配置'}</button>}{selected&&<button type="button" disabled={busy||dirty||changed||!selected.ready||data?.active===selected.id} onClick={()=>void activate()}>{data?.active===selected.id?'当前使用中':'使用此配置'}</button>}</div>
      </form></div>
      <details className="api-file"><summary>配置文件与手动编辑</summary><p>{data?.path??'正在读取配置位置…'}</p><p>密钥保存在本机 .env 中，不回显。外部编辑会自动检测；草稿冲突时请重新载入。</p><code>OURDESKPET_ACTIVE_PROFILE=ds<br/>OURDESKPET_PROFILE_DS_NAME=DeepSeek<br/>OURDESKPET_PROFILE_DS_BASE_URL=…<br/>OURDESKPET_PROFILE_DS_API_KEY=…<br/>OURDESKPET_PROFILE_DS_MODEL=…</code></details>
     </>}
    </div>
   </div>
  </section>
 </main>;
}
