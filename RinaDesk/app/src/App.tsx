import {BOARD} from './components/boardGeometry';
import {usePetSpeech} from './pet/usePetSpeech';
import {SettingsPage} from './components/SettingsPage';
import {usePetDrag} from './pet/usePetDrag';
import {usePetTeleport} from './pet/usePetTeleport';
import {usePetRestore} from './pet/usePetRestore';
import {useArtPack} from './pet/art/useArtPack';
import {effectsForArt,profileForArt,imageForArt,restEffectForArt} from './pet/art/artPacks';
import { usePetNotifications } from './notifications/usePetNotifications';
import { useKeepPetOnScreen } from './pet/useKeepPetOnScreen';
import { invoke } from '@tauri-apps/api/core';
import {emitTo} from '@tauri-apps/api/event';
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { CapturePage } from "./components/CapturePage";
import { DialoguePage } from "./components/DialoguePage";
import { PetView } from "./components/PetView";
import { usePetController } from "./pet/usePetController";
import "./App.css";
import {useEffect,useRef,useCallback} from 'react';
import {playSfx} from './voice/sfx';
import {usePetExit} from './pet/usePetExit';

function App() {
  const art=useArtPack();
  const {dragging,startDrag}=usePetDrag();
  const teleport=usePetTeleport(dragging,art.id);
  const view = new URLSearchParams(window.location.search).get("view");
  const isDialogueView = view === "dialogue";
  const isCaptureView = view === "capture";
  const isSettingsView = view === "settings";
  const restore=usePetRestore(!isDialogueView&&!isCaptureView&&!isSettingsView,teleport);
  const speaking=usePetSpeech(!isDialogueView&&!isCaptureView&&!isSettingsView);
  const petController=usePetController(profileForArt(art.id,art.packs),speaking);
  const notifications = usePetNotifications(!isDialogueView && !isCaptureView && !isSettingsView);
  const reportQuitError=useCallback(async(error:unknown)=>{
    const dialogue=await WebviewWindow.getByLabel('dialogue');
    if(dialogue){await dialogue.show();await dialogue.setFocus();await emitTo('dialogue','deskpet-quit-error',String(error));}
    else console.debug('Window close is only available inside Tauri.',error);
  },[]);
  const gracefulExit=usePetExit(!isDialogueView&&!isCaptureView&&!isSettingsView,teleport.cancel,reportQuitError);
  // 事件音效：通知板弹出与量子传送（出发瞬间）。后端按设置/reviewed 闸门决定是否出声。
  const sfxNotifyRef=useRef(false);
  useEffect(()=>{const active=notifications.phase==='notifying';if(active&&!sfxNotifyRef.current)playSfx('notify');sfxNotifyRef.current=active;},[notifications.phase]);
  const sfxTeleportRef=useRef(false);
  useEffect(()=>{const active=!isDialogueView&&!isCaptureView&&!isSettingsView&&teleport.phase==='out';if(active&&!sfxTeleportRef.current)playSfx('teleport');sfxTeleportRef.current=active;},[teleport.phase,isDialogueView,isCaptureView,isSettingsView]);
  const visualTeleportPhase=gracefulExit.active?gracefulExit.phase:teleport.phase;
  useKeepPetOnScreen(!isDialogueView && !isCaptureView && !isSettingsView && !dragging,teleport.move);

  async function minimizeWindow() {
    try {
      await restore.minimize();
    } catch (error) {
      console.debug("Window minimize is only available inside Tauri.", error);
    }
  }

  async function parkPet(targetLabel:'dialogue'|'settings') {
    // Ask before animating, so opening an already unobstructed panel never flashes the pet.
    try {
      const placement=await invoke<{side:string}>('park_pet_beside_window',{targetLabel,previewOnly:true});
      if(placement.side==='unchanged')return;
    }catch(error){console.debug('Pet placement preflight unavailable',error);return;}
    await teleport.move(async(isCurrent)=>{
    for (const delay of [80,160,320]) {
      await new Promise(resolve=>setTimeout(resolve,delay));
      if(!isCurrent())return;
      try { await invoke('park_pet_beside_window',{targetLabel}); return; }
      catch(error) { if(delay===320)console.warn('Pet automatic placement unavailable',error); }
    }
    });
  }
  async function openDialogueWindow() {
    try {
      const existingWindow = await WebviewWindow.getByLabel("dialogue");
      if (existingWindow) {
        await existingWindow.unminimize();
        await existingWindow.show();
        await existingWindow.setFocus();
        await parkPet('dialogue');
        return;
      }

      const dialogueWindow = new WebviewWindow("dialogue", {
        url: "/?view=dialogue",
        title: "RinaDesk Chat",
        width: 920,
        height: 680,
        minWidth: 680,
        minHeight: 500,
        resizable: true,
        decorations: true,
        center: true,
      });

      dialogueWindow.once('tauri://created',()=>void parkPet('dialogue'));
      dialogueWindow.once("tauri://error", (event) => {
        console.error("Failed to open dialogue window.", event);
      });
    } catch (error) {
      console.debug("Dialogue window is only available inside Tauri.", error);
    }
  }

  async function openSettingsWindow() {
    const existing = await WebviewWindow.getByLabel('settings');
    if (existing) { await existing.unminimize(); await existing.show(); await existing.setFocus(); await parkPet('settings'); return; }
    const height=Math.min(808,Math.max(360,window.screen.availHeight-36));
    const width=Math.min(960,Math.max(420,window.screen.availWidth-24),height*BOARD.width/BOARD.height);
    const settings = new WebviewWindow('settings', {
      url:'/?view=settings',title:'RinaDesk 设置',width,height:Math.min(height,width*BOARD.height/BOARD.width),
      minWidth:Math.min(760,width),minHeight:Math.min(640,height),transparent:true,decorations:false,shadow:false,
      resizable:true,center:true,
    });
    settings.once('tauri://created',()=>void parkPet('settings'));
    settings.once('tauri://error', e => console.error('Settings window failed',e));
  }
  if (isSettingsView) return <SettingsPage/>;
  if (isDialogueView) {
    return <DialoguePage />;
  }

  if (isCaptureView) {
    return <CapturePage />;
  }

  return (
    <PetView
      controller={petController}
      teleportPhase={visualTeleportPhase}
      dragging={dragging}
      displayImage={imageForArt(art.id,petController.state,dragging,art.packs)}
      restEffect={restEffectForArt(art.id,art.packs)}
      artEffects={effectsForArt(art.id,art.packs)}
      notificationPhase={notifications.phase}
      unreadCount={notifications.unread}
      onNoticeDismiss={notifications.dismiss}
      onStartDrag={()=>{if(gracefulExit.active)return;teleport.cancel();void startDrag();}}
      onMinimize={minimizeWindow}
      onClose={()=>void gracefulExit.request()}
      onOpenDialogue={openDialogueWindow}
      onOpenSettings={()=>void openSettingsWindow().catch(console.error)}
    />
  );
}

export default App;


