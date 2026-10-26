import {useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {getCurrentWindow} from '@tauri-apps/api/window';

/** Drag is a transient presentation override; sleep and other behaviour survive it. */
export function usePetDrag(){
  const [dragging,setDragging]=useState(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    if(!dragging)return;
    let disposed=false;let timer:ReturnType<typeof setTimeout>;
    const end=()=>{if(!disposed)setDragging(false);};
    const poll=async()=>{
      try{if(!await invoke<boolean>('pet_left_button_down')){end();return;}}
      catch(error){console.debug('Drag release check unavailable',error);end();return;}
      if(!disposed)timer=setTimeout(()=>void poll(),60);
    };
    window.addEventListener('pointerup',end);
    if(!isTauri())window.addEventListener('pointercancel',end);
    if(isTauri())timer=setTimeout(()=>void poll(),60);
    return()=>{disposed=true;clearTimeout(timer);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);};
  },[dragging]);
  async function startDrag(){
    setDragging(true);
    // Paint the lifted pose before Windows enters its native move loop.
    await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
    if(!mounted.current || !isTauri())return;
    try{
      if(!await invoke<boolean>('pet_left_button_down')){setDragging(false);return;}
      await getCurrentWindow().startDragging();
    }
    catch(error){console.debug('Native drag unavailable',error);if(mounted.current)setDragging(false);}
    // startDragging may resolve before release; native button polling owns completion.
  }
  return {dragging,startDrag};
}
