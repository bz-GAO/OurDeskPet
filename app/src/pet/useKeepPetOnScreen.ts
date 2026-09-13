import {useEffect} from 'react';
import {currentMonitor,getCurrentWindow,PhysicalPosition} from '@tauri-apps/api/window';

/** Debounce native movement so the whole popup remains inside the monitor work area. */
export function useKeepPetOnScreen(enabled:boolean) {
  useEffect(()=>{
    if(!enabled)return;
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>|undefined;
    let unlisten:(()=>void)|undefined;
    async function fit(){
      try {
        const win=getCurrentWindow();
        const [monitor,position,size]=await Promise.all([currentMonitor(),win.outerPosition(),win.outerSize()]);
        if(disposed || !monitor)return;
        const area=monitor.workArea;
        const x=Math.max(area.position.x,Math.min(position.x,area.position.x+Math.max(0,area.size.width-size.width)));
        const y=Math.max(area.position.y,Math.min(position.y,area.position.y+Math.max(0,area.size.height-size.height)));
        if(x!==position.x || y!==position.y) await win.setPosition(new PhysicalPosition(x,y));
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
  },[enabled]);
}
