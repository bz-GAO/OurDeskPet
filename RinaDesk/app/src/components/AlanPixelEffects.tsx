import {useEffect,useRef,useState} from 'react';

type VisorFrame='dim'|'bright'|'scan'|'accent';
const TALK_SEQUENCE:{frame:VisorFrame;duration:number}[]=[
  {frame:'accent',duration:150},{frame:'dim',duration:110},{frame:'bright',duration:140},
  {frame:'dim',duration:260},{frame:'scan',duration:130},{frame:'dim',duration:330},
  {frame:'bright',duration:120},{frame:'dim',duration:290},
];

/** Hand-authored A.L.A.N visor pixels. Body art remains untouched. */
export function AlanVisorSpeech({active,enabled}:{active:boolean;enabled:boolean}){
  const [frame,setFrame]=useState<VisorFrame>('dim');
  useEffect(()=>{
    if(!enabled||!active)return;
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){setFrame('dim');return;}
    let disposed=false,timer:ReturnType<typeof setTimeout>|undefined,index=0;
    const step=()=>{const next=TALK_SEQUENCE[index%TALK_SEQUENCE.length];setFrame(next.frame);index++;timer=setTimeout(()=>{if(!disposed)step();},next.duration);};
    step();return()=>{disposed=true;clearTimeout(timer);};
  },[active,enabled]);
  if(!enabled||!active)return null;
  const fill=frame==='dim'?'#9d357f':frame==='accent'?'#ff68cc':frame==='scan'?'#ff83da':'#ef58c1';
  return <svg className="alan-visor-speech" data-frame={frame} viewBox="0 0 1024 1536" shapeRendering="crispEdges" aria-hidden="true">
    <path fill="#6e245e" d="M397 417h13v-10h29v10h9v19h-7v59h-10v12h-21v-9h-10v-17h-5v-47h-7v-12h9zM590 416h9v-9h24v8h9v18h-6v48h-7v16h-21v10h-12v-13h-7v-57h5v-15h6z"/>
    <path fill={fill} d="M414 421h17v16h7v43h-8v12h-15v-13h-6v-39h-6v-10h11zM600 420h14v12h7v39h-7v15h-14v8h-5v-12h-6v-37h6v-17h5z"/>
    {frame==='scan'&&<path fill="#ffd1ef" d="M399 439h42v13h-42zM585 466h34v13h-34z"/>}
    {frame==='accent'&&<path fill="#ffb4e6" d="M402 419h29v12h-29zM590 421h25v12h-25zM405 485h31v12h-31zM584 482h29v12h-29z"/>}
  </svg>;
}

type DronePhase='hidden'|'start'|'move'|'release';
function Drone({side}:{side:'left'|'right'}){
  return <svg className={`alan-drone alan-drone-${side}`} viewBox="0 0 100 70" shapeRendering="crispEdges" aria-hidden="true">
    <g transform={side==='right'?'translate(100 0) scale(-1 1)':undefined}>
      <path className="drone-body" d="M16 18h9L33 3l11 15h24L77 3l9 15h8v8h6v31h-7v8H15v-8H8V26h8z"/>
      <path className="drone-face" d="M24 26h64v32H24z"/>
      <path className="drone-eye" d="M38 35h9v9h-9zM64 35h9v9h-9z"/>
      <path className="drone-mouth" d="M50 48h5v5h5v-5h5v7h-5v4h-6v-4h-4z"/>
      <path className="drone-rotor" d="M8 23H0v-8h28v7H12zM88 23h-5v-8h17v8h-5v42h-7z"/>
      <path className="drone-side" d="M87 28h11v27H87z"/><path className="drone-side-light" d="M91 32h4v19h-4z"/>
    </g>
  </svg>;
}

/** Two theatre-inspired drones stay outside the body silhouette and never join hit testing. */
export function AlanDroneEscort({active,enabled}:{active:boolean;enabled:boolean}){
  const [phase,setPhase]=useState<DronePhase>('hidden');
  const wasActive=useRef(false);
  useEffect(()=>{
    if(!enabled){wasActive.current=false;setPhase('hidden');return;}
    let timer:ReturnType<typeof setTimeout>|undefined;
    if(active){
      if(!wasActive.current){setPhase('start');timer=setTimeout(()=>setPhase('move'),150);}
      else setPhase('move');
    }else if(wasActive.current){setPhase('release');timer=setTimeout(()=>setPhase('hidden'),290);}
    else setPhase('hidden');
    wasActive.current=active;return()=>clearTimeout(timer);
  },[active,enabled]);
  if(phase==='hidden')return null;
  return <span className="alan-drone-escort" data-phase={phase} aria-hidden="true">
    <Drone side="left"/><Drone side="right"/>
    <span className="drone-trail drone-trail-left"><i/><i/><i/></span>
    <span className="drone-trail drone-trail-right"><i/><i/><i/></span>
  </span>;
}
