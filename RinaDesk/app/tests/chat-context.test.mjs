import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.chat-context-test-'));
try{
 const file=path.join(temp,'context.mjs');await build({entryPoints:['src/llm/context.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {validateAttachmentCount,validateImages}=await import(pathToFileURL(file));
 assert.throws(()=>validateImages(Array(9).fill({mimeType:'image/png',dataUrl:'data:image/png;base64,AA=='})));
 assert.throws(()=>validateAttachmentCount(Array(5).fill({mimeType:'image/png',dataUrl:'data:image/png;base64,AA=='}),Array(4).fill({})));
 assert.throws(()=>validateImages([{mimeType:'image/png',dataUrl:'https://example.com/p.png'}]));
 assert.throws(()=>validateImages([{mimeType:'image/png',dataUrl:'data:image/png;base64,AA==',byteSize:6*1024*1024}]));
 console.log('PASS image and combined attachment limits');
}finally{await rm(temp,{recursive:true,force:true});}
