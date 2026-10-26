import {useCallback, useEffect, useRef, useState} from 'react';
import {isTauri, invoke} from '@tauri-apps/api/core';
import {listen, emitTo} from '@tauri-apps/api/event';
import {getCurrentWindow, UserAttentionType} from '@tauri-apps/api/window';
import {NotificationController, type NoticeState, type TaskEvent} from './notificationController';
import {forgetYakiJob,watchedYakiJobs} from '../extensions/rinayaki/yakiJobWatch';

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
        try { return await invoke<boolean>('dialogue_is_reading'); }
        catch { return false; }
      },
      reveal:()=>safe(()=>invoke('reveal_pet_notification')),
      attention:(active)=>safe(()=>pet.requestUserAttention(active ? UserAttentionType.Informational : null)),
      changed:setState,
      schedule:(callback,ms)=>{const timer=setTimeout(callback,ms); return ()=>clearTimeout(timer);},
    });
    controller.current=machine;
    // Only query while a notice is pending; a missed focus event must not leave it unread.
    let checking=false;
    const readingTimer=setInterval(()=>{
      if(disposed || checking || !machine.hasUnread('chat'))return;
      checking=true;
      void invoke<boolean>('dialogue_is_reading').then(reading=>{
        if(!disposed && reading)machine.acknowledge('chat');
      }).catch(()=>{}).finally(()=>{checking=false;});
    },500);
    let checkingYaki=false;
    const checkYaki=async()=>{
      if(disposed||checkingYaki)return;
      const jobs=watchedYakiJobs();
      if(!jobs.length)return;
      checkingYaki=true;
      try{
        for(const job of jobs){
          if(disposed)break;
          try{
            const result=await invoke<{state:{status:string}}>('extension_yaki_action',{action:'status',request:{job}});
            if(result.state.status==='complete'){
              await machine.receive({source:'rinayaki',taskId:job,status:'completed'});
              forgetYakiJob(job);
            }
          }catch(error){console.debug('RinaYaki task status unavailable',error);}
        }
      }finally{checkingYaki=false;}
    };
    const yakiTimer=setInterval(()=>{void checkYaki();},10000);
    void checkYaki();
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
    return()=>{disposed=true; clearInterval(readingTimer); clearInterval(yakiTimer); machine.dispose(); unlisteners.forEach(fn=>fn()); controller.current=null;};
  },[enabled]);
  const dismiss=useCallback(()=>controller.current?.dismiss(),[]);
  return {...state,dismiss};
}
