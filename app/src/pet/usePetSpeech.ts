import {useEffect,useState} from 'react';
import {isTauri} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';

export function usePetSpeech(enabled:boolean){
 const [speaking,setSpeaking]=useState(false);
 useEffect(()=>{
  if(!enabled||!isTauri())return;
  const active=new Set<string>();let disposed=false;let off:(()=>void)|undefined;
  void listen<{requestId:string;active:boolean}>('deskpet-speech-state',event=>{
   const value=event.payload;if(!value.requestId)return;
   if(value.active)active.add(value.requestId);else active.delete(value.requestId);
   setSpeaking(active.size>0);
  }).then(fn=>{if(disposed)fn();else off=fn;}).catch(console.error);
  return()=>{disposed=true;off?.();};
 },[enabled]);
 return speaking;
}
