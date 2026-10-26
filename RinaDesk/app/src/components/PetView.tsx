import {BOARD,boardStarPosition} from './boardGeometry';
import {usePetHitRegion} from '../pet/usePetHitRegion';
import {useEffect, useRef, useState, type PointerEvent} from 'react';
import type {usePetController} from '../pet/usePetController';
import './PetBoard.css';
import type {TeleportPhase} from '../pet/usePetTeleport';
import {ACTIVE_TELEPORT_EFFECT,PetTeleportEffect} from './PetTeleportEffect';
import {PetDragEffect} from './PetDragEffect';
import {PetRestVisual} from './PetRestVisual';
import {useEffectPreset} from '../pet/useEffectPreset';
import type {RestEffect} from '../pet/art/artPacks';
import type {ArtEffects} from '../pet/art/artPacks';
import {AlanDroneEscort,AlanVisorSpeech} from './AlanPixelEffects';

interface PetViewProps {
  teleportPhase?:TeleportPhase;
  dragging?: boolean;
  displayImage?: string;
  restEffect?:RestEffect;
  artEffects?:ArtEffects;
  notificationPhase?: 'idle' | 'notifying' | 'unread';
  unreadCount?: number;
  onNoticeDismiss?: () => void;
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

export function PetView({controller,onStartDrag,onMinimize,onClose,onOpenDialogue,onOpenSettings,notificationPhase='idle',unreadCount=0,onNoticeDismiss,dragging=false,displayImage,restEffect='none',artEffects={},teleportPhase='idle'}:PetViewProps) {
  const petImage=displayImage ?? controller.view.image;
  const {preset}=useEffectPreset();
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
  usePetHitRegion(visible,dragging);
  useEffect(()=>{if(sleeping)setOpen(false);},[sleeping]);
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
    if(sleeping)return;
    if(event.button===0) gesture.current={x:event.clientX,y:event.clientY,dragged:false};
  }
  function pointerMove(event:PointerEvent<HTMLButtonElement>) {
    if(sleeping)return;
    const start=gesture.current;
    if(start && !start.dragged && event.buttons===1 && Math.hypot(event.clientX-start.x,event.clientY-start.y)>5){
      start.dragged=true;
      setOpen(false);
      onNoticeDismiss?.();
      onStartDrag();
    }
  }
  return <main className="pet-shell pet-popup-shell" data-pet-state={controller.state} data-teleport={teleportPhase} data-teleport-effect={ACTIVE_TELEPORT_EFFECT} onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);onNoticeDismiss?.();}}}>
    {visible && <section className="pet-board-popup" data-notifying={notifying && !active} id="pet-controls" aria-label="璃奈板控制台" onPointerEnter={()=>{setInside(true);if(notifying)setOpen(true);}} onPointerLeave={()=>{setInside(false);leave();}}>
      <img className="board-frame" src="/assets/rina/boards/electronic-faithful.svg" alt="" draggable={false}/>
      {notifying && <svg className="board-notice-wash" viewBox={BOARD.viewBox} aria-hidden="true"><path d={BOARD.screen} fill="white"/></svg>}
      {active && <>
        <svg className="star-highlight" viewBox={BOARD.viewBox} aria-hidden="true"><polygon points={BOARD.stars[active==='chat'?0:active==='minimize'?1:2].points} fill="#e99ac5" stroke="#bc6498" strokeWidth="3" strokeLinejoin="round"/></svg>
        <svg className="board-screen-preview" viewBox={BOARD.viewBox} aria-hidden="true">
          <defs><pattern id="board-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#e9edf1" strokeWidth="1"/></pattern></defs>
          <path d={BOARD.screen} fill="#fff"/><path d={BOARD.screen} fill="url(#board-grid)"/>
        </svg>
        <div className="board-action-preview" data-action={active}><ActionIcon action={active}/></div>
      </>}
      {!active && <><svg className="board-settings-highlight" viewBox={BOARD.viewBox} aria-hidden="true">
        <path d={BOARD.face} fill="#bd5a94"/>
      </svg>
        <button type="button" className="pet-settings-face" title="设置" aria-label="设置" onFocus={()=>setSettingsFocused(true)} onBlur={()=>setSettingsFocused(false)} onClick={()=>{setOpen(false);onNoticeDismiss?.();onOpenSettings();}}/>
      </>}
      <div className="board-stars">
        {([{id:'chat',label:'打开 Chat',run:onOpenDialogue},{id:'minimize',label:'最小化',run:()=>{setOpen(false);onNoticeDismiss?.();onMinimize();}},{id:'close',label:'关闭桌宠',run:onClose}] as const).map((action,index)=><button key={action.id} type="button" className="board-star" style={boardStarPosition(index)} title={action.label} aria-label={action.label}
          onPointerEnter={()=>enter(action.id)} onPointerLeave={leave}
          onPointerDown={()=>setFocused(null)} onFocus={event=>{if(event.currentTarget.matches(':focus-visible')){setFocused(action.id);if(notifying)setOpen(true);}}} onBlur={()=>setFocused(null)} onClick={()=>{setOpen(false);onNoticeDismiss?.();action.run();}}/>) }
      </div>
    </section>}
    <button className="pet-select-button" type="button" aria-label={sleeping?"璃奈休息中：右键唤醒；休息时位置固定":"璃奈：点击显示控制板，拖动移动；右键休息"} data-unread={unreadCount>0} aria-expanded={visible} aria-controls={visible?'pet-controls':undefined}
      onPointerDown={pointerDown} onPointerMove={pointerMove}
      onClick={event=>{if(sleeping)return;if(event.detail===0 || !gesture.current?.dragged){if(visible){setOpen(false);onNoticeDismiss?.();}else setOpen(true);}}}
      onContextMenu={event=>{event.preventDefault();controller.toggleSleep('context-menu');}}
      onMouseEnter={()=>{if(controller.state!=='sleep')controller.follow('hover');}}
      onMouseLeave={()=>{if(controller.state==='follow')controller.idle('leave');}}>
      {unreadCount>0 && <span className="pet-unread-dot" role="status" aria-label="有任务已完成，尚未查看"/>}
      <PetRestVisual src={petImage} sleeping={sleeping} effect={restEffect}/>
      <AlanVisorSpeech active={controller.state==='talk'&&!sleeping&&!dragging} enabled={Boolean(artEffects.talkVisor)}/>
      <PetTeleportEffect phase={teleportPhase} src={petImage} preset={preset}/>
      <PetDragEffect dragging={dragging} enabled={teleportPhase==='idle'} preset={preset}/>
      <AlanDroneEscort active={dragging&&teleportPhase==='idle'} enabled={Boolean(artEffects.dragDrones)}/>
    </button>
  </main>;
}



