import {lazy,Suspense,useEffect,useState} from 'react';
import {ConfirmDialog} from '../components/ConfirmDialog';
import type {MouseEvent} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {openUrl} from '@tauri-apps/plugin-opener';
import type {RinaYakiStatus,RinaYakiToolCapability} from './rinayaki/RinaYakiPage';
import './ExtensionsPage.css';

const RinaYakiPage=lazy(()=>import('./rinayaki/RinaYakiPage'));
const RinaYakiLivePage=lazy(()=>import('./rinayaki/RinaYakiLivePage'));
const RinaTomoPage=lazy(()=>import('./rinatomo/RinaTomoPage'));
const legacyVideo:RinaYakiToolCapability={id:'video',name:'视频翻译',available:true,embeddedReady:false};
const emptyStatus:RinaYakiStatus={id:'rinayaki',connected:false,available:false,embeddedReady:false,path:null,version:null,tools:[]};
const repositories={rinayaki:'https://github.com/bz-GAO/RinaYaki',rinatomo:'https://github.com/bz-GAO/RinaTomo'} as const;

export function ExtensionsPage({hidden=false}:{hidden?:boolean}){
 const [tool,setTool]=useState<RinaYakiStatus>(emptyStatus);
 const [page,setPage]=useState<'video'|'live'|'tomo'|'add'>('video');
 useEffect(()=>{
  if(!isTauri())return;
  let disposed=false;let off:(()=>void)|undefined;
  void import('@tauri-apps/api/event').then(async ({listen})=>{
    const fn=await listen('deskpet-open-yaki',()=>setPage('video'));
    if(disposed)fn();else off=fn;
  }).catch(()=>{});
  return()=>{disposed=true;off?.();};
 },[]);
 const [busy,setBusy]=useState(false);
 const [statusLoading,setStatusLoading]=useState(isTauri());
 const [managing,setManaging]=useState(false);
 const [error,setError]=useState('');
 const [confirmDisconnect,setConfirmDisconnect]=useState(false);
 useEffect(()=>{if(!isTauri()||hidden||busy)return;let alive=true;
  void invoke<RinaYakiStatus>('extension_status').then(next=>{if(alive)setTool(next);}).catch(e=>{if(alive)setError(String(e));}).finally(()=>{if(alive)setStatusLoading(false);});
  return()=>{alive=false;};
 },[hidden,busy]);
 async function connect(){
  setBusy(true);setError('');
  try{const next=await invoke<RinaYakiStatus>('extension_connect');setTool(next);setManaging(false);if(next.connected)setPage('video');}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 function disconnect(){setError('');setConfirmDisconnect(true);}
 async function performDisconnect(){
  setBusy(true);setError('');
  try{setTool(await invoke<RinaYakiStatus>('extension_disconnect'));setPage('add');setManaging(false);setConfirmDisconnect(false);}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function launch(){
  setBusy(true);setError('');
  try{await invoke('extension_launch');}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 function openRepository(event:MouseEvent<HTMLAnchorElement>,url:string){
  if(!isTauri())return;
  event.preventDefault();
  void openUrl(url).catch(e=>setError(`打开 GitHub 失败：${String(e)}`));
 }
 const capabilities=tool.tools?.length?tool.tools:[legacyVideo];
 const video=capabilities.find(item=>item.id==='video');
 const live=capabilities.find(item=>item.id==='live');
 useEffect(()=>{if(page==='live'&&!live)setPage('video');},[page,live]);
 return <section className="extensions-content" aria-label="扩展工具" hidden={hidden}>
  {confirmDisconnect&&<ConfirmDialog title="卸载 RinaYaki？" busy={busy} confirmLabel="确认卸载" onCancel={()=>setConfirmDisconnect(false)} onConfirm={()=>void performDisconnect()}>
   <p>视频翻译与实时翻译会一并移出扩展工具。</p>
   {error&&<p className="extensions-error" role="alert">{error}</p>}
  </ConfirmDialog>}
  {statusLoading?<div className="extensions-loading" role="status">正在读取扩展工具…</div>:<>
  <nav className="extensions-tabs" aria-label="已接入的扩展">
   {tool.connected&&video&&<span className={`extensions-tab-item${managing?' is-managing':''}`}><button type="button" aria-current={page==='video'?'page':undefined} onClick={()=>setPage('video')}>视频翻译</button>{managing&&<button type="button" className="extensions-tab-close" aria-label="卸载视频翻译扩展" title="卸载扩展" onClick={disconnect}>×</button>}</span>}
   {tool.connected&&live&&<span className={`extensions-tab-item${managing?' is-managing':''}`}><button type="button" aria-current={page==='live'?'page':undefined} onClick={()=>setPage('live')}>实时翻译</button>{managing&&<button type="button" className="extensions-tab-close" aria-label="卸载实时翻译扩展" title="卸载扩展" onClick={disconnect}>×</button>}</span>}
   <button type="button" aria-current={page==='tomo'?'page':undefined} onClick={()=>setPage('tomo')}>QQ Bot</button>
   {false&&<button type="button" className="extensions-add-tab" aria-current={page==='add'?'page':undefined} onClick={()=>setPage('add')}>＋ 添加工具</button>}
   {false&&tool.connected&&<button type="button" className="extensions-manage" aria-pressed={managing} onClick={()=>setManaging(value=>!value)}>{managing?'完成':'管理'}</button>}
  </nav>
  {error&&<p className="extensions-error" role="alert">{error}</p>}
  {page==='add'&&<div className="extensions-add-panel">
   <div className="extensions-tool-row">
    <div><strong>RinaYaki</strong><span>视频翻译 · 实时翻译，一次接入</span></div>
    <div className="extensions-row-actions"><a href={repositories.rinayaki} target="_blank" rel="noreferrer" onClick={event=>openRepository(event,repositories.rinayaki)}>GitHub</a><button type="button" disabled={busy||!isTauri()} onClick={()=>void connect()}>{busy?'检测中…':tool.connected?'重新定位':'接入'}</button></div>
   </div>
   <div className="extensions-tool-row">
    <div><strong>RinaTomo</strong><span>QQ Bot · 登录、消息服务与权限管理</span></div>
    <div className="extensions-row-actions"><a href={repositories.rinatomo} target="_blank" rel="noreferrer" onClick={event=>openRepository(event,repositories.rinatomo)}>GitHub</a><button type="button" onClick={()=>setPage('tomo')}>打开</button></div>
   </div>
  </div>}
  {page==='video'&&(tool.connected&&video?<Suspense fallback={<p className="extensions-hint">正在打开视频翻译…</p>}><RinaYakiPage key={tool.path??'unregistered'} tool={tool} busy={busy} onLaunch={()=>void launch()} onRelocate={()=>{setError("内置组件路径由安装器管理，请修复安装。");}}/></Suspense>:<button type="button" className="extensions-add" onClick={()=>setPage('add')}><span aria-hidden="true">＋</span><strong>添加工具</strong></button>)}
  {page==='live'&&tool.connected&&live&&<Suspense fallback={<p className="extensions-hint">正在打开实时翻译…</p>}><RinaYakiLivePage key={tool.path??'unregistered'} tool={tool} capability={live} busy={busy} onLaunch={()=>void launch()} onRelocate={()=>{setError("内置组件路径由安装器管理，请修复安装。");}}/></Suspense>}
  {page==='tomo'&&<Suspense fallback={<p className="extensions-hint">正在打开 QQ Bot…</p>}><RinaTomoPage/></Suspense>}
  </>}
 </section>;
}
