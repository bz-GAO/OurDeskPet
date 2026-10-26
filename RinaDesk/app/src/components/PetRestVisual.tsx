import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {RestEffect} from '../pet/art/artPacks';

type Transition={key:number;from:string;to:string;direction:'sleep'|'wake'};
const PARTICLES=Array.from({length:18},(_,index)=>({
  left:18+(index*37)%67,
  top:18+(index*29)%70,
  delay:(index%6)*34,
  size:index%5===0?7:index%3===0?5:3,
}));

/** State-art swap with a bounded pixel glitch. It never owns sleep state or movement. */
export function PetRestVisual({src,sleeping,effect}:{src:string;sleeping:boolean;effect:RestEffect}){
  const previousSleeping=useRef(sleeping);
  const previousSrc=useRef(src);
  const latestAwake=useRef(src);
  const serial=useRef(0);
  const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
  const [transition,setTransition]=useState<Transition|null>(null);
  if(!sleeping)latestAwake.current=src;
  useLayoutEffect(()=>{
    const changed=previousSleeping.current!==sleeping;
    const oldSrc=previousSrc.current;
    previousSleeping.current=sleeping;
    previousSrc.current=src;
    if(!changed)return;
    if(effect!=='pixel-mask'||window.matchMedia('(prefers-reduced-motion: reduce)').matches){
      clearTimeout(timer.current);setTransition(null);return;
    }
    const key=++serial.current;
    setTransition({key,from:sleeping?latestAwake.current:oldSrc,to:src,direction:sleeping?'sleep':'wake'});
    clearTimeout(timer.current);
    timer.current=setTimeout(()=>setTransition(current=>current?.key===key?null:current),860);
  },[sleeping,src,effect]);
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  return <span className="pet-rest-visual" data-effect={effect} data-animating={transition?.direction}>
    <img className="pet-image" src={src} alt="" draggable={false}/>
    {transition&&<span className="pet-rest-fx" data-direction={transition.direction} key={transition.key} aria-hidden="true">
      <img className="pet-rest-layer pet-rest-from" src={transition.from} alt="" draggable={false}/>
      <img className="pet-rest-layer pet-rest-to" src={transition.to} alt="" draggable={false}/>
      {Array.from({length:7},(_,index)=><img key={`strip-${index}`} className={`pet-rest-layer pet-rest-strip pet-rest-strip-${index+1}`} src={transition.from} alt="" draggable={false}/>)}
      {PARTICLES.map((particle,index)=><i key={index} style={{left:`${particle.left}%`,top:`${particle.top}%`,width:particle.size,height:particle.size,animationDelay:`${particle.delay}ms`}}/>)}
    </span>}
  </span>;
}
