import type { ChangeEvent, ClipboardEvent, FormEvent, KeyboardEvent } from "react";
import {ConfirmDialog} from './ConfirmDialog';
import { openPath, openUrl } from "@tauri-apps/plugin-opener";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import {BOARD} from './boardGeometry';
import { Fragment, lazy, Suspense, useEffect, useRef, useState } from "react";
import { describeImagePayload, fileToImagePayload, isSupportedImageFile } from "../llm/imagePayload";
import { parseAttachedFile } from "../llm/fileParser";
import { MAX_TURN_ATTACHMENTS } from "../llm/context";
import type { ChatMode, ImportedConversation } from "../llm/types";
import type { CaptureErrorEvent, CaptureImageEvent } from "../llm/types";
import { useDialogueChat } from "../llm/useDialogueChat";
import {useConversationStorage} from '../llm/useConversationStorage';
import {toolLabel} from '../llm/toolCalls';
import {durationLabel,phaseLabel,progressInfo} from '../llm/agentTasks';
import {parseSpokenReply} from '../voice/voiceReply';
import {VoiceBubble} from '../voice/VoiceBubble';
import {useVoiceInput} from '../voice/useVoiceInput';
import {VoiceDialog} from '../voice/VoiceDialog';

import { PaperBackdrop } from './PaperBackdrop';
import {ChatSidebar} from './ChatSidebar';
import {BillingStatus} from './BillingStatus';
import {ProjectSettingsProposal} from './ProjectSettingsProposal';
import type {SavedConversationRecord} from './ChatSidebar';
import './DialoguePaper.css';
import './ChatExperience.css';

const MessageMarkdown = lazy(() => import("./MessageMarkdown"));
const fileExtension=(name:string)=>name.includes('.')?(name.split('.').pop()??'FILE').slice(0,5).toUpperCase():'FILE';
function friendlyAttachmentError(file:File,error:unknown){
  const name=file.name||'文件',detail=String(error);
  if(/暂不支持|不支持|unsupported/i.test(detail))return `${name} 暂不支持`;
  if(/文件过大|超过|too large/i.test(detail))return `${name} 文件过大`;
  if(/空文件/.test(detail))return `${name} 是空文件`;
  if(/UTF-8|二进制|无法读取|可读取的文本/.test(detail))return `${name} 无法读取`;
  return `${name} 解析失败`;
}

