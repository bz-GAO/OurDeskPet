import {useEffect,useState} from 'react';
import {isTauri} from '@tauri-apps/api/core';
import {emit,listen} from '@tauri-apps/api/event';
import {ART_STORAGE_KEY,validArtPack,type ArtPackId} from './artPacks';
function read(){try{return validArtPack(localStorage.getItem(ART_STORAGE_KEY));}catch{return validArtPack(null);}}
export function useArtPack(){
  const [id,setId]=useState<ArtPackId>(read);
  useEffect(()=>{
    let disposed=false;let off:(()=>void)|undefined;
    const sync=()=>setId(read());
    window.addEventListener('storage',sync);
    window.addEventListener('rinadesk-art-change',sync);
    if(isTauri())void listen<string>('deskpet-art-change',e=>setId(validArtPack(e.payload))).then(fn=>{if(disposed)fn();else off=fn;}).catch(console.error);
    return()=>{disposed=true;off?.();window.removeEventListener('storage',sync);window.removeEventListener('rinadesk-art-change',sync);};
  },[]);
  function select(value:string){
    const next=validArtPack(value);setId(next);
    try{localStorage.setItem(ART_STORAGE_KEY,next);}catch(error){console.warn('Art preference could not be saved',error);}
    window.dispatchEvent(new Event('rinadesk-art-change'));
    if(isTauri())void emit('deskpet-art-change',next).catch(console.error);
  }
  return {id,select};
}
