import {build} from 'esbuild';
import {mkdtemp,rm,access} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.art-test-'));
try{
 const file=path.join(temp,'art.mjs');
 await build({entryPoints:['src/pet/art/artPacks.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {artPacks,validArtPack,imageForArt,profileForArt}=await import(pathToFileURL(file));
 const uniform=validArtPack(null),original=validArtPack('rina-astromeda-v1');
 assert.equal(validArtPack('obsolete-pack'),uniform);
 assert.equal(validArtPack('rina-uniform-paper-v2'),'rina-winter-v1');
 assert(!artPacks.some(p=>p.id==='rina-uniform-paper-v2'));
 for(const pack of artPacks)await access(path.join('public',pack.notificationBoard));
 for(const state of ['idle','follow','talk','sleep']){
  assert.equal(imageForArt(original,state,true),'/assets/rina/rina-idle-v1.png');
  assert.equal(imageForArt(uniform,state,false),`/assets/rina/winter-v1/${state==='talk'||state==='sleep'?state:'idle'}.png`);
  assert.equal(imageForArt(uniform,state,true),'/assets/rina/winter-v1/drag.png');
  // Release restores the prior state artwork; state data is not mutated by drag rendering.
  const before=profileForArt(uniform).states[state];imageForArt(uniform,state,true);
  assert.equal(profileForArt(uniform).states[state],before);
 }
 for(const image of [imageForArt(original,'idle',false),imageForArt(uniform,'idle',false),imageForArt(uniform,'idle',true)])await access(path.join('public',image));
 for(const pack of artPacks){assert.equal(validArtPack(pack.id),pack.id);for(const state of ['idle','follow','talk','sleep']){for(const dragging of [false,true]){await access(path.join('public',imageForArt(pack.id,state,dragging)));}}}
 console.log('PASS: original pack, new default, all-state fallback, drag override/release, asset files');
}finally{await rm(temp,{recursive:true,force:true});}
