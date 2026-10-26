import {useState} from 'react';
import {ConfirmDialog} from './ConfirmDialog';
import type {ChatMode,PendingAttachment} from '../llm/types';

export interface SavedConversationRecord {id:string;path:string;title:string;mode:ChatMode;}

type Props={
  currentFiles:PendingAttachment[];
  libraryFiles:PendingAttachment[];
  currentTitle:string;
  currentMode:ChatMode;
  currentStorageId?:string;
  savedConversations:SavedConversationRecord[];
  busy:boolean;
  onReferenceFile:(id:string)=>void;
  onDeleteFile:(id:string)=>void;
  onRenameCurrent:(title:string)=>void;
  onRenameSaved:(id:string,title:string)=>void;
  onLoadConversation:(record:SavedConversationRecord)=>void;
  onRemoveConversation:(id:string)=>void;
  onImportConversation:()=>void;
  onOpenConversationDirectory:()=>void;
};

const extension=(name:string)=>name.includes('.')?(name.split('.').pop()??'FILE').slice(0,5).toUpperCase():'FILE';
const readyOnly=(items:PendingAttachment[])=>items.filter((item):item is Extract<PendingAttachment,{state:'ready'}>=>item.state==='ready');

export function ChatSidebar(props:Props){
  const [fileScope,setFileScope]=useState<'current'|'library'>('current');
  const [confirm,setConfirm]=useState<{kind:'file';id:string;name:string}|{kind:'conversation';record:SavedConversationRecord}|null>(null);
  const [renaming,setRenaming]=useState<string|null>(null);
  const [renameDraft,setRenameDraft]=useState('');
  function finishRename(id:string){const title=renameDraft.trim();if(title)props.onRenameSaved(id,title);setRenaming(null);}
  const files=readyOnly(fileScope==='current'?props.currentFiles:props.libraryFiles);
  const currentIsListed=Boolean(props.currentStorageId&&props.savedConversations.some(record=>record.id===props.currentStorageId));
  return <aside className="chat-sidebar" aria-label="文件与对话侧边栏">
    <section className="chat-sidebar-section chat-sidebar-files">
      <div className="chat-sidebar-heading"><h2>文件</h2><div className="chat-sidebar-tabs" role="tablist" aria-label="文件范围"><button data-active={fileScope==='current'} onClick={()=>setFileScope('current')}>当前对话</button><button data-active={fileScope==='library'} onClick={()=>setFileScope('library')}>资料库</button></div></div>
      <div className="chat-sidebar-list">
        {files.length===0?<p className="chat-sidebar-empty">暂无文件</p>:files.map(item=><div className="chat-resource-row" key={item.id}>
          <span className="chat-resource-badge">{extension(item.name)}</span><span className="chat-resource-name" title={item.name}>{item.name}</span>
          <button className="chat-resource-reference" type="button" disabled={props.busy} onClick={()=>props.onReferenceFile(item.id)}>引用</button>
          <button className="chat-sidebar-icon-button" type="button" aria-label={`删除 ${item.name}`} title="删除" disabled={props.busy} onClick={()=>setConfirm({kind:'file',id:item.id,name:item.name})}>×</button>
        </div>)}
      </div>
    </section>
    <section className="chat-sidebar-section chat-sidebar-conversations">
      <div className="chat-sidebar-heading"><h2>对话</h2><div className="chat-sidebar-heading-actions"><button className="chat-folder-button" type="button" aria-label="打开对话目录" title="打开对话目录" disabled={props.busy} onClick={props.onOpenConversationDirectory}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6l2 2h9v9.5a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18zM3.5 9h17"/></svg></button><button className="chat-import-button" type="button" disabled={props.busy} onClick={props.onImportConversation}>载入 JSON</button></div></div>
      <div className="chat-sidebar-list">
        {!currentIsListed?<div className="chat-conversation-row chat-current-conversation" data-active>
          <span className="chat-mode-badge" data-mode={props.currentMode}>{props.currentMode==='project'?'项目助手':'对话'}</span>
          <input aria-label="当前对话标题" value={props.currentTitle} placeholder="新对话" maxLength={80} onChange={event=>props.onRenameCurrent(event.target.value)}/>
        </div>:null}
        {props.savedConversations.length===0&&!currentIsListed?<p className="chat-sidebar-empty">暂无已保存对话</p>:props.savedConversations.map(record=>{const active=record.id===props.currentStorageId;return <div className="chat-conversation-row" key={record.id} data-active={active||undefined}>
          {renaming===record.id?<><span className="chat-mode-badge" data-mode={record.mode}>{record.mode==='project'?'项目助手':'对话'}</span><input className="chat-conversation-title-input" autoFocus value={renameDraft} maxLength={80} aria-label="重命名对话" onChange={event=>setRenameDraft(event.target.value)} onBlur={()=>finishRename(record.id)} onKeyDown={event=>{if(event.key==='Enter')finishRename(record.id);if(event.key==='Escape')setRenaming(null);}}/></>:<button className="chat-conversation-select" type="button" disabled={props.busy} aria-current={active?'page':undefined} onClick={()=>{if(!active)props.onLoadConversation(record);}}><span className="chat-mode-badge" data-mode={record.mode}>{record.mode==='project'?'项目助手':'对话'}</span><span>{record.title}</span></button>}
          <button className="chat-conversation-rename" type="button" aria-label={`重命名 ${record.title}`} title="重命名" disabled={props.busy||renaming===record.id} onClick={()=>{setRenameDraft(record.title);setRenaming(record.id);}}>✎</button>
          <button className="chat-sidebar-icon-button" type="button" aria-label={`移除 ${record.title}`} title="移除" disabled={props.busy} onClick={()=>setConfirm({kind:'conversation',record})}>×</button>
        </div>})}
      </div>
    </section>
    {confirm?<ConfirmDialog title={confirm.kind==='file'?'删除文件？':'永久删除对话？'} busy={props.busy} layout={confirm.kind==='conversation'?'split':'end'} confirmLabel={confirm.kind==='file'?'删除':'永久删除'} onCancel={()=>setConfirm(null)} onConfirm={()=>{if(confirm.kind==='file')props.onDeleteFile(confirm.id);else props.onRemoveConversation(confirm.record.id);setConfirm(null);}}>
      <p>{confirm.kind==='file'?`从资料库删除“${confirm.name}”？`:`永久删除“${confirm.record.title}”？对话文件将被移除，此操作不可撤销。`}</p>
    </ConfirmDialog>:null}
  </aside>;
}
