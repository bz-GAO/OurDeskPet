import {build} from 'esbuild';
import {mkdtemp,rm,access} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.art-test-'));
try{
 const file=path.join(temp,'art.mjs');
 await build({entryPoints:['src/pet/art/artPacks.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {artPacks,validArtPack,imageForArt,profileForArt,restEffectForArt}=await import(pathToFileURL(file));
 const uniform=validArtPack(null),original=validArtPack('rina-astromeda-v1');
 assert.equal(validArtPack('obsolete-pack'),uniform);
 assert.equal(validArtPack('rina-uniform-paper-v2'),'rina-alan-pixel-v1');
 assert.deepEqual(artPacks.map(pack=>pack.id),['rina-alan-pixel-v1']);
 assert(!artPacks.some(p=>p.id==='rina-uniform-paper-v2'));
 assert.equal(restEffectForArt('rina-alan-pixel-v1'),'pixel-mask');
 assert.equal(restEffectForArt(uniform),'pixel-mask');
 assert.equal(imageForArt('rina-alan-pixel-v1','sleep',false),'/assets/rina/alan-pixel-v1/sleep.png');
 assert.equal(imageForArt('rina-alan-pixel-v1','sleep',true),'/assets/rina/alan-pixel-v1/sleep.png');
 assert(!JSON.stringify(artPacks).includes('paper-episode06'));
 for(const pack of artPacks)await access(path.join('public',pack.notificationBoard));
 for(const state of ['idle','follow','talk','sleep']){
  const expected='/assets/rina/alan-pixel-v1/'+(state==='sleep'?'sleep':'idle')+'.png';
  assert.equal(imageForArt(original,state,true),expected);
  assert.equal(imageForArt(uniform,state,false),expected);
  assert.equal(imageForArt(uniform,state,true),expected);
  // Release restores the prior state artwork; state data is not mutated by drag rendering.
  const before=profileForArt(uniform).states[state];imageForArt(uniform,state,true);
  assert.equal(profileForArt(uniform).states[state],before);
 }
 for(const image of [imageForArt(original,'idle',false),imageForArt(uniform,'idle',false),imageForArt(uniform,'idle',true)])await access(path.join('public',image));
 for(const pack of artPacks){assert.equal(validArtPack(pack.id),pack.id);for(const state of ['idle','follow','talk','sleep']){for(const dragging of [false,true]){await access(path.join('public',imageForArt(pack.id,state,dragging)));}}}
 console.log('PASS release art: single default pixel pack, legacy fallback and sleep-safe drag');
}finally{await rm(temp,{recursive:true,force:true});}
