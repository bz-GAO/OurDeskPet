import {useEffect,useRef} from 'react';
import {isTauri} from '@tauri-apps/api/core';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {advanceParticles,emitMotionParticles,MOTION_EDGES,motionOpacity,type MotionParticle,type EffectPreset} from '../pet/motionParticles';

/** Small window-local tail; never changes placement, hit regions or character opacity. */
export function PetDragEffect({dragging,enabled=true,preset='quantum',preview=false}:{dragging:boolean;enabled?:boolean;preset?:EffectPreset;preview?:boolean}){
  const canvas=useRef<HTMLCanvasElement>(null);
  const state=useRef({dragging:false,moved:false,particles:[] as MotionParticle[]});
  const wake=useRef(()=>{});
  useEffect(()=>{
    const target=canvas.current,ctx=target?.getContext('2d');if(!target||!ctx)return;
    let disposed=false,frame=0,last=0;
    let off:(()=>void)|undefined,offScale:(()=>void)|undefined;
    let previous:{x:number;y:number}|undefined,scale=1;
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    const clear=()=>{state.current.particles=[];state.current.moved=false;cancelAnimationFrame(frame);frame=0;ctx.clearRect(0,0,240,200);};
    const paint=(now:number)=>{
      frame=0;if(disposed||reduced.matches||!enabled){clear();return;}
      state.current.particles=advanceParticles(state.current.particles,(now-last)/1000);last=now;
      ctx.clearRect(0,0,240,200);
      for(const p of state.current.particles){
        ctx.globalAlpha=motionOpacity(p.age,p.life);ctx.strokeStyle=MOTION_EDGES[p.color]??p.color;
        const x=Math.round(p.x),y=Math.round(p.y);
        if(p.outline)ctx.strokeRect(x+.5,y+.5,p.size-1,p.size-1);
        else {
          ctx.fillStyle=MOTION_EDGES[p.color]??p.color;ctx.fillRect(x,y,p.size,p.size);
          ctx.fillStyle=p.color;ctx.fillRect(x,y,p.size-1,p.size-1);
        }
      }
      ctx.globalAlpha=1;
      if(state.current.particles.length)frame=requestAnimationFrame(paint);
    };
    wake.current=()=>{if(!disposed&&enabled&&!reduced.matches&&!frame){last=performance.now();frame=requestAnimationFrame(paint);}};
    const movement=(x:number,y:number)=>{
      const before=previous;previous={x,y};
      if(!before||!enabled||!state.current.dragging||reduced.matches)return;
      const dx=(x-before.x)/scale,dy=(y-before.y)/scale;
      if(Math.hypot(dx,dy)>=.75&&Math.hypot(dx,dy)<=120)state.current.moved=true;
      emitMotionParticles(state.current.particles,dx,dy,false,Math.random,preset);wake.current();
    };
    const pointer=(event:PointerEvent)=>movement(event.screenX,event.screenY);
    async function connect(){
      try{
        const win=getCurrentWindow();
        const [factor,origin]=await Promise.all([win.scaleFactor(),win.outerPosition()]);
        scale=factor;previous={x:origin.x,y:origin.y};
        if(disposed)return;
        const stopScale=await win.onScaleChanged(event=>{scale=event.payload.scaleFactor;previous=undefined;clear();});
        if(disposed){stopScale();return;}offScale=stopScale;
        const stop=await win.onMoved(event=>movement(event.payload.x,event.payload.y));
        if(disposed){stop();return;}off=stop;
      }catch(error){console.debug('Drag particle movement unavailable',error);}
    }
    let demo:ReturnType<typeof setInterval>|undefined;
    if(preview){let x=0;previous={x:0,y:0};demo=setInterval(()=>{x+=3;movement(x,0);},45);}
    else if(isTauri())void connect();else window.addEventListener('pointermove',pointer);
    const preference=()=>{if(reduced.matches)clear();};reduced.addEventListener('change',preference);
    const visibility=()=>{if(document.hidden){previous=undefined;clear();}};
    document.addEventListener('visibilitychange',visibility);
    return()=>{disposed=true;clear();clearInterval(demo);wake.current=()=>{};off?.();offScale?.();window.removeEventListener('pointermove',pointer);reduced.removeEventListener('change',preference);document.removeEventListener('visibilitychange',visibility);};
  },[enabled,preset,preview]);
  useEffect(()=>{
    const s=state.current;
    if(dragging&&!s.dragging){s.moved=false;s.particles=[];}
    if(!dragging&&s.dragging&&s.moved&&enabled){emitMotionParticles(s.particles,0,0,true,Math.random,preset);wake.current();}
    s.dragging=dragging;
  },[dragging,enabled,preset]);
  return <canvas ref={canvas} className="pet-drag-fx" width="240" height="200" aria-hidden="true"/>;
}
