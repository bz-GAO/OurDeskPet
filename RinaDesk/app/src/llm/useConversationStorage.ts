import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import type {ChatMode,DialogueMessage,StoredConversation} from './types';
import {conversationTitle} from './conversationTitle';

export type StorageSettings={enabled:boolean;directory:string};
export function useStorageSettings(){
 const [settings,setSettings]=useState<StorageSettings|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const refresh=useCallback(async()=>{if(!isTauri())return;try{const value=await invoke<StorageSettings>('chat_storage_settings');if(typeof value?.enabled!=='boolean'||!value.directory)throw Error('对话存储配置不可用');setSettings(value);setError('');}catch(e){setError(String(e));}},[]);
 useEffect(()=>{void refresh();let alive=true,off:(()=>void)|undefined;void listen('deskpet-chat-storage-changed',()=>void refresh()).then(fn=>{if(alive)off=fn;else fn();}).catch(()=>{});return()=>{alive=false;off?.();};},[refresh]);
 const change=useCallback(async(command:'chat_storage_enable'|'chat_storage_choose',args?:{enabled:boolean})=>{setBusy(true);try{const value=await invoke<StorageSettings>(command,args);setSettings(value);setError('');}catch(e){setError(String(e));}finally{setBusy(false);}},[]);
 return {settings,error,busy,change};
}
type Snapshot={sessionId:string;chatMode:ChatMode;messages:DialogueMessage[];conversationTitle:string;isSending:boolean;storage?:StoredConversation};
type Draft={title:string;mode:ChatMode;messages:Array<Record<string,unknown>>};
const sameDirectory=(a:string|undefined,b:string)=>a!==undefined&&a.replace(/^\\\\\?\\/,'').replace(/\\/g,'/').toLowerCase()===b.replace(/^\\\\\?\\/,'').replace(/\\/g,'/').toLowerCase();
const draftOf=(chat:Snapshot):Draft=>{const first=chat.messages.find(m=>m.role==='user');return {title:chat.conversationTitle||conversationTitle(first?.content??'',{images:Boolean(first?.images?.length),files:Boolean(first?.files?.length)}),mode:chat.chatMode,messages:chat.messages.map(message=>({role:message.role,content:message.content,state:message.state==='streaming'?'cancelled':message.state,images:(message.images??[]).map(({mimeType,width,height,byteSize,name})=>({mimeType,width,height,byteSize,name})),files:message.files??[],sources:message.sources??[],error:message.error,searchWarning:message.searchWarning,voice:message.voice,suggestsProject:message.suggestsProject||undefined}))};};
type Entry={id:string;record?:StoredConversation;lastSaved:string;checkpoint:number;draft?:Draft;timer?:ReturnType<typeof setTimeout>;chain:Promise<void>};
export function useConversationStorage(chat:Snapshot){
 const config=useStorageSettings();const settingsRef=useRef(config.settings);settingsRef.current=config.settings;
 const latest=useRef(chat);latest.current=chat;
 const [records,setRecords]=useState<StoredConversation[]>([]),[error,setError]=useState(''),[pending,setPending]=useState(0);
 const entries=useRef(new Map<string,Entry>()),alive=useRef(true),forgotten=useRef(new Set<string>());
 const acceptRecord=useCallback((record:StoredConversation)=>{
  for(const entry of entries.current.values())if(entry.id===record.id)entry.record=record;
  setRecords(current=>record.visible&&!forgotten.current.has(record.id)?[record,...current.filter(item=>item.id!==record.id)]:current.filter(item=>item.id!==record.id));
 },[]);
 const enqueue=useCallback((entry:Entry)=>{
  if(entry.timer)clearTimeout(entry.timer);entry.timer=undefined;
  const draft=entry.draft,settings=settingsRef.current;if(!draft||!settings?.enabled)return entry.chain;
  const signature=JSON.stringify(draft);
  setPending(value=>value+1);
  entry.chain=entry.chain.catch(()=>{}).then(async()=>{
   if(!settingsRef.current?.enabled||settingsRef.current.directory!==settings.directory)return;
   if(signature===entry.lastSaved&&sameDirectory(entry.record?.directory,settings.directory)){if(alive.current)setError('');return;}
   const record=await invoke<StoredConversation>('chat_storage_save',{id:entry.id,directory:settings.directory,expected:sameDirectory(entry.record?.directory,settings.directory)?entry.record?.revision:null,request:{...draft,exportedAt:new Date().toISOString()}});
   entry.record=record;entry.lastSaved=signature;if(alive.current){acceptRecord(record);setError('');}
  }).catch(e=>{if(alive.current)setError(`保存失败：${String(e)}`);throw e;}).finally(()=>{if(alive.current)setPending(value=>value-1);});
  // Keep rejections observable for explicit flush, without an unhandled promise.
  void entry.chain.catch(()=>{});return entry.chain;
 },[acceptRecord]);
 const flush=useCallback(async()=>{if(!settingsRef.current)throw Error('对话存储配置尚未读取');if(!settingsRef.current.enabled){await Promise.all([...entries.current.values()].map(entry=>entry.chain.catch(()=>{})));return;}
  const current=latest.current;if(current.messages.length){let entry=entries.current.get(current.sessionId);if(!entry){entry={id:current.storage?.id??crypto.randomUUID(),record:current.storage,lastSaved:'',checkpoint:0,chain:Promise.resolve()};entries.current.set(current.sessionId,entry);}entry.draft=draftOf(current);}
  await Promise.all([...entries.current.values()].map(enqueue));
 },[enqueue]);
 useEffect(()=>{let active=true,off:(()=>void)|undefined;void listen<string>('deskpet-quit-error',event=>setError(event.payload)).then(fn=>{if(active)off=fn;else fn();}).catch(()=>{});return()=>{active=false;off?.();};},[]);
 useEffect(()=>{let active=true,off:(()=>void)|undefined;
  void listen('deskpet-before-quit',()=>{void flush().then(()=>invoke('chat_storage_flush_done',{error:null})).catch(error=>invoke('chat_storage_flush_done',{error:String(error)}));}).then(fn=>{if(active)off=fn;else fn();}).catch(()=>{});
  return()=>{active=false;off?.();};
 },[flush]);
 useEffect(()=>{
  if(!config.settings)return;let active=true;
  void invoke<{records:StoredConversation[];skipped:number}>('chat_storage_list').then(value=>{if(active){setRecords(value.records);setError(value.skipped?'部分对话文件无法载入':'');}}).catch(e=>{if(active)setError(String(e));});
  return()=>{active=false;};
 },[config.settings?.directory]);
 useEffect(()=>{
  if(!config.settings?.enabled){for(const entry of entries.current.values()){if(entry.timer)clearTimeout(entry.timer);entry.timer=undefined;}return;}
  if(!chat.messages.length)return;
  let entry=entries.current.get(chat.sessionId);
  if(!entry){
   // Reopening a managed file creates a new model session, not a second writer.
   if(chat.storage)for(const [session,previous] of entries.current){if(previous.id===chat.storage.id){if(previous.timer)clearTimeout(previous.timer);entries.current.delete(session);}}
   entry={id:chat.storage?.id??crypto.randomUUID(),record:chat.storage,lastSaved:'',checkpoint:0,chain:Promise.resolve()};entries.current.set(chat.sessionId,entry);
  }
  // One checkpoint at the start of a turn, then one completed-turn save. Never
  // serialize/write each token. Interrupted checkpoints reload as cancelled.
  if(chat.isSending&&entry.checkpoint===chat.messages.length)return;
  entry.checkpoint=chat.messages.length;
  entry.draft=draftOf(chat);
  if(chat.storage&&entry.lastSaved===''&&entry.record===chat.storage){entry.lastSaved=JSON.stringify(entry.draft);return;}
  if(entry.timer)clearTimeout(entry.timer);
  const current=entry;entry.timer=setTimeout(()=>void enqueue(current).catch(()=>{}),chat.isSending?0:200);
 },[chat.messages,chat.conversationTitle,chat.chatMode,chat.sessionId,chat.isSending,chat.storage,config.settings,enqueue]);
 useEffect(()=>{alive.current=true;const hidden=()=>{if(document.hidden)void flush().catch(()=>{});};document.addEventListener('visibilitychange',hidden);
  return()=>{alive.current=false;document.removeEventListener('visibilitychange',hidden);for(const entry of entries.current.values())if(entry.timer)clearTimeout(entry.timer);};
 },[flush]);
 const rename=async(record:StoredConversation,title:string)=>{try{await flush();const updated=await invoke<StoredConversation>('chat_storage_rename',{id:record.id,expected:entries.current.get(chat.sessionId)?.id===record.id?entries.current.get(chat.sessionId)?.record?.revision??record.revision:record.revision,title});acceptRecord(updated);return updated;}catch(e){setError(String(e));return null;}};
 const forget=async(id:string)=>{try{await invoke('chat_storage_forget',{id});forgotten.current.add(id);setRecords(current=>current.filter(record=>record.id!==id));}catch(e){setError(String(e));}};
 const removeRecord=useCallback((id:string)=>{setRecords(current=>current.filter(record=>record.id!==id));},[]);
 return {...config,records,error:error||config.error,saving:pending>0,flush,rename,forget,removeRecord,currentId:chat.storage?.id??entries.current.get(chat.sessionId)?.id};
}
