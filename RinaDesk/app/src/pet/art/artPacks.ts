import {defaultPetProfile} from '../profiles/defaultPetProfile';
import type {PetProfile,PetState} from '../types';

export type ArtImages={idle:string;drag:string;talk:string;sleep:string};
export type RestEffect='none'|'pixel-mask';
export type ArtEffects={talkVisor?:boolean;dragDrones?:boolean};
export type ArtPack={
  id:string;label:string;code:string;folder:string;notificationBoard:string;
  custom?:boolean;images?:ArtImages;restEffect?:RestEffect;effects?:ArtEffects;
};

export const FIXED_NOTIFICATION_BOARD='/assets/rina/boards/electronic-faithful.svg';
export const artPacks:ArtPack[] = [
  {id:'rina-alan-pixel-v1',label:'璃奈 · A.L.A.N 像素',code:'RINA-ALAN-PIXEL-01',folder:'alan-pixel-v1',notificationBoard:FIXED_NOTIFICATION_BOARD,
    images:{idle:'/assets/rina/alan-pixel-v1/idle.png',drag:'/assets/rina/alan-pixel-v1/idle.png',talk:'/assets/rina/alan-pixel-v1/idle.png',sleep:'/assets/rina/alan-pixel-v1/sleep.png'},
    restEffect:'pixel-mask',effects:{talkVisor:true,dragDrones:true}},
];
export type ArtPackId = string;
export const ART_STORAGE_KEY='rinadesk.art-pack';

export function validArtPack(value:unknown,packs:ArtPack[]=artPacks):ArtPackId {
  return packs.find(pack=>pack.id===value)?.id??'rina-alan-pixel-v1';
}
function packFor(id:ArtPackId,packs:ArtPack[]):ArtPack{return packs.find(pack=>pack.id===id)??artPacks.find(pack=>pack.id==='rina-alan-pixel-v1')!;}
export function restEffectForArt(id:ArtPackId,packs:ArtPack[]=artPacks):RestEffect{return packFor(id,packs).restEffect??'none';}
export function effectsForArt(id:ArtPackId,packs:ArtPack[]=artPacks):ArtEffects{return packFor(id,packs).effects??{};}
const profiles=new WeakMap<ArtPack,PetProfile>();
export function profileForArt(id:ArtPackId,packs:ArtPack[]=artPacks):PetProfile {
  const pack=packFor(id,packs);
  if(pack.id==='rina-astromeda-v1')return defaultPetProfile;
  const cached=profiles.get(pack);if(cached)return cached;
  const profile:PetProfile={
    ...defaultPetProfile,id:pack.id,
    states:Object.fromEntries(Object.entries(defaultPetProfile.states).map(([state,view])=>{
      const image=pack.images?.[state==='talk'?'talk':state==='sleep'?'sleep':'idle']??`/assets/rina/${pack.folder}/${state==='talk'||state==='sleep'?state:'idle'}.png`;
      return [state,{...view,image,imageAlt:pack.label}];
    })) as PetProfile['states'],
  };
  profiles.set(pack,profile);return profile;
}
export function imageForArt(id:ArtPackId,state:PetState,dragging:boolean,packs:ArtPack[]=artPacks):string {
  const pack=packFor(id,packs);
  if(dragging&&state!=='sleep'&&pack.id!=='rina-astromeda-v1')return pack.images?.drag??`/assets/rina/${pack.folder}/drag.png`;
  return profileForArt(pack.id,packs).states[state].image;
}
