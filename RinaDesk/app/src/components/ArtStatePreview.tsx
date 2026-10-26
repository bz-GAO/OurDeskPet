import type {ArtEffects} from '../pet/art/artPacks';
import type {EffectPreset} from '../pet/motionParticles';
import {AlanDroneEscort,AlanVisorSpeech} from './AlanPixelEffects';
import {PetDragEffect} from './PetDragEffect';

export function ArtStatePreview({src,state,effects,preset}:{src:string;state:'idle'|'drag'|'talk'|'sleep';effects:ArtEffects;preset:EffectPreset}){
  const dragging=state==='drag';
  return <span className="art-state-demo" data-state={state}>
    <span className="art-state-stage">
      <img className="pet-image" src={src} alt="" draggable={false}/>
      <AlanVisorSpeech active={state==='talk'} enabled={Boolean(effects.talkVisor)}/>
      {dragging&&<PetDragEffect dragging enabled preset={preset} preview/>}
      {dragging&&<AlanDroneEscort active enabled={Boolean(effects.dragDrones)}/>} 
    </span>
  </span>;
}
