import {invoke} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import {useCallback,useEffect,useRef,useState} from 'react';
import type {TeleportPhase} from './usePetTeleport';

const EXIT_ANIMATION_MS=600;

/**
 * Funnels both the board action and native main-window close requests through
 * one graceful exit. Conversation data is flushed while the pet dissolves;
 * the process is terminated only after both have completed.
 */
export function usePetExit(enabled:boolean,cancelMotion:()=>void,onError:(error:unknown)=>void){
  const [phase,setPhase]=useState<TeleportPhase>('idle');
  const exiting=useRef(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);

  const request=useCallback(async()=>{
    if(!enabled||exiting.current)return;
    exiting.current=true;
    cancelMotion();
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches||document.hidden;
    setPhase(reduced?'hidden':'out');
    try{
      const flush=invoke('prepare_quit_app');
      if(reduced)await flush;
      else await Promise.all([flush,new Promise(resolve=>setTimeout(resolve,EXIT_ANIMATION_MS))]);
      if(mounted.current)setPhase('hidden');
      await invoke('complete_quit_app');
    }catch(error){
      exiting.current=false;
      if(mounted.current)setPhase('idle');
      onError(error);
    }
  },[enabled,cancelMotion,onError]);

  useEffect(()=>{
    if(!enabled)return;
    let disposed=false,unlisten:(()=>void)|undefined;
    void listen('deskpet-exit-requested',()=>void request()).then(stop=>{if(disposed)stop();else unlisten=stop;}).catch(onError);
    return()=>{disposed=true;unlisten?.();};
  },[enabled,onError,request]);

  return {phase,request,active:phase!=='idle'};
}
