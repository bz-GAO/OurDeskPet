import {useEffect} from 'react';
import {currentMonitor,getCurrentWindow,PhysicalPosition} from '@tauri-apps/api/window';

const PET_VISIBLE_WIDTH=180;
const PET_VISIBLE_HEIGHT=162;

type Point={x:number;y:number};
type Size={width:number;height:number};
type WorkArea={position:Point;size:Size};

/**
 * The native overlay is intentionally larger than the visible pet. Keep the
 * character on-screen without treating the transparent margins as overflow.
 */
export function clampVisiblePetPosition(position:Point,size:Size,area:WorkArea,scaleFactor=1){
  const visibleWidth=Math.min(size.width,Math.round(PET_VISIBLE_WIDTH*scaleFactor));
  const visibleHeight=Math.min(size.height,Math.round(PET_VISIBLE_HEIGHT*scaleFactor));
  const offsetX=Math.max(0,Math.round((size.width-visibleWidth)/2));
  const offsetY=Math.max(0,size.height-visibleHeight);
  const petX=position.x+offsetX;
  const petY=position.y+offsetY;
  const clampedPetX=Math.max(area.position.x,Math.min(petX,area.position.x+Math.max(0,area.size.width-visibleWidth)));
  const clampedPetY=Math.max(area.position.y,Math.min(petY,area.position.y+Math.max(0,area.size.height-visibleHeight)));
  return {x:position.x+(clampedPetX-petX),y:position.y+(clampedPetY-petY)};
}

/** Minimized Windows coordinates are sentinel values, never placement targets. */
export async function fitPetNow(isCurrent:()=>boolean=()=>true){
  const win=getCurrentWindow();
  if(!isCurrent()||await win.isMinimized())return;
  const [monitor,position,size]=await Promise.all([currentMonitor(),win.outerPosition(),win.outerSize()]);
  if(!isCurrent()||!monitor||await win.isMinimized())return;
  const {x,y}=clampVisiblePetPosition(position,size,monitor.workArea,monitor.scaleFactor);
  if(x!==position.x||y!==position.y)await win.setPosition(new PhysicalPosition(x,y));
}

/** Debounce native movement and keep only the visible pet inside the work area. */
export function useKeepPetOnScreen(enabled:boolean,move:(action:(isCurrent:()=>boolean)=>Promise<void>)=>Promise<void>) {
  useEffect(()=>{
    if(!enabled)return;
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>|undefined;
    let unlisten:(()=>void)|undefined;
    async function fit(){
      try {
        const win=getCurrentWindow();
        if(await win.isMinimized()||!await win.isVisible())return;
        const [monitor,position,size]=await Promise.all([currentMonitor(),win.outerPosition(),win.outerSize()]);
        if(disposed || !monitor)return;
        const target=clampVisiblePetPosition(position,size,monitor.workArea,monitor.scaleFactor);
        const correction=Math.max(Math.abs(target.x-position.x),Math.abs(target.y-position.y));
        if(correction>0 && correction<=Math.max(3,Math.round(3*monitor.scaleFactor))){
          // DPI rounding and a one-pixel edge overshoot should not replay a full
          // disappearance/reappearance cycle after the user releases a drag.
          await win.setPosition(new PhysicalPosition(target.x,target.y));
        }else if(correction>0) await move(async(isCurrent)=>{
          if(disposed||!isCurrent())return;
          // Re-read after the animation: DPI, window size and monitor may have changed.
          const [latest,origin,extent]=await Promise.all([currentMonitor(),win.outerPosition(),win.outerSize()]);
          if(disposed||!latest||!isCurrent()||await win.isMinimized())return;
          const finalPosition=clampVisiblePetPosition(origin,extent,latest.workArea,latest.scaleFactor);
          await win.setPosition(new PhysicalPosition(finalPosition.x,finalPosition.y));
        });
      }catch(error){console.debug('Pet work-area placement unavailable.',error);}
    }
    async function connect(){
      try {
        const off=await getCurrentWindow().onMoved(()=>{clearTimeout(timer);timer=setTimeout(()=>void fit(),350);});
        if(disposed){off();return;}unlisten=off;void fit();
      }catch(error){console.debug('Native window movement unavailable.',error);}
    }
    void connect();
    return()=>{disposed=true;clearTimeout(timer);unlisten?.();};
  },[enabled,move]);
}
