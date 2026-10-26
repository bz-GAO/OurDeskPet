// Presentation only: driven by native or pointer drag displacement.
export type MotionParticle={x:number;y:number;vx:number;vy:number;age:number;life:number;size:number;color:string;outline:boolean};
export const MOTION_COLORS=['#76e4ff','#9797ff','#b88bff'] as const;
export type EffectPreset='quantum'|'forest';
export const EFFECT_PRESETS={
  quantum:{colors:MOTION_COLORS,highlight:'#d8faff'},
  forest:{colors:['#165b47','#268567','#61ba82'] as const,highlight:'#b4ebc4'},
};
export function validEffectPreset(value:unknown):EffectPreset{return value==='forest'?'forest':'quantum';}
// Same hues as teleport, with a darker one-pixel rim for light desktops.
export const MOTION_EDGES:Record<string,string>={'#76e4ff':'#289bbd','#9797ff':'#6263bd','#b88bff':'#8655b8','#165b47':'#103d32','#268567':'#18543f','#61ba82':'#32764f'};
export function motionOpacity(age:number,life:number){
  return .95*Math.max(0,Math.min(1,(1-age/life)/.75));
}
export const MAX_MOTION_PARTICLES=84;
export function advanceParticles(particles:MotionParticle[],seconds:number){
  const dt=Math.min(.05,Math.max(0,seconds));
  return particles.filter(p=>{p.age+=dt;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=35*dt;return p.age<p.life;});
}
export function emitMotionParticles(particles:MotionParticle[],dx:number,dy:number,landing=false,random= Math.random,preset:EffectPreset='quantum'){
  if(!Number.isFinite(dx)||!Number.isFinite(dy))return;
  const distance=Math.hypot(dx,dy);
  if(!landing && distance<.75)return;
  // Large jumps are monitor/layout corrections, not a trail across the desktop.
  if(distance>120){particles.length=0;return;}
  if(!landing)for(const p of particles){p.x-=dx;p.y-=dy;}
  const count=landing?20:Math.min(9,Math.max(2,Math.ceil(distance/3.5)));
  const ux=distance?dx/distance:0,uy=distance?dy/distance:0;
  for(let i=0;i<count;i++){
    const r=random(),side=i%2?1:-1;
    // Seed behind the lower body along the just-travelled segment, not around the torso.
    // Existing particles already compensate for window movement; keep extra drift small.
    const lag=10+random()*12,along=random();
    particles.push({x:120+(random()-.5)*(landing?50:24)-ux*lag-dx*along,
      y:landing?190:158+random()*28-uy*lag-dy*along,
      vx:landing?side*(32+random()*58):-ux*(9+random()*11)+(random()-.5)*5,
      vy:landing?-16-random()*48:-uy*(9+random()*11)+(random()-.5)*5,
      age:0,life:landing?.48+random()*.22:.25+random()*.22,size:r<.65?4:r<.9?5:7,
      color:EFFECT_PRESETS[preset].colors[i%3],outline:r>.8});
  }
  if(particles.length>MAX_MOTION_PARTICLES)particles.splice(0,particles.length-MAX_MOTION_PARTICLES);
}
