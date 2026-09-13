import {usePetHitRegion} from '../pet/usePetHitRegion';
import {useEffect, useRef, useState, type PointerEvent} from 'react';
import type {usePetController} from '../pet/usePetController';
import './PetBoard.css';

interface PetViewProps {
  dragging?: boolean;
  displayImage?: string;
  notificationPhase?: 'idle' | 'notifying' | 'unread';
  unreadCount?: number;
  onNoticeDismiss?: () => void;
  onInteractionChange?: (active:boolean) => void;
  controller: ReturnType<typeof usePetController>;
  onStartDrag: () => void;
  onMinimize: () => void;
  onClose: () => void;
  onOpenDialogue: () => void;
  onOpenSettings: () => void;
}

type Action = 'chat' | 'minimize' | 'close';
function ActionIcon({action}:{action:Action}) {
  return <svg viewBox="0 0 40 40" aria-hidden="true">{action==='chat'?<><path d="M7 10h26v18H18l-8 6v-6H7Z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round"/><circle cx="14" cy="19" r="1.5"/><circle cx="20" cy="19" r="1.5"/><circle cx="26" cy="19" r="1.5"/></>:action==='minimize'?<path d="M9 23h22" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>:<path d="m11 11 18 18m0-18L11 29" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"/>}</svg>;
}

export function PetView({controller,onStartDrag,onMinimize,onClose,onOpenDialogue,onOpenSettings,notificationPhase='idle',unreadCount=0,onNoticeDismiss,onInteractionChange,dragging=false,displayImage}:PetViewProps) {
  const [open,setOpen]=useState(false);
  const [hovered,setHovered]=useState<Action|null>(null);
  const [focused,setFocused]=useState<Action|null>(null);
  const [settingsFocused,setSettingsFocused]=useState(false);
  const [inside,setInside]=useState(false);
  const cooldown=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const active=hovered??focused;
  const notifying=notificationPhase==='notifying';
  const sleeping=controller.state==='sleep';
  const visible=!sleeping && !dragging && (open || notifying);
  usePetHitRegion(visible);
  useEffect(()=>{if(sleeping)setOpen(false);},[sleeping]);
  useEffect(()=>{onInteractionChange?.(inside || Boolean(focused));},[inside,focused,onInteractionChange]);
  useEffect(()=>{
    if(!open || inside || focused || settingsFocused)return;
    const timer=setTimeout(()=>setOpen(false),10000);
    return()=>clearTimeout(timer);
  },[open,inside,focused,settingsFocused]);
  useEffect(()=>{
    if(!visible){clearTimeout(cooldown.current);setHovered(null);setFocused(null);setSettingsFocused(false);setInside(false);}
  },[visible]);
  useEffect(()=>{
    const blur=()=>{setFocused(null);setSettingsFocused(false);setInside(false);setHovered(null);};
    window.addEventListener('blur',blur);
    return()=>{window.removeEventListener('blur',blur);clearTimeout(cooldown.current);};
  },[]);
  function enter(action:Action){clearTimeout(cooldown.current);setHovered(action);}
  function leave(){clearTimeout(cooldown.current);cooldown.current=setTimeout(()=>setHovered(null),250);}
  const gesture=useRef<{x:number;y:number;dragged:boolean}|null>(null);
  function pointerDown(event:PointerEvent<HTMLButtonElement>) {
    if(event.button===0) gesture.current={x:event.clientX,y:event.clientY,dragged:false};
  }
  function pointerMove(event:PointerEvent<HTMLButtonElement>) {
    const start=gesture.current;
    if(start && !start.dragged && event.buttons===1 && Math.hypot(event.clientX-start.x,event.clientY-start.y)>5){
      start.dragged=true;
      setOpen(false);
      onNoticeDismiss?.();
      onStartDrag();
    }
  }
  return <main className="pet-shell pet-popup-shell" data-pet-state={controller.state} onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);onNoticeDismiss?.();}}}>
    {visible && <section className="pet-board-popup" data-notifying={notifying && !active} id="pet-controls" aria-label="璃奈板控制台" onPointerEnter={()=>{setInside(true);if(notifying)setOpen(true);}} onPointerLeave={()=>{setInside(false);leave();}}>
      <img className="board-frame" src="/assets/rina/boards/electronic-faithful.svg" alt="" draggable={false}/>
      {notifying && <div className="board-notice-wash" aria-hidden="true"/>}
      {active && <>
        <img className="star-highlight" data-action={active} src="/assets/rina/boards/electronic-faithful.svg" alt=""/>
        <svg className="board-screen-preview" viewBox="235 30 1070 900" aria-hidden="true">
          <defs><clipPath id="board-screen-only"><path d="M497 219 768 310 1038 219 1159 281V334L1207 364V743L1086 867H440L331 743V364L374 334V281Z"/></clipPath></defs>
          <image href="/assets/rina/boards/electronic-blank-v3.png" width="1536" height="1024" clipPath="url(#board-screen-only)"/>
        </svg>
        <div className="board-action-preview" data-action={active}><ActionIcon action={active}/></div>
      </>}
      {!active && <><svg className="board-settings-highlight" viewBox="235 30 1070 900" aria-hidden="true">
        <defs>
        <mask id="smile-pink-mask"><image href="/assets/rina/boards/electronic-v3.png" width="1536" height="1024" filter="url(#smile-alpha)"/></mask>
        <filter id="smile-alpha" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  6 -6 0 0 -0.12"/></filter></defs>
        <rect x="235" y="30" width="1070" height="900" fill="#bd5a94" mask="url(#smile-pink-mask)"/>
      </svg>
        <button type="button" className="pet-settings-face" title="设置" aria-label="设置" onFocus={()=>setSettingsFocused(true)} onBlur={()=>setSettingsFocused(false)} onClick={()=>{setOpen(false);onNoticeDismiss?.();onOpenSettings();}}/>
      </>}
      <div className="board-stars">
        {([{id:'chat',label:'打开对话',run:onOpenDialogue},{id:'minimize',label:'最小化',run:()=>{setOpen(false);onNoticeDismiss?.();onMinimize();}},{id:'close',label:'关闭桌宠',run:onClose}] as const).map(action=><button key={action.id} type="button" className="board-star" title={action.label} aria-label={action.label}
          onPointerEnter={()=>enter(action.id)} onPointerLeave={leave}
          onPointerDown={()=>setFocused(null)} onFocus={event=>{if(event.currentTarget.matches(':focus-visible')){setFocused(action.id);if(notifying)setOpen(true);}}} onBlur={()=>setFocused(null)} onClick={()=>{setOpen(false);onNoticeDismiss?.();action.run();}}/>) }
      </div>
    </section>}
    <button className="pet-select-button" type="button" aria-label={sleeping?"璃奈休息中：右键唤醒，拖动移动":"璃奈：点击显示控制板，拖动移动；右键休息"} data-unread={unreadCount>0} aria-expanded={visible} aria-controls={visible?'pet-controls':undefined}
      onPointerDown={pointerDown} onPointerMove={pointerMove}
      onClick={event=>{if(sleeping)return;if(event.detail===0 || !gesture.current?.dragged){if(visible){setOpen(false);onNoticeDismiss?.();}else setOpen(true);}}}
      onContextMenu={event=>{event.preventDefault();controller.toggleSleep('context-menu');}}
      onMouseEnter={()=>{if(controller.state!=='sleep')controller.follow('hover');}}
      onMouseLeave={()=>{if(controller.state==='follow')controller.idle('leave');}}>
      {unreadCount>0 && <span className="pet-unread-dot" role="status" aria-label="有任务已完成，尚未查看"/>}
      <img className="pet-image" src={displayImage ?? controller.view.image} alt="" draggable={false}/>
    </button>
  </main>;
}



