import {storeImage,transportImage,releaseImageResources,releaseImages} from './imageStore';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {listen,emitTo} from '@tauri-apps/api/event';
import {useCallback,useEffect,useRef,useState} from 'react';
import type {Dispatch,SetStateAction} from 'react';
import {MAX_TURN_ATTACHMENTS,validateAttachmentCount,validateImages} from './context';
import {applyToolEvent} from './toolCalls';
import type {ToolCallEvent} from './toolCalls';
import {applyProposalEvent,applyTaskEvent} from './agentTasks';
import type {AgentProposalEvent,AgentTaskCard} from './agentTasks';
import {playSfx} from '../voice/sfx';
import {parseSpokenReply} from '../voice/voiceReply';
import {validateParsedFiles} from './fileParser';
import type {ChatCompleteEvent,ChatDeltaEvent,ChatErrorEvent,ChatMode,ChatStreamRequest,DialogueMessage,ImagePayload,ImportedConversation,LlmConfigStatus,ParsedFilePayload,PendingAttachment,SearchMode,SearchSource,SendMessageOptions} from './types';
import {conversationTitle} from './conversationTitle';


const id=(prefix:string)=>`${prefix}-${crypto.randomUUID()}`;
type ConversationState={messages:DialogueMessage[];input:string;pendingAttachments:PendingAttachment[];uploadedFiles:PendingAttachment[];contextNote:string;status:string;title:string;storage?:ImportedConversation['storage']};
const modes:ChatMode[]=['chat','project'];
const newConversation=(status='正在读取配置…',uploadedFiles:PendingAttachment[]=[]):ConversationState=>({messages:[],input:'',pendingAttachments:[],uploadedFiles,contextNote:'',status,title:''});
const readyImages=(attachments:PendingAttachment[])=>attachments.flatMap(item=>item.state==='ready'&&item.kind==='image'?[item.image]:[]);
const readyFiles=(attachments:PendingAttachment[])=>attachments.flatMap(item=>item.state==='ready'&&item.kind==='file'?[item.file]:[]);
const attachmentId=()=>id('attachment');
const sameResource=(left:PendingAttachment,right:PendingAttachment)=>left.state==='ready'&&right.state==='ready'&&left.kind===right.kind&&(left.kind==='image'&&right.kind==='image'?left.image.dataUrl===right.image.dataUrl:left.kind==='file'&&right.kind==='file'?left.file.name===right.file.name&&left.file.byteSize===right.file.byteSize&&left.file.parser===right.file.parser&&left.file.content===right.file.content:false);
const registerResources=(current:PendingAttachment[],additions:PendingAttachment[])=>additions.reduce((items,item)=>items.some(existing=>sameResource(existing,item))?items:[...items,item],current);

