import {useCallback, useEffect, useRef, useState} from 'react';
import {isTauri, invoke} from '@tauri-apps/api/core';
import {listen, emitTo} from '@tauri-apps/api/event';
import {getCurrentWindow, UserAttentionType} from '@tauri-apps/api/window';
import {WebviewWindow} from '@tauri-apps/api/webviewWindow';
import {NotificationController, type NoticeState, type TaskEvent} from './notificationController';

/** Future local translation/audio integrations publish metadata through this adapter. */
export function publishTaskEvent(event: TaskEvent) { return emitTo('main','deskpet-task-event',event); }
export function acknowledgeTaskSource(source: string) { return emitTo('main','deskpet-task-read',{source}); }

export function usePetNotifications(enabled: boolean) {
  const [state,setState]=useState<NoticeState>({phase:'idle',unread:0});
  const controller=useRef<NotificationController|null>(null);
  useEffect(()=>{
    if(!enabled || !isTauri()) return;
    let disposed=false;
    const unlisteners:Array<()=>void>=[];
    const pet=getCurrentWindow();
    const safe=async(action:()=>Promise<unknown>)=>{try{await action();}catch(error){console.debug('Pet notification window action unavailable',error);}};
    const machine=new NotificationController({
      isReading:async(source)=>{
        if(source!=='chat') return false;
        try { const dialogue=await WebviewWindow.getByLabel('dialogue'); return Boolean(dialogue && await dialogue.isFocused()); }
        catch { return false; }
      },
      reveal:()=>safe(()=>invoke('reveal_pet_notification')),
      attention:(active)=>safe(()=>pet.requestUserAttention(active ? UserAttentionType.Informational : null)),
      changed:setState,
      schedule:(callback,ms)=>{const timer=setTimeout(callback,ms); return ()=>clearTimeout(timer);},
    });
    controller.current=machine;
    const register=async()=>{
      const subscriptions=[
        listen<TaskEvent>('deskpet-task-event',event=>{void machine.receive(event.payload);}),
        listen<{source:string}>('deskpet-task-read',event=>machine.acknowledge(event.payload.source)),
      ];
      for(const pending of subscriptions) {
        try {const unlisten=await pending; if(disposed) unlisten(); else unlisteners.push(unlisten);}
        catch(error) {console.error('Could not subscribe to pet notifications',error);}
      }
    };
    void register();
    return()=>{disposed=true; machine.dispose(); unlisteners.forEach(fn=>fn()); controller.current=null;};
  },[enabled]);
  const dismiss=useCallback(()=>controller.current?.dismiss(),[]);
  return {...state,dismiss};
}
