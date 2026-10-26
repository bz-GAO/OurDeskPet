import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {emit,listen} from '@tauri-apps/api/event';
import {ART_STORAGE_KEY,FIXED_NOTIFICATION_BOARD,artPacks,validArtPack,type ArtPack,type ArtPackId} from './artPacks';
type CustomPack=Omit<ArtPack,'folder'|'notificationBoard'|'custom'>;
function selected(){try{return localStorage.getItem(ART_STORAGE_KEY);}catch{return null;}}
function normalize(custom:CustomPack):ArtPack{return {...custom,folder:'',notificationBoard:FIXED_NOTIFICATION_BOARD,custom:true};}
function customPacks(value:unknown):CustomPack[]{
  if(!Array.isArray(value))return [];
  return value.filter((item):item is CustomPack=>{
    if(!item||typeof item!=='object')return false;
    const pack=item as Partial<CustomPack>;
    const images=pack.images as Partial<NonNullable<CustomPack['images']>>|undefined;
    return typeof pack.id==='string'&&typeof pack.label==='string'&&typeof pack.code==='string'&&
      !!images&&['idle','drag','talk','sleep'].every(key=>typeof images[key as keyof typeof images]==='string');
  });
}
export function useArtPack(){
  const [packs,setPacks]=useState<ArtPack[]>(artPacks);
  const packsRef=useRef(packs);packsRef.current=packs;
  const [id,setId]=useState<ArtPackId>(()=>validArtPack(selected()));
  const reload=useCallback(async()=>{
    if(!isTauri()){setPacks(artPacks);setId(validArtPack(selected()));return artPacks;}
    try{
      const custom=customPacks(await invoke<unknown>('art_custom_list'));
      const next=[...artPacks,...custom.map(normalize)];
      packsRef.current=next;setPacks(next);setId(validArtPack(selected(),next));return next;
    }catch(error){console.warn('Custom art could not be loaded',error);setPacks(artPacks);setId(validArtPack(selected()));return artPacks;}
  },[]);
  useEffect(()=>{
    let disposed=false;let offChange:(()=>void)|undefined;let offPacks:(()=>void)|undefined;
    const sync=()=>setId(validArtPack(selected(),packsRef.current));
    window.addEventListener('storage',sync);
    window.addEventListener('rinadesk-art-change',sync);
    void reload();
    if(isTauri()){
      void listen<string>('deskpet-art-change',e=>setId(validArtPack(e.payload,packsRef.current))).then(fn=>{if(disposed)fn();else offChange=fn;}).catch(console.error);
      void listen('deskpet-art-packs-change',()=>void reload()).then(fn=>{if(disposed)fn();else offPacks=fn;}).catch(console.error);
    }
    return()=>{disposed=true;offChange?.();offPacks?.();window.removeEventListener('storage',sync);window.removeEventListener('rinadesk-art-change',sync);};
  },[reload]);
  function select(value:string){
    const next=validArtPack(value,packs);setId(next);
    try{localStorage.setItem(ART_STORAGE_KEY,next);}catch(error){console.warn('Art preference could not be saved',error);}
    window.dispatchEvent(new Event('rinadesk-art-change'));
    if(isTauri())void emit('deskpet-art-change',next).catch(console.error);
  }
  return {id,packs,select,reload};
}
