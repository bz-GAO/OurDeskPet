import {useEffect,useState} from 'react';
import {isTauri} from '@tauri-apps/api/core';
import {emit,listen} from '@tauri-apps/api/event';
import {validEffectPreset,type EffectPreset} from './motionParticles';
export const EFFECT_STORAGE_KEY='rinadesk.effect-preset';
export function currentEffectPreset():EffectPreset{
  try{return validEffectPreset(localStorage.getItem(EFFECT_STORAGE_KEY));}catch{return 'quantum';}
}
export function useEffectPreset(){
  const [preset,setPreset]=useState(currentEffectPreset);
  const [error,setError]=useState('');
  useEffect(()=>{
    let disposed=false,off:(()=>void)|undefined;
    const sync=()=>setPreset(currentEffectPreset());
    window.addEventListener('storage',sync);window.addEventListener('rinadesk-effect-change',sync);
    // Reconcile changes made while this window was suspended/minimized.
    window.addEventListener('focus',sync);
    if(isTauri())void listen('deskpet-effect-change',sync).then(fn=>{if(disposed)fn();else{off=fn;sync();}}).catch(console.error);
    return()=>{disposed=true;off?.();window.removeEventListener('storage',sync);window.removeEventListener('rinadesk-effect-change',sync);window.removeEventListener('focus',sync);};
  },[]);
  function select(value:EffectPreset){
    const next=validEffectPreset(value);
    try{localStorage.setItem(EFFECT_STORAGE_KEY,next);}catch{setError('未能保存特效选择，请重试。');return;}
    setError('');setPreset(next);window.dispatchEvent(new Event('rinadesk-effect-change'));
    if(isTauri())void emit('deskpet-effect-change').catch(console.error);
  }
  return {preset,select,error};
}
