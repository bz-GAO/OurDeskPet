import {useCallback,useEffect,useRef} from 'react';
import {isTauri} from '@tauri-apps/api/core';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {fitPetNow} from './useKeepPetOnScreen';
import type {usePetTeleport} from './usePetTeleport';

export function usePetRestore(enabled:boolean,teleport:ReturnType<typeof usePetTeleport>){
  const {conceal,reveal,cancel}=teleport;
  const state=useRef({minimized:false,requesting:false,checking:false,restoring:false});
  useEffect(()=>{
    if(!enabled||!isTauri())return;
    let disposed=false;const off:Array<()=>void>=[];
    const check=async()=>{
      const s=state.current;if(disposed||s.checking||s.requesting)return;s.checking=true;
      try{
        const minimized=await getCurrentWindow().isMinimized();
        if(disposed)return;
        if(minimized){if(!s.minimized){s.minimized=true;conceal();}}
        else if(s.minimized&&!s.restoring){
          s.minimized=false;s.restoring=true;
          try{await reveal(valid=>fitPetNow(()=>!disposed&&valid()));}
          finally{s.restoring=false;}
        }
      }catch(error){console.debug('Pet restore state unavailable.',error);}
      finally{s.checking=false;}
    };
    const register=async()=>{
      for(const subscribe of [
        ()=>getCurrentWindow().onResized(()=>void check()),
        ()=>getCurrentWindow().onFocusChanged(()=>void check()),
      ]){
        try{const remove=await subscribe();if(disposed)remove();else off.push(remove);}
        catch(error){console.debug('Pet restore listener unavailable.',error);}
      }
      void check();
    };
    const wake=()=>void check();
    document.addEventListener('visibilitychange',wake);
    // Fallback for native taskbar/notification restore paths that omit focus.
    const timer=setInterval(wake,500);void register();
    return()=>{disposed=true;clearInterval(timer);off.forEach(fn=>fn());document.removeEventListener('visibilitychange',wake);};
  },[enabled,conceal,reveal]);
  const minimize=useCallback(async()=>{
    const s=state.current;if(s.requesting)return;
    s.requesting=true;conceal();
    try{
      // Paint invisibility before the native minimize/restore path can take a snapshot.
      await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
      await getCurrentWindow().minimize();s.minimized=true;
    }catch(error){s.minimized=false;cancel();throw error;}
    finally{s.requesting=false;}
  },[conceal,cancel]);
  return {minimize};
}
