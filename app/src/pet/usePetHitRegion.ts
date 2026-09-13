import {useLayoutEffect} from 'react';
import {invoke, isTauri} from '@tauri-apps/api/core';

/** Preserve the window anchor while removing its unused native input area. */
export function usePetHitRegion(boardVisible:boolean) {
  useLayoutEffect(()=>{
    if(!isTauri())return;
    let previous='';
    const update=()=>{
      const elements=[document.querySelector<HTMLElement>('.pet-select-button'),
        ...(boardVisible?[document.querySelector<HTMLElement>('.pet-board-popup')]:[])];
      const rects=elements.filter((e):e is HTMLElement=>Boolean(e)).map(e=>{
        // offset dimensions avoid clipping the popup's temporary entrance transform.
        const x=e.classList.contains('pet-select-button')?e.offsetLeft-e.offsetWidth/2:e.offsetLeft;
        const pad=e.classList.contains('pet-board-popup')?4:0;
        return {x:x-pad,y:e.offsetTop-pad,width:e.offsetWidth+pad*2,height:e.offsetHeight+pad*2};
      });
      const key=JSON.stringify([rects,window.devicePixelRatio]);
      if(key===previous || !rects.length)return;
      previous=key;
      void invoke('set_pet_region',{rects}).catch(error=>{previous='';console.warn('Pet input region unavailable',error);});
    };
    const observer=new ResizeObserver(update);
    observer.observe(document.documentElement);
    document.querySelectorAll('.pet-select-button,.pet-board-popup').forEach(e=>observer.observe(e));
    window.addEventListener('resize',update);
    update();
    return()=>{observer.disconnect();window.removeEventListener('resize',update);};
  },[boardVisible]);
}
