import {useCallback,useEffect,useRef,useState} from 'react';

export type TeleportPhase='idle'|'out'|'hidden'|'in';
type MoveAction=(isCurrent:()=>boolean)=>Promise<void>;
/** One move at a time; later automatic requests replace the pending request. */
export function usePetTeleport(blocked:boolean,skin:string){
  const [phase,setPhase]=useState<TeleportPhase>('idle');
  const state=useRef({generation:0,blocked,busy:false,mounted:true,concealed:false,pending:null as null|MoveAction});
  state.current.blocked=blocked;
  const cancel=useCallback(()=>{
    const s=state.current;s.generation++;s.pending=null;s.concealed=false;
    if(s.mounted)setPhase('idle');
  },[]);
  useEffect(()=>{state.current.mounted=true;return()=>{state.current.mounted=false;cancel();};},[cancel]);
  useEffect(()=>{cancel();},[blocked,skin,cancel]);
  useEffect(()=>{
    const hide=()=>{if(document.hidden&&!state.current.concealed)cancel();};
    document.addEventListener('visibilitychange',hide);
    return()=>document.removeEventListener('visibilitychange',hide);
  },[cancel]);
  const move=useCallback(async(action:MoveAction)=>{
    const s=state.current;
    if(s.blocked||!s.mounted||s.concealed)return;
    s.pending=action;
    if(s.busy)return;
    s.busy=true;
    try{
      while(s.pending&&!s.blocked&&s.mounted){
        const next=s.pending;s.pending=null;
        const generation=s.generation;
        const valid=()=>s.mounted&&!s.blocked&&s.generation===generation;
        const wait=(ms:number)=>new Promise(resolve=>setTimeout(resolve,ms));
        try{
          if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches&&!document.hidden){
            setPhase('out');await wait(600);
            if(!valid())continue;
            setPhase('hidden');await wait(100);
            if(!valid())continue;
            await next(valid);
            if(!valid())continue;
            setPhase('in');await wait(600);
          }else await next(valid);
        }catch(error){console.debug('Automatic pet move failed; restoring visibility.',error);}
        finally{if(valid())setPhase('idle');}
      }
    }finally{s.busy=false;if(s.mounted&&!s.concealed)setPhase('idle');}
  },[]);
  const conceal=useCallback(()=>{
    cancel();state.current.concealed=true;
    if(state.current.mounted)setPhase('hidden');
  },[cancel]);
  const reveal=useCallback(async(action:MoveAction)=>{
    const s=state.current;
    if(!s.mounted||s.blocked)return;
    conceal();const generation=s.generation;
    const valid=()=>s.mounted&&!s.blocked&&s.generation===generation;
    try{
      await action(valid);
      if(!valid())return;
      if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
        setPhase('in');await new Promise(resolve=>setTimeout(resolve,600));
      }
    }catch(error){console.debug('Pet restore placement failed; restoring visibility.',error);}
    finally{if(valid()){s.concealed=false;setPhase('idle');}}
  },[conceal]);
  return {phase,move,cancel,conceal,reveal};
}
