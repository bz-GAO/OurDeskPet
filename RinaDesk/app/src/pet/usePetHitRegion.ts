import {useEffect,useLayoutEffect,useState} from 'react';
import {invoke, isTauri} from '@tauri-apps/api/core';

// The board enters with a short scale/translate animation and its top star
// protrudes slightly beyond the artwork box. Reserve the whole animated edge
// so SetWindowRgn cannot freeze a smaller, mid-animation clipping rectangle.
const BOARD_REGION_PAD=12;

/** Preserve the window anchor while removing its unused native input area. */
export function usePetHitRegion(boardVisible:boolean,dragging=false) {
  const [releaseSpace,setReleaseSpace]=useState(false);
  // Keep the expanded region until the drones' 290ms release animation ends.
  useEffect(()=>{
    if(dragging){setReleaseSpace(true);return;}
    const timer=setTimeout(()=>setReleaseSpace(false),360);
    return()=>clearTimeout(timer);
  },[dragging]);
  const dragSpace=dragging||releaseSpace;
  useLayoutEffect(()=>{
    if(!isTauri())return;
    let previous='';
    const update=()=>{
      const elements=[document.querySelector<HTMLElement>('.pet-select-button'),
        ...(boardVisible?[document.querySelector<HTMLElement>('.pet-board-popup')]:[])];
      const rects=elements.filter((e):e is HTMLElement=>Boolean(e)).map(e=>{
        // The visual shell stays 280px wide inside a stable 420px native
        // canvas. Viewport coordinates keep the region aligned in both the
        // initial 280px bootstrap frame and the settled wide frame.
        const box=e.getBoundingClientRect();
        const x=box.left;
        const pad=e.classList.contains('pet-board-popup')?BOARD_REGION_PAD:0;
        if(dragSpace&&e.classList.contains('pet-select-button')){
          // SetWindowRgn clips rendering as well as pointer input. During drag,
          // give the escort the full stable native canvas instead of estimating
          // the animated SVG/filter bounds; the region is temporary and avoids
          // DPI- or WebView-specific edge clipping.
          return {x:box.left+box.width/2-210,y:box.top+box.height-230,width:420,height:230};
        }
        return {x:x-pad,y:box.top-pad,width:box.width+pad*2,height:box.height+pad*2};
      });
      const viewportWidth=window.innerWidth;
      const key=JSON.stringify([rects,window.devicePixelRatio,dragSpace,viewportWidth]);
      if(key===previous || !rects.length)return;
      previous=key;
      void invoke('set_pet_region',{rects,dragSpace,viewportWidth}).catch(error=>{previous='';console.warn('Pet input region unavailable',error);});
    };
    const observer=new ResizeObserver(update);
    const refresh=()=>{previous='';update();};
    observer.observe(document.documentElement);
    document.querySelectorAll('.pet-select-button,.pet-board-popup').forEach(e=>observer.observe(e));
    window.addEventListener('resize',update);
    window.addEventListener('focus',refresh);
    update();
    return()=>{observer.disconnect();window.removeEventListener('resize',update);window.removeEventListener('focus',refresh);};
  },[boardVisible,dragSpace]);
}
