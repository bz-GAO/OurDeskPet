import {useEffect,useRef} from 'react';
import type {TeleportPhase} from '../pet/usePetTeleport';
import {EFFECT_PRESETS,type EffectPreset} from '../pet/motionParticles';

export type TeleportEffectStyle='scanline'|'quantum';
// Keep both renderers code-complete. A future setting may expose this choice.
export const ACTIVE_TELEPORT_EFFECT:TeleportEffectStyle='quantum';

const random=(seed:number)=>{const x=Math.sin(seed*127.1+311.7)*43758.5453;return x-Math.floor(x);};

function LegacyScanlineEffect({phase}:{phase:TeleportPhase}){
  if(phase!=='out'&&phase!=='in')return null;
  return <span className="pet-teleport-fx pet-teleport-fx-legacy" key={phase} aria-hidden="true">
    <span className="pet-scan-line"/>
    {Array.from({length:30},(_,i)=><i key={i} style={{left:`${12+(i*37)%76}%`,animationDelay:`${(i%10)*45}ms`,width:2+i%3,height:2+i%3}}/>)}
  </span>;
}

function QuantumFragmentEffect({phase,src,preset}:{phase:TeleportPhase;src:string;preset:EffectPreset}){
  const canvas=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{
    if(phase!=='out'&&phase!=='in')return;
    const target=canvas.current;if(!target)return;
    const context=target.getContext('2d');if(!context)return;
    let disposed=false,frame=0;const started=performance.now(),image=new Image();
    const {colors:palette,highlight}=EFFECT_PRESETS[preset];
    image.onload=()=>{
      const mask=document.createElement('canvas');mask.width=158;mask.height=158;
      const draw=mask.getContext('2d',{willReadFrequently:true});if(!draw)return;
      const scale=Math.min(158/image.naturalWidth,158/image.naturalHeight);
      const width=image.naturalWidth*scale,height=image.naturalHeight*scale;
      draw.drawImage(image,(158-width)/2,158-height,width,height);
      const alpha=draw.getImageData(0,0,158,158).data;
      const paint=(now:number)=>{
        if(disposed)return;
        const progress=Math.min(1,(now-started)/600),scan=158*(1-progress);
        context.clearRect(0,0,158,158);
        context.save();context.globalCompositeOperation='source-over';
        for(let y=0;y<158;y+=4)for(let x=0;x<158;x+=4){
          if(alpha[((Math.min(157,y+2)*158+Math.min(157,x+2))*4)+3]<24)continue;
          const seed=x+y*158,band=Math.abs(y-scan);
          if(band>28||random(seed+18)>.48)continue;
          const distance=1-band/28,travel=(phase==='out'?progress:1-progress);
          const dx=(random(seed+3)-.5)*46*travel,dy=(random(seed+8)-.65)*38*travel;
          const pick=random(seed+19),size=Math.round(pick<.6?2+random(seed+22)*2:pick<.9?5+random(seed+22)*3:9+random(seed+22)*4);
          const color=palette[Math.floor(random(seed+21)*palette.length)];
          const px=Math.round(x+dx),py=Math.round(y+dy);
          context.globalAlpha=Math.min(1,distance*1.35);context.fillStyle=color;context.strokeStyle=color;
          if(pick>.6&&random(seed+23)<.45){context.lineWidth=1;context.strokeRect(px+.5,py+.5,size-1,size-1);}
          else {context.fillRect(px,py,size,size);if(size>=9){context.fillStyle=highlight;context.fillRect(px+1,py+1,size-2,1);}}
        }
        // A segmented one-pixel scan edge keeps the effect crisp at desktop-pet scale.
        context.globalAlpha=.9;
        for(let x=10;x<148;x+=13){context.fillStyle=palette[(x/13)%3|0];context.fillRect(x,Math.round(scan),8,1);}
        context.restore();
        if(progress<1)frame=requestAnimationFrame(paint);
      };
      frame=requestAnimationFrame(paint);
    };
    image.src=src;
    return()=>{disposed=true;cancelAnimationFrame(frame);};
  },[phase,src,preset]);
  if(phase!=='out'&&phase!=='in')return null;
  return <canvas ref={canvas} className="pet-teleport-fx pet-quantum-fx" width="158" height="158" aria-hidden="true"/>;
}

export function PetTeleportEffect({phase,src,preset='quantum'}:{phase:TeleportPhase;src:string;preset?:EffectPreset}){
  return ACTIVE_TELEPORT_EFFECT==='quantum'
    ?<QuantumFragmentEffect phase={phase} src={src} preset={preset}/>
    :<LegacyScanlineEffect phase={phase}/>;
}
