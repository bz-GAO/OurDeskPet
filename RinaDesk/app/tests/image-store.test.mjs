import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.image-store-test-'));
try{
 const file=path.join(temp,'store.mjs');await build({entryPoints:['src/llm/imageStore.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const s=await import(pathToFileURL(file));const original={mimeType:'image/png',dataUrl:'data:image/png;base64,AQIDBA==',name:'test'};
 const stored=s.storeImage(original);assert(stored.dataUrl.startsWith('blob:'));assert.equal(s.storeImage(stored),stored);
 assert.equal((await s.transportImage(stored)).dataUrl,original.dataUrl);assert.equal(stored.byteSize,4);
 s.releaseImages();assert(!s.isStoredImage(stored));assert.throws(()=>s.storeImage(stored));
 console.log('PASS binary attachment reuse, transport roundtrip and release');
}finally{await rm(temp,{recursive:true,force:true});}