export function useDialogueChat(){
 const [conversations,setConversations]=useState<Record<ChatMode,ConversationState>>(()=>({chat:newConversation(),project:newConversation()}));
 const conversationsRef=useRef(conversations);useEffect(()=>{conversationsRef.current=conversations;},[conversations]);
 const updateConversation=useCallback((mode:ChatMode,update:(current:ConversationState)=>ConversationState)=>setConversations(current=>({...current,[mode]:update(current[mode])})),[]);
 const [config,setConfig]=useState<LlmConfigStatus|null>(null);
 const [isSending,setIsSending]=useState(false);const [isStopping,setIsStopping]=useState(false);
 const [searchModes,setSearchModes]=useState<Record<ChatMode,SearchMode>>({chat:'auto',project:'auto'});
 const [chatMode,setChatModeState]=useState<ChatMode>('chat');
 const active=conversations[chatMode];const searchMode=searchModes[chatMode];
 const searchOverride=useRef<Record<ChatMode,boolean>>({chat:false,project:false});
 const setSearchMode=useCallback((mode:SearchMode)=>{searchOverride.current[chatMode]=true;setSearchModes(current=>({...current,[chatMode]:mode}));},[chatMode]);
 const sessionRef=useRef<Record<ChatMode,string>>({chat:id('chat-session'),project:id('project-session')});
 const titleAttempts=useRef(new Set<string>()),manualTitles=useRef(new Set<string>());
 useEffect(()=>{
  if(isSending)return;
  for(const mode of modes){
   const current=conversations[mode],session=sessionRef.current[mode];
   if(current.storage||titleAttempts.current.has(session)||manualTitles.current.has(session))continue;
   const user=current.messages.find(message=>message.role==='user');
   const answer=current.messages.find(message=>message.role==='assistant'&&message.state==='complete'&&message.content.trim());
   if(!user||user.id.startsWith('loaded-')||!answer)continue;
   titleAttempts.current.add(session);
   void invoke<string>('chat_export_title',{mode,messages:[{role:'user',content:user.content},{role:'assistant',content:answer.content}]}).then(title=>{
    if(!mounted.current||sessionRef.current[mode]!==session||manualTitles.current.has(session)||!title?.trim())return;
    updateConversation(mode,state=>({...state,title:title.trim()}));
   }).catch(()=>{});
  }
 },[conversations,isSending,updateConversation]);
 const requestRef=useRef<string|null>(null),lock=useRef(false),stopWanted=useRef(false),resetWanted=useRef<boolean|null>(null);
 const setChatMode=useCallback((mode:ChatMode)=>{if(!lock.current)setChatModeState(mode);},[]);
 const unlisteners=useRef<Array<()=>void>>([]);const mounted=useRef(true);
 const isConfigured=Boolean(config?.hasApiKey&&config.model);
 const setModeStatus=useCallback((mode:ChatMode,status:string)=>updateConversation(mode,current=>({...current,status})),[updateConversation]);
 const setInput=useCallback<Dispatch<SetStateAction<string>>>((value)=>updateConversation(chatMode,current=>({...current,input:typeof value==='function'?value(current.input):value})),[chatMode,updateConversation]);
 const reset=useCallback((mode:ChatMode,clearUploadedFiles=true)=>{const current=conversationsRef.current[mode];const retained=clearUploadedFiles?[]:current.uploadedFiles;const otherImages=modes.filter(other=>other!==mode).flatMap(other=>{const state=conversationsRef.current[other];return [...readyImages(state.uploadedFiles),...readyImages(state.pendingAttachments),...state.messages.flatMap(message=>message.images??[])];});const retainedUrls=new Set([...readyImages(retained),...otherImages].map(image=>image.dataUrl));const releasable=[...readyImages(current.pendingAttachments),...readyImages(current.uploadedFiles),...current.messages.flatMap(message=>message.images??[])].filter(image=>!retainedUrls.has(image.dataUrl));releaseImageResources(releasable);const previous=sessionRef.current[mode];sessionRef.current[mode]=id(`${mode}-session`);if(isTauri())void invoke('clear_chat_history',{sessionId:previous}).catch(()=>{});updateConversation(mode,()=>newConversation('',retained));if(isTauri())void emitTo('main','deskpet-task-read',{source:'chat'}).catch(()=>{});},[updateConversation]);
 const refreshConfig=useCallback(async()=>{
  try{const next=await invoke<LlmConfigStatus>('llm_config_status');setConfig(next);setSearchModes(current=>Object.fromEntries(modes.map(mode=>[mode,searchOverride.current[mode]?current[mode]:(next.searchMode??'auto')])) as Record<ChatMode,SearchMode>);if(!lock.current)setConversations(current=>Object.fromEntries(modes.map(mode=>[mode,{...current[mode],status:next.hasApiKey&&next.model?'':'请先在设置中配置 API。'}])) as Record<ChatMode,ConversationState>);return next;}
  catch(e){setConfig(null);if(!lock.current)setConversations(current=>Object.fromEntries(modes.map(mode=>[mode,{...current[mode],status:`读取配置失败：${String(e)}`}])) as Record<ChatMode,ConversationState>);return null;}
 },[]);
 useEffect(()=>{mounted.current=true;void refreshConfig();const refresh=()=>{if(!lock.current)void refreshConfig();};let disposed=false;let off:(()=>void)|undefined;
  window.addEventListener('focus',refresh);
  if(isTauri())void listen('deskpet-api-config-changed',refresh).then(fn=>{if(disposed)fn();else off=fn;}).catch(()=>{});
  return()=>{disposed=true;mounted.current=false;releaseImages();window.removeEventListener('focus',refresh);off?.();stopWanted.current=true;if(requestRef.current)void invoke('cancel_chat_stream',{requestId:requestRef.current}).catch(()=>{});unlisteners.current.forEach(fn=>fn());};
 },[refreshConfig]);
 // 任务卡事件属于任务生命周期：确认/开始/轮询都发生在发起回合结束之后，
 // 而回合订阅在 finally 里会统一注销，所以这里在组件挂载层长期订阅。
 const taskSoundPhases=useRef(new Map<string,string>());
 useEffect(()=>{
  if(!isTauri())return;
  let disposed=false;let off:(()=>void)|undefined;
  void listen<Partial<AgentTaskCard>>('agent-task',event=>{
   if(disposed)return;
   const payload=event.payload;
   const phase=payload.phase;
   const soundKey=payload.jobPath??payload.proposalId;
   if(soundKey&&phase&&taskSoundPhases.current.get(soundKey)!==phase){
    taskSoundPhases.current.set(soundKey,phase);
    if(taskSoundPhases.current.size>256)taskSoundPhases.current.delete(taskSoundPhases.current.keys().next().value!);
    if(phase==='awaiting_style'||phase==='complete')playSfx('task_complete');
    else if(phase==='failed')playSfx('task_failed');
   }
   setConversations(current=>{
    let changed=false;
    const next=Object.fromEntries(modes.map(mode=>{
     const state=current[mode];
     const messages=state.messages.map(message=>{
      if(!message.agentTasks?.length)return message;
      const updated=applyTaskEvent(message.agentTasks,payload);
      if(updated!==message.agentTasks){changed=true;return {...message,agentTasks:updated};}
      return message;
     });
     return [mode,messages===state.messages?state:{...state,messages}];
    })) as Record<ChatMode,ConversationState>;
    return changed?next:current;
   });
  }).then(fn=>{if(disposed)fn();else off=fn;}).catch(()=>{});
  return()=>{disposed=true;off?.();};
 },[]);
 const addPendingImages=useCallback((images:ImagePayload[])=>updateConversation(chatMode,current=>{try{if(current.pendingAttachments.length+images.length>MAX_TURN_ATTACHMENTS)throw new Error('一次性文件上传太多了哦');const currentImages=readyImages(current.pendingAttachments),files=readyFiles(current.pendingAttachments);validateImages([...currentImages,...images]);validateAttachmentCount([...currentImages,...images],files);const additions:PendingAttachment[]=images.map(image=>({id:attachmentId(),name:image.name??'image',state:'ready',kind:'image',image:storeImage(image)}));return {...current,pendingAttachments:[...current.pendingAttachments,...additions],uploadedFiles:registerResources(current.uploadedFiles,additions)};}catch(e){return {...current,status:String(e)};}}),[chatMode,updateConversation]);
 const addPendingFiles=useCallback((files:ParsedFilePayload[])=>updateConversation(chatMode,current=>{try{if(current.pendingAttachments.length+files.length>MAX_TURN_ATTACHMENTS)throw new Error('一次性文件上传太多了哦');const images=readyImages(current.pendingAttachments),nextFiles=[...readyFiles(current.pendingAttachments),...files];validateParsedFiles(nextFiles);validateAttachmentCount(images,nextFiles);const additions:PendingAttachment[]=files.map(file=>({id:attachmentId(),name:file.name,state:'ready',kind:'file',file}));return {...current,pendingAttachments:[...current.pendingAttachments,...additions],uploadedFiles:registerResources(current.uploadedFiles,additions)};}catch(e){return {...current,status:String(e)};}}),[chatMode,updateConversation]);
 const reservePendingAttachments=useCallback((items:Array<{id:string;name:string}>)=>updateConversation(chatMode,current=>current.pendingAttachments.length+items.length>MAX_TURN_ATTACHMENTS?{...current,status:'一次性文件上传太多了哦'}:{...current,pendingAttachments:[...current.pendingAttachments,...items.map(item=>({...item,state:'parsing' as const}))]}),[chatMode,updateConversation]);
 const resolvePendingImage=useCallback((attachment:string,image:ImagePayload)=>updateConversation(chatMode,current=>{const index=current.pendingAttachments.findIndex(item=>item.id===attachment&&item.state==='parsing');if(index<0)return current;try{const images=readyImages(current.pendingAttachments),files=readyFiles(current.pendingAttachments);validateImages([...images,image]);validateAttachmentCount([...images,image],files);const next=[...current.pendingAttachments];const ready:PendingAttachment={id:attachment,name:image.name??next[index].name,state:'ready',kind:'image',image:storeImage(image)};next[index]=ready;return {...current,pendingAttachments:next,uploadedFiles:registerResources(current.uploadedFiles,[ready])};}catch(e){return {...current,pendingAttachments:current.pendingAttachments.filter(item=>item.id!==attachment),status:String(e)};}}),[chatMode,updateConversation]);
 const resolvePendingFile=useCallback((attachment:string,file:ParsedFilePayload)=>updateConversation(chatMode,current=>{const index=current.pendingAttachments.findIndex(item=>item.id===attachment&&item.state==='parsing');if(index<0)return current;try{const images=readyImages(current.pendingAttachments),files=[...readyFiles(current.pendingAttachments),file];validateParsedFiles(files);validateAttachmentCount(images,files);const next=[...current.pendingAttachments];const ready:PendingAttachment={id:attachment,name:file.name,state:'ready',kind:'file',file};next[index]=ready;return {...current,pendingAttachments:next,uploadedFiles:registerResources(current.uploadedFiles,[ready])};}catch(e){return {...current,pendingAttachments:current.pendingAttachments.filter(item=>item.id!==attachment),status:String(e)};}}),[chatMode,updateConversation]);
 const rejectPendingAttachment=useCallback((attachment:string,error:string)=>updateConversation(chatMode,current=>current.pendingAttachments.some(item=>item.id===attachment)?{...current,pendingAttachments:current.pendingAttachments.filter(item=>item.id!==attachment),status:error}:current),[chatMode,updateConversation]);
 const removePendingAttachment=useCallback((attachment:string)=>updateConversation(chatMode,current=>({...current,pendingAttachments:current.pendingAttachments.filter(item=>item.id!==attachment)})),[chatMode,updateConversation]);
 const setConversationTitle=useCallback((title:string)=>{manualTitles.current.add(sessionRef.current[chatMode]);updateConversation(chatMode,current=>({...current,title:title.trimStart().slice(0,80)}));},[chatMode,updateConversation]);
 const allUploadedFiles=registerResources([],modes.flatMap(mode=>conversations[mode].uploadedFiles));
 const referenceUploadedFile=useCallback((attachment:string)=>{const source=registerResources([],modes.flatMap(mode=>conversationsRef.current[mode].uploadedFiles)).find(item=>item.id===attachment);if(!source||source.state!=='ready')return false;const current=conversationsRef.current[chatMode];if(current.pendingAttachments.some(item=>item.state==='ready'&&sameResource(item,source)))return true;if(current.pendingAttachments.length>=MAX_TURN_ATTACHMENTS){updateConversation(chatMode,value=>({...value,status:'一次性文件上传太多了哦'}));return false;}updateConversation(chatMode,value=>({...value,pendingAttachments:[...value.pendingAttachments,source],uploadedFiles:registerResources(value.uploadedFiles,[source])}));return true;},[chatMode,updateConversation]);
 const deleteUploadedFile=useCallback((attachment:string)=>{const snapshot=conversationsRef.current;const target=registerResources([],modes.flatMap(mode=>snapshot[mode].uploadedFiles)).find(item=>item.id===attachment);if(!target||target.state!=='ready')return;setConversations(current=>Object.fromEntries(modes.map(mode=>{const state=current[mode];return [mode,{...state,uploadedFiles:state.uploadedFiles.filter(item=>!sameResource(item,target)),pendingAttachments:state.pendingAttachments.filter(item=>!sameResource(item,target))}];})) as Record<ChatMode,ConversationState>);if(target.kind==='image'){const stillReferenced=modes.some(mode=>snapshot[mode].messages.some(message=>(message.images??[]).some(item=>item.dataUrl===target.image.dataUrl)));if(!stillReferenced)releaseImageResources([target.image]);}},[]);
 const loadConversation=useCallback(async(document:ImportedConversation)=>{if(lock.current)throw new Error('请先停止当前回复。');const mode=document.mode;const previous=sessionRef.current[mode];const nextSession=id(`${mode}-session`);const messages:DialogueMessage[]=document.messages.map((message,index)=>({...message,id:`loaded-${index}-${crypto.randomUUID()}`,files:message.files??[],sources:message.sources??[]}));const resources:PendingAttachment[]=registerResources([],messages.flatMap(message=>(message.files??[]).map(file=>({id:attachmentId(),name:file.name,state:'ready' as const,kind:'file' as const,file}))));await invoke('restore_chat_history',{sessionId:nextSession,messages:document.messages.filter(message=>message.role==='user'||message.state==='complete').map(({role,content,files})=>({role,content,files:files??[]}))});sessionRef.current[mode]=nextSession;if(isTauri())void invoke('clear_chat_history',{sessionId:previous}).catch(()=>{});setConversations(current=>({...current,[mode]:{...newConversation('',registerResources(current[mode].uploadedFiles,resources)),messages,title:document.title,storage:document.storage}}));setChatModeState(mode);},[]);
 const stopMessage=useCallback(async()=>{
  if(!lock.current)return;stopWanted.current=true;setIsStopping(true);setModeStatus(chatMode,'正在停止…');
  if(requestRef.current)try{await invoke('cancel_chat_stream',{requestId:requestRef.current});}catch(e){setIsStopping(false);setModeStatus(chatMode,`停止失败：${String(e)}，可再次尝试。`);}
 },[chatMode,setModeStatus]);
 const clearConversation=useCallback((options:{clearUploadedFiles?:boolean}={})=>{const clear=options.clearUploadedFiles??true;if(lock.current){resetWanted.current=clear;void stopMessage();}else reset(chatMode,clear);},[chatMode,reset,stopMessage]);

 const run=useCallback(async(options:SendMessageOptions={},retry=false)=>{
  if(lock.current)return;lock.current=true;stopWanted.current=false;resetWanted.current=null;setIsSending(true);setIsStopping(false);
  const targetMode=chatMode;const conversation=conversations[targetMode];
  const setRunMessages=(value:SetStateAction<DialogueMessage[]>)=>updateConversation(targetMode,current=>({...current,messages:typeof value==='function'?value(current.messages):value}));
  const setRunStatus=(status:string)=>setModeStatus(targetMode,status);
  const setRunContextNote=(contextNote:string)=>updateConversation(targetMode,current=>({...current,contextNote}));
  let assistantId:string|null=null;let completed=false;let requestId:string|null=null;let voiceBuffer='';
  const off:Array<()=>void>=[];unlisteners.current=off;
  const subscribe:typeof listen=async(event,handler,options)=>{
   const unsubscribe=await listen(event,handler,options);
   if(!mounted.current){unsubscribe();throw new Error('Dialogue disposed');}
   return unsubscribe;
  };
  try{
   // Refresh immediately before sending: a hidden window may have missed config events.
   const fresh=await invoke<LlmConfigStatus>('llm_config_status');setConfig(fresh);
   if(!fresh.hasApiKey||!fresh.model)throw new Error('请先在设置中配置 API。');
   const effectiveSearchMode=searchOverride.current[targetMode]?searchModes[targetMode]:(fresh.searchMode??'auto');if(!searchOverride.current[targetMode])setSearchModes(current=>({...current,[targetMode]:effectiveSearchMode}));
   if(effectiveSearchMode==='required'&&!fresh.searchAvailable)throw new Error('请先启用可用的搜索服务。');
   let history=conversation.messages;let images=options.images??readyImages(conversation.pendingAttachments);let files=options.files??readyFiles(conversation.pendingAttachments);let text=(options.text??conversation.input).trim();let turnId=id('user');
   if(retry){const index=conversation.messages.map(m=>m.role).lastIndexOf('user');if(index<0)return;const old=conversation.messages[index];history=conversation.messages.slice(0,index);text=old.content;images=old.images??[];files=old.files??[];turnId=old.id;}
   text=text||((images.length||files.length)?options.fallbackText??'请分析这些附件。':'');if(!text)return;
   validateImages(images);validateParsedFiles(files);validateAttachmentCount(images,files);images=images.map(storeImage);
   const user:DialogueMessage={id:turnId,role:'user',state:'complete',content:text,images,files};
   const attachmentChars=files.reduce((sum,file)=>sum+file.name.length+file.content.length+120,0);
   if(text.length+attachmentChars>(fresh.contextChars??12000))throw new Error('附件内容较多，暂时无法一次发送。');
   if(stopWanted.current||!mounted.current)return;
   assistantId=id('assistant');requestId=id('chat');
   const update=(fn:(m:DialogueMessage)=>DialogueMessage)=>{if(mounted.current)setRunMessages(current=>current.map(m=>m.id===assistantId?fn(m):m));};
   // Listeners are created inside the guarded scope; partial setup is always cleaned up.
   off.push(await subscribe<ChatDeltaEvent>('llm-chat-delta',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;voiceBuffer+=event.payload.delta;update(m=>({...m,content:m.content+event.payload.delta}));setRunStatus('正在回复…');}));
   off.push(await subscribe<ChatCompleteEvent>('llm-chat-complete',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;completed=true;requestRef.current=null;const state=event.payload.status==='cancelled'?'cancelled':event.payload.status==='truncated'?'truncated':'complete';update(m=>({...m,state}));setRunStatus(state==='cancelled'?'已停止。':state==='truncated'?'回复达到长度限制，内容可能不完整。':'');}));
   off.push(await subscribe<ChatErrorEvent>('llm-chat-error',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;completed=true;requestRef.current=null;update(m=>({...m,state:'error',error:event.payload.message}));setRunStatus(event.payload.message);}));
   off.push(await subscribe<{requestId:string;phase:string;detail:string}>('llm-chat-phase',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;const p=event.payload;if(p.phase==='history-warning')setRunContextNote(p.detail);if(p.phase==='search-warning')update(m=>({...m,searchWarning:p.detail}));setRunStatus(p.phase==='summarizing'?'正在整理较早的对话…':p.phase==='searching'?`正在搜索：${p.detail}`:p.phase==='reading-project'?`正在读取项目资料：${p.detail}`:p.phase==='search-warning'?`搜索提示：${p.detail}`:p.phase==='answering'?'正在整理回复…':'正在思考…');}));
   off.push(await subscribe<{requestId:string;sources:SearchSource[]}>('llm-chat-sources',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;update(m=>({...m,sources:event.payload.sources}));}));
   off.push(await subscribe<ToolCallEvent>('llm-chat-tool',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;update(m=>({...m,toolCalls:applyToolEvent(m.toolCalls??[],event.payload)}));}));
   off.push(await subscribe<AgentProposalEvent>('agent-proposal',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;update(m=>({...m,agentTasks:applyProposalEvent(m.agentTasks??[],event.payload)}));}));
   off.push(await subscribe<{requestId:string}>('agent-suggest-project',event=>{if(event.payload.requestId!==requestId||completed||!mounted.current)return;update(m=>({...m,suggestsProject:true}));}));
   if(stopWanted.current||!mounted.current)return;
   setRunMessages([...history,user,{id:assistantId,role:'assistant',state:'streaming',content:''}]);
   if(!retry)updateConversation(targetMode,current=>({...current,input:'',pendingAttachments:[],title:current.title||conversationTitle(text,{images:images.length>0,files:files.length>0})}));setRunContextNote('');
   requestRef.current=requestId;setRunStatus('正在思考…');
   const transportImages=await Promise.all(images.map(transportImage));
   if(stopWanted.current||!mounted.current){setRunMessages(current=>current.map(m=>m.id===assistantId?{...m,state:'cancelled'}:m));return;}
   const request:ChatStreamRequest={requestId,messages:[{role:'user',content:text}],sessionId:sessionRef.current[targetMode],turnId,images:transportImages.length?transportImages:undefined,files:files.length?files:undefined,searchMode:effectiveSearchMode,chatMode:targetMode,currentDate:new Date().toISOString().slice(0,10),voiceReply:options.voiceReply||undefined};
   const result=await invoke<string>('chat_stream',{request});
   // The command result is authoritative even if the completion event is delayed.
   if(!completed&&mounted.current){completed=true;const state=result==='cancelled'?'cancelled':result==='truncated'?'truncated':'complete';update(m=>({...m,state}));setRunStatus(state==='cancelled'?'已停止。':state==='truncated'?'回复达到长度限制，内容可能不完整。':'');}
   // 语音结合回答：完成后把口述段合成 wav，data URL 挂进消息（与图片同模式持久化）。
   if(options.voiceReply&&result==='completed'&&mounted.current){
    const parsed=parseSpokenReply(voiceBuffer);
    if(parsed.hasVoice&&parsed.spoken&&assistantId){
     try{
      const reply=await invoke<{dataUrl:string}>('voice_reply_synthesize',{text:parsed.spoken});
      if(mounted.current)update(m=>m.id===assistantId?{...m,voice:{dataUrl:reply.dataUrl,text:parsed.spoken}}:m);
     }catch(e){if(mounted.current)setRunStatus(`语音合成失败：${String(e)}`);}
    }
   }

  }catch(e){if(completed||!mounted.current)return;completed=true;const error=String(e);if(assistantId)setRunMessages(current=>current.map(m=>m.id===assistantId?{...m,state:'error',error}:m));setRunStatus(error);}
  finally{off.forEach(fn=>fn());unlisteners.current=[];requestRef.current=null;lock.current=false;if(!mounted.current)return;setIsSending(false);setIsStopping(false);if(resetWanted.current!==null){const clear=resetWanted.current;resetWanted.current=null;reset(targetMode,clear);}else if(stopWanted.current&&!completed)setRunStatus('已停止。');}
 },[chatMode,conversations,reset,searchModes,setModeStatus,updateConversation]);
 const sendMessage=useCallback((options:SendMessageOptions={})=>run(options),[run]);
 const retryLast=useCallback(()=>run({},true),[run]);
 const setStatus=useCallback((status:string)=>setModeStatus(chatMode,status),[chatMode,setModeStatus]);
 // 跳转项目助手：切模式并把触发跳转的那句话预填进项目输入框（两模式会话独立）。
 const jumpToProject=useCallback((draft:string)=>{if(lock.current)return;setChatModeState('project');updateConversation('project',current=>({...current,input:draft&&!current.input?draft:current.input}));},[updateConversation]);
 const pendingImages=readyImages(active.pendingAttachments),pendingFiles=readyFiles(active.pendingAttachments),isParsingAttachments=active.pendingAttachments.some(item=>item.state==='parsing');
 return {messages:active.messages,input:active.input,pendingAttachments:active.pendingAttachments,pendingImages,pendingFiles,isParsingAttachments,uploadedFileCount:active.uploadedFiles.length,currentUploadedFiles:active.uploadedFiles,allUploadedFiles,conversationTitle:active.title,config,status:active.status,isConfigured,isSending,isStopping,searchMode,setSearchMode,chatMode,setChatMode,contextNote:active.contextNote,setInput,setStatus,setConversationTitle,
  storage:active.storage,sessionId:sessionRef.current[chatMode],addPendingImages,addPendingFiles,reservePendingAttachments,resolvePendingImage,resolvePendingFile,rejectPendingAttachment,removePendingAttachment,referenceUploadedFile,deleteUploadedFile,loadConversation,sendMessage,stopMessage,clearConversation,refreshConfig,retryLast,jumpToProject};
}
