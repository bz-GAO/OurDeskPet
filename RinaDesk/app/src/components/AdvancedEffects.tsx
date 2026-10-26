import {useEffect,useRef,useState} from 'react';
import {useEffectPreset} from '../pet/useEffectPreset';
import type {EffectPreset} from '../pet/motionParticles';
import {PetDragEffect} from './PetDragEffect';
import {PetTeleportEffect} from './PetTeleportEffect';
import './PetBoard.css';
import './AdvancedEffects.css';
import type {ArtEffects} from '../pet/art/artPacks';
import {AlanDroneEscort} from './AlanPixelEffects';

function Preview({preset,src,artEffects}:{preset:EffectPreset;src:string;artEffects:ArtEffects}){
  const [step,setStep]=useState(0);
  useEffect(()=>{const timer=setInterval(()=>setStep(s=>(s+1)%40),100);return()=>clearInterval(timer);},[]);
  const phase=step<22?'idle':step<28?'out':step<34?'in':'idle';
  return <span className="effect-preview" data-teleport={phase} data-teleport-effect="quantum">
    <img className="pet-image" src={src} alt="" draggable={false}/>
    <PetDragEffect dragging={step<16} enabled={phase==='idle'} preset={preset} preview/>
    <AlanDroneEscort active={step<16&&phase==='idle'} enabled={Boolean(artEffects.dragDrones)}/>
    <PetTeleportEffect phase={phase} src={src} preset={preset}/>
  </span>;
}
export function AdvancedEffects({src,artEffects={}}:{src:string;artEffects?:ArtEffects}){
  const {preset,select,error}=useEffectPreset();
  const root=useRef<HTMLDivElement>(null);
  const [visible,setVisible]=useState(false),[motion,setMotion]=useState(false),[foreground,setForeground]=useState(!document.hidden);
  useEffect(()=>{
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
    const update=()=>setMotion(!reduced.matches);update();reduced.addEventListener('change',update);
    const active=()=>setForeground(!document.hidden);document.addEventListener('visibilitychange',active);
    const observer=new IntersectionObserver(entries=>setVisible(entries.some(e=>e.isIntersecting)));
    if(root.current)observer.observe(root.current);
    return()=>{observer.disconnect();reduced.removeEventListener('change',update);document.removeEventListener('visibilitychange',active);};
  },[]);
  const ids:EffectPreset[]=['quantum','forest'];
  return <div ref={root} className="advanced-effects">
    <div className="effect-options" role="radiogroup" aria-label="高级特效">
      {ids.map((id,index)=><button key={id} type="button" className="effect-option" role="radio" aria-checked={preset===id}
        aria-label={id==='quantum'?'青紫粒子特效':'墨绿色粒子特效'} tabIndex={preset===id?0:-1}
        onClick={()=>select(id)} onKeyDown={event=>{
          if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)){
            event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?1:1-index;
            select(ids[next]);root.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[next]?.focus();
          }
        }}>
        {visible&&motion&&foreground?<Preview src={src} preset={id} artEffects={artEffects}/>:<span className="effect-preview effect-still" data-preset={id}><img className="pet-image" src={src} alt=""/><i/><i/><i/></span>}
        {preset===id&&<span className="effect-selected" aria-hidden="true">✓</span>}
      </button>)}
    </div>
    {error&&<p className="settings-error" role="alert">{error}</p>}
  </div>;
}
