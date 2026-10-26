const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/pet/motionParticles.ts'),'utf8');
const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const mod={exports:{}};new Function('exports','module',output)(mod.exports,mod);
const {emitMotionParticles,advanceParticles,MAX_MOTION_PARTICLES}=mod.exports;
assert.equal(mod.exports.validEffectPreset('forest'),'forest');
assert.equal(mod.exports.validEffectPreset('unknown'),'quantum');
{
  const saved=new Map(), states=[], effects=[], events=new EventTarget();
  let failed=false;
  const storage={getItem:key=>saved.get(key)??null,setItem:(key,value)=>{if(failed)throw Error('full');saved.set(key,value);}};
  const hookSource=fs.readFileSync(path.join(__dirname,'../src/pet/useEffectPreset.ts'),'utf8');
  const hookOutput=ts.transpileModule(hookSource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  const hook={exports:{}};
  const deps={react:{useState:value=>{const i=states.length;states.push(typeof value==='function'?value():value);return[states[i],next=>{states[i]=next;}];},useEffect:fn=>effects.push(fn)},'@tauri-apps/api/core':{isTauri:()=>false},'@tauri-apps/api/event':{},'./motionParticles':mod.exports};
  new Function('exports','require','localStorage','window',hookOutput)(hook.exports,id=>deps[id],storage,events);
  const api=hook.exports.useEffectPreset(),clean=effects[0]();
  api.select('forest');assert.equal(states[0],'forest');assert.equal(hook.exports.currentEffectPreset(),'forest');
  saved.set(hook.exports.EFFECT_STORAGE_KEY,'quantum');events.dispatchEvent(new Event('storage'));assert.equal(states[0],'quantum');
  failed=true;api.select('forest');assert.equal(states[0],'quantum');assert.ok(states[1]);
  clean();
}
for(const preset of ['quantum','forest']){
  const samples=[];emitMotionParticles(samples,12,0,false,()=>.5,preset);
  assert.deepEqual([...new Set(samples.map(p=>p.color))], [...mod.exports.EFFECT_PRESETS[preset].colors]);
  assert.ok(samples.every(p=>mod.exports.MOTION_EDGES[p.color]));
}
assert.equal(mod.exports.motionOpacity(0,1),.95);
assert.equal(mod.exports.motionOpacity(.25,1),.95);
assert.ok(mod.exports.motionOpacity(.6,1)<.95);
assert.equal(mod.exports.motionOpacity(1,1),0);
for(const sample of [.2,.7,.95]){
  const check=[];emitMotionParticles(check,5,0,false,()=>sample);
  assert.ok(check.every(p=>[4,5,7].includes(p.size)));
  assert.ok(check.every(p=>mod.exports.MOTION_EDGES[p.color]));
}
const fixed=()=>.5;
for(const direction of [-1,1]){
  const trail=[];emitMotionParticles(trail,12*direction,0,false,fixed);
  assert.ok(trail.every(p=>p.y>=158&&p.y<=186),'trail starts on lower body');
  assert.ok(trail.every(p=>(p.x-120)*direction<0),'trail is behind travel direction');
  assert.ok(trail.every(p=>p.vx*direction<0),'drift trails rather than radiates');
}
let particles=[];
emitMotionParticles(particles,0,0,false,fixed);assert.equal(particles.length,0);
emitMotionParticles(particles,12,0,false,fixed);assert.equal(particles.length,4);
assert.ok(particles.every(p=>p.vx<0));
const origin=particles[0].x;
emitMotionParticles(particles,4,0,false,fixed);assert.equal(particles[0].x,origin-4);
for(let i=0;i<100;i++)emitMotionParticles(particles,5,2,false,fixed);
assert.ok(particles.length<=MAX_MOTION_PARTICLES);
emitMotionParticles(particles,1000,0,false,fixed);assert.equal(particles.length,0);
emitMotionParticles(particles,NaN,0,false,fixed);assert.equal(particles.length,0);
emitMotionParticles(particles,0,0,true,fixed);assert.equal(particles.length,20);
assert.ok(particles.some(p=>p.vx<0)&&particles.some(p=>p.vx>0));
assert.ok(particles.every(p=>p.vy<0&&p.y===190));
for(let i=0;i<20;i++)particles=advanceParticles(particles,.05);
assert.equal(particles.length,0);
console.log('PASS: stationary suppression, opposite trail, screen compensation, cap, jump/NaN rejection, landing spread and expiration');

// Exercise the React effect against a mocked native event source (no desktop input).
(async()=>{
  const refs=[],effects=[];let slot=0,draws=0,move,scaleChange,unlistened=0;
  const frames=new Map();let nextFrame=0;
  const context={clearRect(){},fillRect(){draws++;},strokeRect(){draws++;},globalAlpha:1};
  const canvas={getContext:()=>context};
  const preference=new EventTarget();preference.matches=false;
  global.window=new EventTarget();window.matchMedia=()=>preference;
  global.document=new EventTarget();document.hidden=false;
  global.requestAnimationFrame=callback=>{frames.set(++nextFrame,callback);return nextFrame;};
  global.cancelAnimationFrame=id=>frames.delete(id);
  const native={scaleFactor:async()=>2,outerPosition:async()=>({x:100,y:100}),
    onScaleChanged:async callback=>{scaleChange=callback;return()=>unlistened++;},
    onMoved:async callback=>{move=callback;return()=>unlistened++;}};
  const react={useRef(value){const index=slot++;return refs[index]??(refs[index]={current:value===null?canvas:value});},
    useEffect(callback,deps){const index=slot++,previous=effects[index];
      if(!previous||deps.some((value,i)=>value!==previous.deps[i]))effects[index]={callback,deps,dirty:true,cleanup:previous?.cleanup};}};
  const module={exports:{}};
  const component=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/components/PetDragEffect.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  new Function('require','module','exports',component)(name=>{
    if(name==='react')return react;
    if(name==='react/jsx-runtime')return {jsx:()=>null};
    if(name==='@tauri-apps/api/core')return {isTauri:()=>true};
    if(name==='@tauri-apps/api/window')return {getCurrentWindow:()=>native};
    if(name==='../pet/motionParticles')return mod.exports;
    throw Error(name);
  },module,module.exports);
  const render=(dragging,enabled=true)=>{slot=0;module.exports.PetDragEffect({dragging,enabled});
    for(const effect of effects.filter(Boolean))if(effect.dirty){effect.cleanup?.();effect.cleanup=effect.callback();effect.dirty=false;}};
  const flush=()=>new Promise(resolve=>setImmediate(resolve));
  const tick=()=>{const pending=[...frames.values()];frames.clear();pending.forEach(callback=>callback(performance.now()+16));};
  render(false);await flush();assert.equal(frames.size,0);
  render(true);move({payload:{x:110,y:100}});tick();assert.ok(draws>0,'first short native move emits');
  assert.ok(refs[1].current.particles.every(p=>p.vx<0));
  render(false);assert.equal(refs[1].current.particles.filter(p=>p.y===190).length,20,'release splash');
  render(true);scaleChange({payload:{scaleFactor:1.5}});assert.equal(refs[1].current.particles.length,0);
  preference.matches=true;preference.dispatchEvent(new Event('change'));assert.equal(frames.size,0);
  move({payload:{x:130,y:100}});move({payload:{x:135,y:100}});assert.equal(frames.size,0);
  preference.matches=false;render(false,false);await flush();
  move({payload:{x:140,y:100}});assert.equal(frames.size,0,'teleport-disabled overlay stays idle');
  for(const effect of effects.filter(Boolean))effect.cleanup?.();
  assert.equal(frames.size,0);assert.equal(unlistened,4);
  console.log('PASS: native initial position, drag/release, DPI cleanup, reduced motion, teleport exclusion and listener teardown');
})().catch(error=>{console.error(error);process.exitCode=1;});
