import {invoke,isTauri} from '@tauri-apps/api/core';
import {listen,emitTo} from '@tauri-apps/api/event';
import {useCallback,useEffect,useRef,useState} from 'react';
import {buildContext,validateImages} from './context';
import type {ChatCompleteEvent,ChatDeltaEvent,ChatErrorEvent,ChatStreamRequest,DialogueMessage,ImagePayload,LlmConfigStatus,SearchMode,SearchSource,SendMessageOptions} from './types';

const INITIAL:DialogueMessage={id:'initial-assistant',role:'assistant',state:'complete',content:'我在这里。聊天会保留到桌宠退出；只有“重置对话”会主动清空。'};
const id=(prefix:string)=>`${prefix}-${crypto.randomUUID()}`;

export function useDialogueChat(){
 const [messages,setMessages]=useState<DialogueMessage[]>([INITIAL]);
 const [input,setInput]=useState('');const [pendingImages,setPendingImages]=useState<ImagePayload[]>([]);
 const [config,setConfig]=useState<LlmConfigStatus|null>(null);const [status,setStatus]=useState('正在读取配置…');
 const [isSending,setIsSending]=useState(false);const [isStopping,setIsStopping]=useState(false);
 const [searchMode,setSearchMode]=useState<SearchMode>('auto');const [contextNote,setContextNote]=useState('');
 const requestRef=useRef<string|null>(null),lock=useRef(false),stopWanted=useRef(false),resetWanted=useRef(false);
 const unlisteners=useRef<Array<()=>void>>([]);const mounted=useRef(true);
 const isConfigured=Boolean(config?.hasApiKey&&config.model);
 const reset=useCallback(()=>{setMessages([INITIAL]);setInput('');setPendingImages([]);setContextNote('');setStatus('对话已重置。');if(isTauri())void emitTo('main','deskpet-task-read',{source:'chat'}).catch(()=>{});},[]);
 const refreshConfig=useCallback(async()=>{
  try{const next=await invoke<LlmConfigStatus>('llm_config_status');setConfig(next);if(!lock.current)setStatus(next.hasApiKey&&next.model?'就绪。':'请先在设置中配置 API。');return next;}
  catch(e){setConfig(null);if(!lock.current)setStatus(`读取配置失败：${String(e)}`);return null;}
 },[]);
 useEffect(()=>{mounted.current=true;void refreshConfig();const refresh=()=>{if(!lock.current)void refreshConfig();};let disposed=false;let off:(()=>void)|undefined;
  window.addEventListener('focus',refresh);
  if(isTauri())void listen('deskpet-api-config-changed',refresh).then(fn=>{if(disposed)fn();else off=fn;}).catch(()=>{});
  return()=>{disposed=true;mounted.current=false;window.removeEventListener('focus',refresh);off?.();unlisteners.current.forEach(fn=>fn());};
 },[refreshConfig]);
 const addPendingImages=useCallback((images:ImagePayload[])=>{
  setPendingImages(current=>{try{validateImages([...current,...images]);return [...current,...images];}catch(e){setStatus(String(e));return current;}});
 },[]);
 const removePendingImage=useCallback((index:number)=>setPendingImages(current=>current.filter((_,i)=>i!==index)),[]);
 const clearPendingImages=useCallback(()=>setPendingImages([]),[]);
 const stopMessage=useCallback(async()=>{
  if(!lock.current)return;stopWanted.current=true;setIsStopping(true);setStatus('正在停止…');
  if(requestRef.current)try{await invoke('cancel_chat_stream',{requestId:requestRef.current});}catch(e){setIsStopping(false);setStatus(`停止失败：${String(e)}，可再次尝试。`);}
 },[]);
 const clearConversation=useCallback(()=>{if(lock.current){resetWanted.current=true;void stopMessage();}else reset();},[reset,stopMessage]);

 const run=useCallback(async(options:SendMessageOptions={},retry=false)=>{
  if(lock.current)return;lock.current=true;stopWanted.current=false;resetWanted.current=false;setIsSending(true);setIsStopping(false);
  let assistantId:string|null=null;let completed=false;let requestId:string|null=null;
  const off:Array<()=>void>=[];unlisteners.current=off;
  try{
   // Refresh immediately before sending: a hidden window may have missed config events.
   const fresh=await invoke<LlmConfigStatus>('llm_config_status');setConfig(fresh);
   if(!fresh.hasApiKey||!fresh.model)throw new Error('请先在设置中配置 API。');
   if(searchMode==='required'&&!fresh.searchAvailable)throw new Error('请在 .env 填写 TAVILY_API_KEY 并启用搜索。');
   let history=messages;let images=options.images??pendingImages;let text=(options.text??input).trim();
   if(retry){const index=messages.map(m=>m.role).lastIndexOf('user');if(index<0)return;const old=messages[index];history=messages.slice(0,index);text=old.content;images=old.images??[];}
   text=text||(images.length?options.fallbackText??'请看这张图片。':'');if(!text)return;
   validateImages(images);
   const user:DialogueMessage={id:id('user'),role:'user',state:'complete',content:text,images};
   const context=buildContext(history,user,fresh.contextChars??24000);
   if(stopWanted.current)return;
   assistantId=id('assistant');requestId=id('chat');
   const update=(fn:(m:DialogueMessage)=>DialogueMessage)=>{if(mounted.current)setMessages(current=>current.map(m=>m.id===assistantId?fn(m):m));};
   // Listeners are created inside the guarded scope; partial setup is always cleaned up.
   off.push(await listen<ChatDeltaEvent>('llm-chat-delta',event=>{if(event.payload.requestId!==requestId)return;update(m=>({...m,content:m.content+event.payload.delta}));setStatus('正在回复…');}));
   off.push(await listen<ChatCompleteEvent>('llm-chat-complete',event=>{if(event.payload.requestId!==requestId)return;completed=true;const state=event.payload.status==='cancelled'?'cancelled':event.payload.status==='truncated'?'truncated':'complete';update(m=>({...m,state}));setStatus(state==='cancelled'?'已停止。':state==='truncated'?'回复达到长度限制，内容可能不完整。':'就绪。');}));
   off.push(await listen<ChatErrorEvent>('llm-chat-error',event=>{if(event.payload.requestId!==requestId)return;completed=true;update(m=>({...m,state:'error',error:event.payload.message}));setStatus(event.payload.message);}));
   off.push(await listen<{requestId:string;phase:string;detail:string}>('llm-chat-phase',event=>{if(event.payload.requestId!==requestId)return;const p=event.payload;if(p.phase==='search-warning')update(m=>({...m,searchWarning:p.detail}));setStatus(p.phase==='searching'?`正在搜索：${p.detail}`:p.phase==='search-warning'?`搜索提示：${p.detail}`:p.phase==='answering'?'正在整理回复…':'正在思考…');}));
   off.push(await listen<{requestId:string;sources:SearchSource[]}>('llm-chat-sources',event=>{if(event.payload.requestId!==requestId)return;update(m=>({...m,sources:event.payload.sources}));}));
   if(stopWanted.current)return;
   setMessages([...history,user,{id:assistantId,role:'assistant',state:'streaming',content:''}]);
   if(!retry){setInput('');setPendingImages([]);}setContextNote(context.omitted?`本次仅发送最近上下文，省略了 ${context.omitted} 轮较早对话；完整聊天仍保留在窗口中。`:'');
   requestRef.current=requestId;setStatus('正在思考…');
   const request:ChatStreamRequest={requestId,messages:context.messages,images:images.length?images:undefined,searchMode,currentDate:new Date().toISOString().slice(0,10)};
   const result=await invoke<string>('chat_stream',{request});
   // The command result is authoritative even if the completion event is delayed.
   if(!completed){const state=result==='cancelled'?'cancelled':result==='truncated'?'truncated':'complete';update(m=>({...m,state}));setStatus(state==='cancelled'?'已停止。':state==='truncated'?'回复达到长度限制，内容可能不完整。':'就绪。');}

  }catch(e){const error=String(e);if(assistantId)setMessages(current=>current.map(m=>m.id===assistantId?{...m,state:'error',error}:m));setStatus(error);}
  finally{off.forEach(fn=>fn());unlisteners.current=[];requestRef.current=null;lock.current=false;setIsSending(false);setIsStopping(false);if(resetWanted.current){resetWanted.current=false;reset();}else if(stopWanted.current&&!completed)setStatus('已停止。');}
 },[messages,input,pendingImages,searchMode,reset]);
 const sendMessage=useCallback((options:SendMessageOptions={})=>run(options),[run]);
 const retryLast=useCallback(()=>run({},true),[run]);
 return {messages,input,pendingImages,config,status,isConfigured,isSending,isStopping,searchMode,setSearchMode,contextNote,setInput,setStatus,
  addPendingImages,removePendingImage,clearPendingImages,sendMessage,stopMessage,clearConversation,refreshConfig,retryLast};
}