export function DialoguePage() {
  const chat = useDialogueChat();
  const storage=useConversationStorage(chat);
  const threadRef = useRef<HTMLDivElement>(null);
  const followBottom = useRef(true);
  const [awayFromBottom,setAwayFromBottom]=useState(false);
  const [confirmReset,setConfirmReset]=useState(false);
  const [clearUploadedFiles,setClearUploadedFiles]=useState(true);
  const isSaving=storage.saving;
  const [sidebarOpen,setSidebarOpen]=useState(false);
  const [savedConversations,setSavedConversations]=useState<SavedConversationRecord[]>([]);
  function scrollToBottom(){const node=threadRef.current;if(node){node.scrollTop=node.scrollHeight;followBottom.current=true;setAwayFromBottom(false);}}
  function selectChatMode(mode:ChatMode){
    setConfirmReset(false);setCaptureStatus(null);setPreviewAttachmentId(null);setPreviewSource(null);setMessagePreviewImage(null);
    followBottom.current=true;setAwayFromBottom(false);chat.setChatMode(mode);
  }

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewAttachmentId, setPreviewAttachmentId] = useState<string | null>(null);
  const [previewSource, setPreviewSource] = useState<"pending" | "message" | null>(null);
  const [captureStatus, setCaptureStatus] = useState<string | null>(null);
  const [attachmentAlert,setAttachmentAlert]=useState<string | null>(null);
  const attachmentAlertTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const cancelledAttachmentIds=useRef(new Set<string>());
  const [messagePreviewImage, setMessagePreviewImage] = useState<{
    dataUrl: string;
    alt: string;
    description?: string;
  } | null>(null);
  const addPendingImages = chat.addPendingImages;
  const setChatInput = chat.setInput;
  const voice = useVoiceInput();
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [agentGate, setAgentGate] = useState<{cardId: string; gate: 1 | 2} | null>(null);
  const [agentGateBusy, setAgentGateBusy] = useState(false);
  const [projectJump, setProjectJump] = useState<string | null>(null);
  const [agentForm, setAgentForm] = useState({name: '', parent: ''});

  useEffect(() => {
    if (!isTauri()) return;
    let disposed = false;
    let off: (() => void) | undefined;
    void listen<{proposalId: string; url: string}>('agent-proposal', event => {
      if (disposed) return;
      setAgentGateBusy(false);
      setAgentGate({cardId: event.payload.proposalId, gate: 1});
    }).then(fn => {
      if (disposed) fn();
      else off = fn;
    }).catch(() => {});
    return () => {
      disposed = true;
      off?.();
    };
  }, []);

  const agentCard = agentGate
    ? chat.messages.flatMap(message => message.agentTasks ?? []).find(card => card.proposalId === agentGate.cardId) ?? null
    : null;

  async function confirmAgentGate() {
    if (!agentGate || agentGateBusy) return;
    const {cardId, gate} = agentGate;
    setAgentGateBusy(true);
    try {
      if (gate === 1) await invoke('agent_proposal_confirm', {proposalId: cardId});
      else await invoke('agent_task_start', {proposalId: cardId, name: agentForm.name, parent: agentForm.parent});
      setAgentGate(null);
    } catch (error) {
      chat.setStatus(`翻译任务操作失败：${String(error)}`);
    } finally {
      setAgentGateBusy(false);
    }
  }

  function cancelAgentGate() {
    if (!agentGate || agentGateBusy) return;
    const declined = agentGate.gate === 1;
    const cardId = agentGate.cardId;
    setAgentGate(null);
    if (declined) void invoke('agent_proposal_decline', {proposalId: cardId}).catch(() => {});
  }

  // 任务卡角标：打开/聚焦设置窗口并定向切到 Yaki 扩展页。投递交给 Rust
  // emit_to（前端跨窗口广播在部分版本不达），新建窗口时延迟一拍再通知。
  async function openYakiExtension() {
    try {
      const existing = await WebviewWindow.getByLabel('settings');
      if (existing) {
        await invoke('agent_open_yaki');
        return;
      }
      const height = Math.min(808, Math.max(360, window.screen.availHeight - 36));
      const width = Math.min(960, Math.max(420, window.screen.availWidth - 24), height * BOARD.width / BOARD.height);
      const settings = new WebviewWindow('settings', {
        url: '/?view=settings', title: 'RinaDesk 设置', width, height: Math.min(height, width * BOARD.height / BOARD.width),
        minWidth: Math.min(760, width), minHeight: Math.min(640, height), transparent: true, decorations: false, shadow: false,
        resizable: true, center: true,
      });
      settings.once('tauri://created', () => { setTimeout(() => {void invoke('agent_open_yaki').catch(() => {});}, 600); });
      settings.once('tauri://error', error => console.error('Settings window failed', error));
    } catch (error) {
      chat.setStatus(`打开扩展页失败：${String(error)}`);
    }
  }

  async function exportAgentTask(jobPath: string) {
    try {
      await invoke('agent_task_export', {jobPath});
    } catch (error) {
      chat.setStatus(`导出失败：${String(error)}`);
    }
  }

  function openProjectJump() {
    const lastUser = [...chat.messages].reverse().find(message => message.role === 'user');
    setProjectJump(lastUser?.content ?? '');
  }

  // 运行中的任务卡：轮询桥状态，结果经 agent-task 事件合并回消息。
  const runningJobs = [...new Set(chat.messages
    .flatMap(message => message.agentTasks ?? [])
    .filter(card => card.phase === 'running' && card.jobPath)
    .map(card => card.jobPath as string))].sort();
  const runningJobsKey = JSON.stringify(runningJobs);
  useEffect(() => {
    if (!isTauri() || runningJobs.length === 0) return;
    let disposed=false;
    let timer:number|undefined;
    const poll=async()=>{
      await Promise.allSettled(runningJobs.map(jobPath=>invoke('agent_task_status',{jobPath})));
      if(!disposed)timer=window.setTimeout(()=>void poll(),3000);
    };
    timer=window.setTimeout(()=>void poll(),3000);
    return () => {disposed=true;if(timer!==undefined)window.clearTimeout(timer);};
  }, [runningJobsKey]);

  function openVoiceDialog() {
    if (voice.status && !voice.status.supported) {
      showAttachmentAlert(voice.status.reason || '当前 API 方案不支持语音输入。');
      return;
    }
    setVoiceOpen(true);
  }

  function sendVoiceText(text: string, combined: boolean) {
    setVoiceOpen(false);
    voice.reset();
    if (!text) return;
    followBottom.current = true;
    void chat.sendMessage({ text, voiceReply: combined });
    textareaRef.current?.focus();
  }

  function closeVoiceDialog() {
    setVoiceOpen(false);
    void voice.cancel().finally(voice.reset);
  }

  const pendingPreviewAttachment=previewSource==='pending'&&previewAttachmentId?chat.pendingAttachments.find(item=>item.id===previewAttachmentId):null;
  const pendingPreviewImage=pendingPreviewAttachment?.state==='ready'&&pendingPreviewAttachment.kind==='image'?pendingPreviewAttachment.image:null;
  const activePreviewImage =
    pendingPreviewImage
      ? {
          dataUrl: pendingPreviewImage.dataUrl,
          alt: pendingPreviewImage.name ?? "Pending image preview",
          description: describeImagePayload(pendingPreviewImage),
        }
      : messagePreviewImage;

  function showAttachmentAlert(message:string){
    setAttachmentAlert(message);
    if(attachmentAlertTimer.current)clearTimeout(attachmentAlertTimer.current);
    attachmentAlertTimer.current=setTimeout(()=>{setAttachmentAlert(null);attachmentAlertTimer.current=null;},3000);
  }

  function removePendingAttachment(id:string,parsing:boolean){
    if(parsing)cancelledAttachmentIds.current.add(id);
    if(previewAttachmentId===id){setPreviewSource(null);setPreviewAttachmentId(null);}
    chat.removePendingAttachment(id);
  }

  function cancelAllParsingAttachments(){
    for(const item of chat.pendingAttachments)if(item.state==='parsing')cancelledAttachmentIds.current.add(item.id);
  }

  useEffect(()=>()=>{if(attachmentAlertTimer.current)clearTimeout(attachmentAlertTimer.current);},[]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) {
      return;
    }

    if(followBottom.current)thread.scrollTop = thread.scrollHeight;
  }, [chat.messages]);

  useEffect(() => {
    resizeInput();
  }, [chat.input]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    let width = -1;
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth === width) return;
      width = textarea.clientWidth;
      resizeInput();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let isMounted = true;
    let unlistenReady: (() => void) | null = null;
    let unlistenError: (() => void) | null = null;

    async function listenForCapture() {
      unlistenReady = await listen<CaptureImageEvent>("capture-image-ready", (event) => {
        if (!isMounted) {
          return;
        }

        addPendingImages([event.payload.image]);
        setChatInput((currentInput) => currentInput || event.payload.prompt || "请解释这张截图中的内容。");
        textareaRef.current?.focus();
      });

      unlistenError = await listen<CaptureErrorEvent>("capture-image-error", (event) => {
        if (!isMounted) {
          return;
        }

        console.warn(event.payload.message);
      });
    }

    void listenForCapture();

    return () => {
      isMounted = false;
      unlistenReady?.();
      unlistenError?.();
    };
  }, [addPendingImages, setChatInput]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (chat.isSending) {
      void chat.stopMessage();
      return;
    }
    if(chat.isParsingAttachments)return;

    followBottom.current=true;
    void chat.sendMessage();
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (chat.isSending||chat.isParsingAttachments) {
        return;
      }
      followBottom.current=true;
    void chat.sendMessage();
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLTextAreaElement>) {
    chat.setInput(event.target.value);
    resizeInput();
  }

  async function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    await attachFiles(files);
    event.target.value = "";
  }

  async function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const imageFiles = Array.from(event.clipboardData.files).filter(isSupportedImageFile);
    if (imageFiles.length === 0) {
      return;
    }

    event.preventDefault();
    await attachFiles(imageFiles);
  }

  async function attachFiles(files:File[]){
    if(files.length===0)return;
    if(chat.pendingAttachments.length+files.length>MAX_TURN_ATTACHMENTS){showAttachmentAlert('一次性文件上传太多了哦');return;}
    const jobs: Array<{id:string;name:string;file:File;sourcePath?:string}>=[];
    for(const file of files){
      const sourcePath=(file as File&{path?:string}).path;
      // Re-read explicit uploads: an unchanged path/name can contain new data.
      jobs.push({id:`attachment-${crypto.randomUUID()}`,name:file.name||'未命名文件',file,sourcePath});
    }
    chat.reservePendingAttachments(jobs.map(({id,name})=>({id,name})));
    await Promise.all(jobs.map(async({id,file,sourcePath})=>{
      try{
        if(isSupportedImageFile(file)){const parsed={...await fileToImagePayload(file),sourcePath};if(!cancelledAttachmentIds.current.has(id))chat.resolvePendingImage(id,parsed);}
        else {const parsed={...await parseAttachedFile(file),sourcePath};if(!cancelledAttachmentIds.current.has(id))chat.resolvePendingFile(id,parsed);}
      }catch(error){if(!cancelledAttachmentIds.current.has(id)){const message=friendlyAttachmentError(file,error);chat.rejectPendingAttachment(id,message);showAttachmentAlert(message);}}
      finally{cancelledAttachmentIds.current.delete(id);}
    }));
  }

  async function importConversation(){
    if(chat.isSending||isSaving)return;
    try{
      await storage.flush();
      const document=await invoke<ImportedConversation|null>('chat_import_choose');
      if(!document)return;
      setSavedConversations(current=>current.some(item=>item.path.toLocaleLowerCase()===document.path.toLocaleLowerCase())?current:[{id:crypto.randomUUID(),path:document.path,title:document.title,mode:document.mode},...current]);
      await chat.loadConversation(document);followBottom.current=true;setConfirmReset(false);chat.setStatus('');
    }catch(error){chat.setStatus(String(error).includes('文件不存在')?'文件不存在':`载入失败：${String(error)}`);}
  }

  async function loadSavedConversation(record:SavedConversationRecord){
    if(chat.isSending||isSaving)return;
    try{await storage.flush();const managed=storage.records.some(item=>item.id===record.id);const document=await invoke<ImportedConversation>(managed?'chat_storage_read':'chat_import_read',managed?{id:record.id}:{path:record.path});await chat.loadConversation(document);followBottom.current=true;setConfirmReset(false);chat.setStatus('');}
    catch(error){chat.setStatus(String(error).includes('文件不存在')?'文件不存在':`载入失败：${String(error)}`);}
  }

  function chooseFile() {
    fileInputRef.current?.click();
  }

  function resizeInput() {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.overflowY = "hidden";
    textarea.style.height = "0px";
    const style = getComputedStyle(textarea);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    const maximum = parseFloat(style.maxHeight) || 148;
    const needed = textarea.scrollHeight + border;
    textarea.style.height = `${Math.min(needed, maximum)}px`;
    textarea.style.overflowY = needed > maximum + 1 ? "auto" : "hidden";
  }

  const proposalTurns=new Map<string,string>();let latestUser='';
  for(const message of chat.messages){if(message.role==='user')latestUser=message.id;else if(latestUser)proposalTurns.set(message.id,latestUser);}

  return (
    <main className="dialogue-page" data-dialogue-theme="paper">
      <div className="chat-toolbar">
      <header className="dialogue-header">
        <div className="chat-title-area">
          <button className="chat-sidebar-toggle" type="button" aria-label={sidebarOpen?'收起侧边栏':'展开侧边栏'} title={sidebarOpen?'收起侧边栏':'展开侧边栏'} aria-expanded={sidebarOpen} onClick={()=>setSidebarOpen(open=>!open)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v14H4zM9 5v14M6.25 8h.5M6.25 11h.5M6.25 14h.5"/></svg></button>
          <div>
          <h1>Chat</h1>
          {(captureStatus || chat.status) && <p role="status">{captureStatus ?? chat.status}</p>}
          </div>
        </div>
        <div className="chat-header-actions">
          <BillingStatus compact/>
          <select className="chat-save-mode" aria-label="对话保存方式" value={storage.settings?.enabled?'auto':'off'} disabled={!storage.settings||storage.busy} onChange={event=>void storage.change('chat_storage_enable',{enabled:event.target.value==='auto'})}><option value="auto">自动保存</option><option value="off">不保存</option></select>
          <button className="dialogue-clear-button" type="button" disabled={isSaving} onClick={()=>{setClearUploadedFiles(true);setConfirmReset(true);}}>新对话</button>
        </div>
      </header>

      {confirmReset&&<ConfirmDialog title="新对话确认" confirmLabel="开始新对话" onCancel={()=>setConfirmReset(false)} onConfirm={async()=>{try{await storage.flush();cancelAllParsingAttachments();chat.clearConversation({clearUploadedFiles});setConfirmReset(false);followBottom.current=true;}catch(error){chat.setStatus(String(error));}}}><p>清空当前页和草稿{chat.isSending?'，并停止当前回复':''}。</p><label><input type="checkbox" checked={clearUploadedFiles} onChange={event=>setClearUploadedFiles(event.target.checked)}/>清空上传的文件</label></ConfirmDialog>}
      {voiceOpen&&<VoiceDialog voice={voice} onSend={sendVoiceText} onClose={closeVoiceDialog}/>}
      {projectJump!==null&&<ConfirmDialog
        title="跳转到项目助手模式？"
        confirmLabel="跳转"
        layout="split"
        onCancel={()=>setProjectJump(null)}
        onConfirm={()=>{chat.jumpToProject(projectJump);setProjectJump(null);}}
      >
        <p>项目助手模式可以读取项目源码、提案 Desk 设置并处理工程操作。将把你最后一条消息带到新模式的输入框。</p>
      </ConfirmDialog>}
      {agentGate&&agentCard?<ConfirmDialog
        title={agentGate.gate===1?'创建翻译任务':'开始翻译'}
        confirmLabel={agentGate.gate===1?'获取视频信息':'开始'}
        busy={agentGateBusy}
        onCancel={cancelAgentGate}
        onConfirm={()=>void confirmAgentGate()}
      >
        {agentGate.gate===1?(
          <p>将读取视频信息并生成翻译任务卡片（此步不下载、不产生费用）：<br/><code>{agentCard.url}</code></p>
        ):(
          <div className="agent-task-form">
            <p><strong>{agentCard.title||agentCard.url}</strong>{agentCard.duration?`（${durationLabel(agentCard.duration)}）`:''}</p>
            <p>即将开始：下载 → 转写 → 翻译。费用：{agentCard.estimate||'按时长计费，以实际用量为准'}。</p>
            <label>项目名称<input value={agentForm.name} maxLength={100} aria-label="项目名称" onChange={event=>setAgentForm(form=>({...form,name:event.target.value}))}/></label>
            <label>保存位置<input value={agentForm.parent} aria-label="保存位置" onChange={event=>setAgentForm(form=>({...form,parent:event.target.value}))}/></label>
          </div>
        )}
      </ConfirmDialog>:null}
      {storage.error&&<p className="settings-error" role="status">{storage.error}<button type="button" disabled={isSaving} onClick={()=>void storage.flush().catch(()=>{})}>重试保存</button></p>}
      {attachmentAlert&&<div className="chat-attachment-alert" role="alert">{attachmentAlert}</div>}
      <div className="chat-options">
        <div className="chat-mode-switch" role="group" aria-label="Chat 模式">
          <button type="button" aria-pressed={chat.chatMode==='chat'} data-active={chat.chatMode==='chat'} disabled={chat.isSending||chat.isParsingAttachments||isSaving} onClick={()=>selectChatMode('chat')}>对话</button>
          <button type="button" aria-pressed={chat.chatMode==='project'} data-active={chat.chatMode==='project'} disabled={chat.isSending||chat.isParsingAttachments||isSaving} onClick={()=>selectChatMode('project')}>项目助手</button>
        </div>
        <label>联网 <select aria-label="联网模式" value={chat.searchMode} disabled={chat.isSending} onChange={e=>chat.setSearchMode(e.target.value as 'auto'|'off'|'required')}><option value="auto">自动</option><option value="off">关闭</option><option value="required">必须搜索</option></select></label>
      </div>
      {chat.contextNote&&<p className="chat-context-note">{chat.contextNote}</p>}
      </div>
      <div className="dialogue-workspace" data-sidebar-open={sidebarOpen}>
      {sidebarOpen?<ChatSidebar currentFiles={chat.currentUploadedFiles} libraryFiles={chat.allUploadedFiles} currentTitle={chat.conversationTitle} currentMode={chat.chatMode} currentStorageId={storage.currentId} savedConversations={[...storage.records,...savedConversations]} busy={chat.isSending||chat.isParsingAttachments||isSaving} onReferenceFile={id=>{if(!chat.referenceUploadedFile(id))showAttachmentAlert('一次性文件上传太多了哦');}} onDeleteFile={chat.deleteUploadedFile} onRenameCurrent={chat.setConversationTitle} onRenameSaved={(id,title)=>{const record=storage.records.find(item=>item.id===id);if(record)void storage.rename(record,title).then(updated=>{if(updated&&storage.currentId===id)chat.setConversationTitle(title);});else setSavedConversations(current=>current.map(record=>record.id===id?{...record,title}:record));}} onLoadConversation={record=>void loadSavedConversation(record)} onRemoveConversation={id=>{const managed=storage.records.some(item=>item.id===id);if(managed&&storage.currentId===id){chat.setStatus('当前打开的对话不能删除，请先切换到其他对话。');return;}const record=[...storage.records,...savedConversations].find(item=>item.id===id);void invoke(managed?'chat_storage_delete':'chat_storage_delete_file',managed?{id}:{path:record?.path??''}).then(()=>{if(managed)storage.removeRecord(id);else setSavedConversations(current=>current.filter(item=>item.id!==id));}).catch(error=>chat.setStatus(`删除失败：${String(error)}`));}} onImportConversation={()=>void importConversation()} onOpenConversationDirectory={()=>void invoke<string>('chat_storage_prepare_directory').then(path=>openPath(path)).catch(error=>chat.setStatus(`无法打开对话目录：${String(error)}`))}/>:null}
      <section className="dialogue-shell" data-chat-mode={chat.chatMode} aria-label={chat.chatMode==='project'?'项目助手页面':'普通对话页面'}>
        <section className="dialogue-main"><div className="dialogue-paper-thread-area"><PaperBackdrop />
          <div className="dialogue-thread" ref={threadRef} onScroll={e=>{const node=e.currentTarget;const near=node.scrollHeight-node.scrollTop-node.clientHeight<64;followBottom.current=near;setAwayFromBottom(!near);}}>
            {chat.messages.map((message) => (
              <Fragment key={message.id}>
              <article
                className="dialogue-message"
                data-role={message.role}
                data-state={message.state}
              >
                <span>{message.role === "user" ? "You" : "Rina"}</span>
                {message.voice&&<VoiceBubble voice={message.voice}/>}
                {message.suggestsProject&&message.role==='assistant'&&<div className="project-mode-suggest"><span>这个请求更适合项目助手模式处理</span><button type="button" disabled={chat.isSending} onClick={openProjectJump}>跳转</button></div>}
                {message.images && message.images.length > 0 ? (
                  <div className="dialogue-message-images" aria-label="Sent image attachments">
                    {message.images.map((image, index) => (
                      <button
                        className="image-preview-button"
                        key={`${message.id}-${image.dataUrl.slice(0, 36)}-${index}`}
                        type="button"
                        onClick={() => {
                          setPreviewSource("message");
                          setPreviewAttachmentId(null);
                          setMessagePreviewImage({
                            dataUrl: image.dataUrl,
                            alt: image.name ?? `Attachment ${index + 1}`,
                            description: describeImagePayload(image),
                          });
                        }}
                      >
                        <img
                          alt={image.name ?? `Attachment ${index + 1}`}
                          src={image.dataUrl} loading="lazy" decoding="async"
                        />
                      </button>
                    ))}
                  </div>
                ) : null}
                {message.images?.length ? <button className="chat-reuse-image" type="button" onClick={()=>chat.addPendingImages(message.images!)}>再次附加这些图片</button>:null}
                {message.files?.length?<div className="dialogue-message-files" aria-label="附加文件">{message.files.map((file,index)=><span key={`${message.id}-${file.name}-${index}`}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3.75h7l3 3v13.5H7zM14 3.75v3h3"/></svg>{file.name}</span>)}</div>:null}
                <Suspense fallback={<p>{message.content}</p>}><MessageMarkdown content={(message.voice?parseSpokenReply(message.content).rest:message.content) || (message.state === "streaming" ? "..." : "")} /></Suspense>
                {message.error&&<p className="chat-message-note" role="status">{message.error}</p>}
                {message.toolCalls?.length?<div className="chat-tool-calls" aria-label="使用的工具">{message.toolCalls.map((call,index)=><span key={`${message.id}-tool-${index}`} className="chat-tool-chip" data-state={call.state} title={call.detail}>{toolLabel(call.name)}{call.state==='done'?' ✓':call.state==='error'?' ✕':' …'}</span>)}</div>:null}
                {message.agentTasks?.length?<div className="agent-task-cards" aria-label="agent 任务">{message.agentTasks.map(card=><div key={`${message.id}-task-${card.proposalId}`} className="agent-task-card" data-phase={card.phase}>
                  <button type="button" className="agent-task-jump" title="在扩展页中查看" aria-label="转到 Yaki 扩展页" onClick={()=>void openYakiExtension()}>转到 Yaki ↗</button>
                  <div className="agent-task-title">{card.title||card.url}</div>
                  {(card.phase==='ready'||card.phase==='running')&&card.thumbnail?<div className="agent-task-preview"><div className="agent-task-cover"><img src={card.thumbnail} alt="视频封面" loading="lazy"/></div><div className="agent-task-meta"><span>时长 {durationLabel(card.duration)||'—'}</span><span>画质 {card.qualityLabel||'自动'}</span></div></div>:null}
                  <div className="agent-task-status" data-phase={card.phase}>{phaseLabel(card)}</div>
                  {(card.phase==='ready'||(card.phase==='running'&&card.stage!=='export_and_mux'))&&card.estimate?<div className="agent-task-estimate">{card.estimate}</div>:null}
                  {card.phase==='running'&&progressInfo(card)?<div className="agent-task-progress"><span>{progressInfo(card)!.label}</span><div className="agent-task-bar" data-indeterminate={progressInfo(card)!.percent===null||undefined}><div className="agent-task-bar-fill" style={progressInfo(card)!.percent===null?undefined:{width:`${progressInfo(card)!.percent}%`}}/></div></div>:null}
                  {card.phase==='ready'?<button type="button" className="agent-task-start" onClick={()=>{setAgentGateBusy(false);setAgentForm({name: card.suggestedName||'', parent: card.defaultParent||''});setAgentGate({cardId:card.proposalId,gate:2});}}>开始翻译</button>:null}
                  {card.phase==='awaiting_style'?<button type="button" className="agent-task-export" onClick={()=>void exportAgentTask(card.jobPath??'')}>一键导出</button>:null}
                </div>)}</div>:null}
                {message.searchWarning&&<p className="chat-message-note">搜索未能完成查证：{message.searchWarning}</p>}
                {message.state==='cancelled'&&<p className="chat-message-note">已停止 · 部分回复不作为完整回答发送到下一轮</p>}
                {message.state==='truncated'&&<p className="chat-message-note">达到长度限制 · 回复未完整</p>}
                {message.sources?.length ? <details className="chat-sources"><summary>搜索来源（{message.sources.length}）</summary><ul>{message.sources.map(source=><li key={source.url}><a href={source.url} onClick={event=>{if(isTauri()){event.preventDefault();void openUrl(source.url).catch(error=>chat.setStatus(`打开来源失败：${String(error)}`));}}} target="_blank" rel="noreferrer">{source.title}</a></li>)}</ul></details>:null}
                {message.role==='assistant'&&message.id===chat.messages[chat.messages.length-1]?.id&& !chat.isSending&&<button className="chat-retry" onClick={()=>{followBottom.current=true;void chat.retryLast();}}>{message.state==='complete'?'重新生成':'重试上一条'}</button>}
              </article>
              {message.role==='assistant'&&proposalTurns.has(message.id)&&<div className="project-settings-anchor" data-project-settings-turn={proposalTurns.get(message.id)}/>}
              </Fragment>
            ))}
            <ProjectSettingsProposal key={chat.sessionId} session={chat.sessionId} busy={chat.isSending} visible={chat.chatMode==='project'}/>
          </div>

          {awayFromBottom&&<button className="chat-jump-bottom" onClick={scrollToBottom}>回到最新回复 ↓</button>}
          </div><form className="dialogue-input-row" onSubmit={handleSubmit}>
            <div className="dialogue-compose-stack">
              <div className="dialogue-compose-top">
                <button
                  className="dialogue-tool-button"
                  type="button"
                  aria-label="附加文件"
                  title="附加文件"
                  onClick={chooseFile}
                >
                  <svg className="file-tool-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.75 6.75h6l1.8 2h8.7v10.5H3.75zM3.75 6.75v-2h6l1.5 2"/></svg>
                </button>
                {chat.pendingAttachments.length>0?<div className="pending-attachment-strip" aria-label="待发送附件" onWheel={event=>{const node=event.currentTarget;if(node.scrollWidth>node.clientWidth&&Math.abs(event.deltaY)>Math.abs(event.deltaX)){node.scrollLeft+=event.deltaY;event.preventDefault();}}}>{chat.pendingAttachments.map(item=>{
                  if(item.state==='parsing')return <div className="pending-attachment-card is-parsing" key={item.id}><span className="attachment-spinner" aria-hidden="true"/><span title={item.name}>{item.name}</span><button type="button" aria-label={`取消解析 ${item.name}`} onClick={()=>removePendingAttachment(item.id,true)}>×</button></div>;
                  if(item.kind==='image')return <figure className="pending-attachment-card is-image" key={item.id}><button className="pending-attachment-preview" type="button" aria-label={`预览 ${item.name}`} onClick={()=>{setPreviewSource('pending');setPreviewAttachmentId(item.id);setMessagePreviewImage(null);}}><img alt={item.name} src={item.image.dataUrl} loading="lazy" decoding="async"/><span title={item.name}>{item.name}</span></button><button className="pending-attachment-remove" type="button" aria-label={`移除 ${item.name}`} onClick={()=>removePendingAttachment(item.id,false)}>×</button></figure>;
                  return <div className="pending-attachment-card is-file" key={item.id}><span className="pending-file-badge" aria-hidden="true">{fileExtension(item.name)}</span><span title={item.name}>{item.name}</span><button type="button" aria-label={`移除 ${item.name}`} onClick={()=>removePendingAttachment(item.id,false)}>×</button></div>;
                })}</div>:null}
              </div>
              <div className="dialogue-input-line">
                <button
                  className="dialogue-voice-button"
                  type="button"
                  aria-label="语音输入"
                  title={voice.status && !voice.status.supported ? (voice.status.reason || '当前 API 方案不支持语音输入') : '语音输入'}
                  onClick={openVoiceDialog}
                  disabled={!chat.isConfigured || chat.isSending}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5a2.8 2.8 0 0 1 2.8 2.8v5.4a2.8 2.8 0 0 1-5.6 0V6.3A2.8 2.8 0 0 1 12 3.5z"/><path d="M5.8 11.3a6.2 6.2 0 0 0 12.4 0M12 17.5v3"/></svg>
                </button>
                <textarea
                  ref={textareaRef}
                  placeholder={chat.isConfigured ? (chat.chatMode==='project'?"询问功能、项目结构或使用方法…":"Ask Rina...") : "请先在设置中配置 API。"}
                  aria-label="Dialogue input"
                  value={chat.input}
                  onChange={handleInputChange}
                  onKeyDown={handleInputKeyDown}
                  onPaste={handlePaste}
                  disabled={!chat.isConfigured}
                  rows={1}
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  hidden
                  onChange={handleFileInputChange}
                />
                <button
                  className="dialogue-send-button"
                  type={chat.isSending ? "button" : "submit"}
                  onClick={chat.isSending ? () => void chat.stopMessage() : undefined}
                  data-mode={chat.isSending ? "stop" : "send"}
                  disabled={
                    (!chat.isSending && !chat.input.trim() && chat.pendingImages.length === 0 && chat.pendingFiles.length === 0) ||
                    chat.isStopping ||
                    chat.isParsingAttachments ||
                    !chat.isConfigured
                  }
                >
                  {chat.isSending ? "Stop" : "Send"}
                </button>
              </div>
            </div>
          </form>
        </section>
      </section>
      </div>

      {activePreviewImage ? (
        <section
          className="image-preview-modal"
          aria-label="Image preview"
          role="dialog"
          onClick={() => {
            setPreviewSource(null);
            setPreviewAttachmentId(null);
            setMessagePreviewImage(null);
          }}
        >
          <div className="image-preview-surface" onClick={(event) => event.stopPropagation()}>
            <button
              className="image-preview-close"
              type="button"
              aria-label="Close image preview"
              onClick={() => {
                setPreviewSource(null);
                setPreviewAttachmentId(null);
                setMessagePreviewImage(null);
              }}
            >
              x
            </button>
            <img alt={activePreviewImage.alt} src={activePreviewImage.dataUrl} />
            {activePreviewImage.description ? <p>{activePreviewImage.description}</p> : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}


