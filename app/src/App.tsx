import {usePetSpeech} from './pet/usePetSpeech';
import {SettingsPage} from './components/SettingsPage';
import {usePetDrag} from './pet/usePetDrag';
import {useArtPack} from './pet/art/useArtPack';
import {profileForArt,imageForArt} from './pet/art/artPacks';
import { usePetNotifications } from './notifications/usePetNotifications';
import { useKeepPetOnScreen } from './pet/useKeepPetOnScreen';
import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow } from "@tauri-apps/api/window";
import { WebviewWindow } from "@tauri-apps/api/webviewWindow";
import { CapturePage } from "./components/CapturePage";
import { DialoguePage } from "./components/DialoguePage";
import { PetView } from "./components/PetView";
import { usePetController } from "./pet/usePetController";
import "./App.css";

function App() {
  const art=useArtPack();
  const {dragging,startDrag}=usePetDrag();
  const view = new URLSearchParams(window.location.search).get("view");
  const isDialogueView = view === "dialogue";
  const isCaptureView = view === "capture";
  const isSettingsView = view === "settings";
  const speaking=usePetSpeech(!isDialogueView&&!isCaptureView&&!isSettingsView);
  const petController=usePetController(profileForArt(art.id),speaking);
  const notifications = usePetNotifications(!isDialogueView && !isCaptureView && !isSettingsView);
  useKeepPetOnScreen(!isDialogueView && !isCaptureView && !isSettingsView);

  async function minimizeWindow() {
    try {
      await getCurrentWindow().minimize();
    } catch (error) {
      console.debug("Window minimize is only available inside Tauri.", error);
    }
  }

  async function closeWindow() {
    try {
      await invoke('quit_app');
    } catch (error) {
      console.debug("Window close is only available inside Tauri.", error);
    }
  }

  async function parkPet(targetLabel:'dialogue'|'settings') {
    for (const delay of [80,160,320]) {
      await new Promise(resolve=>setTimeout(resolve,delay));
      try { await invoke('park_pet_beside_window',{targetLabel}); return; }
      catch(error) { if(delay===320)console.warn('Pet automatic placement unavailable',error); }
    }
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
        title: "RinaDesk Agent Dialogue",
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
    const width=Math.min(960,Math.max(420,window.screen.availWidth-24),height*1070/900);
    const settings = new WebviewWindow('settings', {
      url:'/?view=settings',title:'RinaDesk 设置',width,height,
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
      dragging={dragging}
      displayImage={imageForArt(art.id,petController.state,dragging)}
      notificationPhase={notifications.phase}
      unreadCount={notifications.unread}
      onNoticeDismiss={notifications.dismiss}
      onStartDrag={startDrag}
      onMinimize={minimizeWindow}
      onClose={closeWindow}
      onOpenDialogue={openDialogueWindow}
      onOpenSettings={()=>void openSettingsWindow().catch(console.error)}
    />
  );
}

export default App;


