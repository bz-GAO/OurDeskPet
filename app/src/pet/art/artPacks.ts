import {defaultPetProfile} from '../profiles/defaultPetProfile';
import type {PetProfile,PetState} from '../types';

export const artPacks = [
  {id:'rina-summer-v1',label:'璃奈 · 夏服·开衫',code:'RINA-SUMMER-01',folder:'summer-v1',notificationBoard:'/assets/rina/boards/electronic-faithful.svg'},
  {id:'rina-winter-v1',label:'璃奈 · 冬服·外套',code:'RINA-WINTER-01',folder:'winter-v1',notificationBoard:'/assets/rina/boards/electronic-faithful.svg'},
  {id:'rina-astromeda-v1',label:'璃奈 · Astromeda（原版）',code:'RINA-ASTROMEDA-01',folder:'',notificationBoard:'/assets/rina/boards/electronic-faithful.svg'},
] as const;
export type ArtPackId = typeof artPacks[number]['id'];
export const ART_STORAGE_KEY='rinadesk.art-pack';
export function validArtPack(value:unknown):ArtPackId {
  return artPacks.find(pack=>pack.id===value)?.id??'rina-winter-v1';
}
const profiles=Object.fromEntries(artPacks.map(pack=>[pack.id,pack.id==='rina-astromeda-v1'?defaultPetProfile:{
  ...defaultPetProfile,id:pack.id,
  states:Object.fromEntries(Object.entries(defaultPetProfile.states).map(([state,view])=>
    [state,{...view,image:`/assets/rina/${pack.folder}/${state==='talk'||state==='sleep'?state:'idle'}.png`,imageAlt:pack.label}])) as PetProfile['states'],
}])) as Record<ArtPackId,PetProfile>;
export function profileForArt(id:ArtPackId):PetProfile {return profiles[id];}
export function imageForArt(id:ArtPackId,state:PetState,dragging:boolean):string {
  if(dragging&&id!=='rina-astromeda-v1')return `/assets/rina/${artPacks.find(pack=>pack.id===id)!.folder}/drag.png`;
  return profileForArt(id).states[state].image;
}
