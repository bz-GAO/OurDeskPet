import {useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import './ConfirmDialog.css';

export function ConfirmDialog({title,children,busy=false,confirmLabel='确认',layout='end',onConfirm,onCancel}:{title:string;children?:ReactNode;busy?:boolean;confirmLabel?:string;layout?:'end'|'split';onConfirm:()=>void;onCancel:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{
  const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
  const node=ref.current;node?.showModal();
  return()=>{node?.close();if(previous?.isConnected)previous.focus();};
 },[]);
 return createPortal(<dialog ref={ref} className="rina-confirm-dialog" role="alertdialog" aria-label={title} onCancel={event=>{event.preventDefault();if(!busy)onCancel();}}>
  <h2>{title}</h2>{children&&<div className="rina-confirm-body">{children}</div>}
  <div className="rina-confirm-actions" data-layout={layout}><button type="button" autoFocus disabled={busy} onClick={onCancel}>取消</button><button type="button" disabled={busy} onClick={onConfirm}>{busy?'处理中…':confirmLabel}</button></div>
 </dialog>,document.body);
}

export function useConfirmDialog(){
 const [title,setTitle]=useState<string|null>(null);
 const pending=useRef<((value:boolean)=>void)|null>(null);
 const confirm=useCallback((message:string)=>{
  if(pending.current)return Promise.resolve(false);
  return new Promise<boolean>(resolve=>{pending.current=resolve;setTitle(message);});
 },[]);
 const finish=(value:boolean)=>{const resolve=pending.current;pending.current=null;setTitle(null);resolve?.(value);};
 useEffect(()=>()=>{pending.current?.(false);pending.current=null;},[]);
 return {confirm,dialog:title?<ConfirmDialog title={title} onCancel={()=>finish(false)} onConfirm={()=>finish(true)}/>:null};
}
