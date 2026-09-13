import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.chat-context-test-'));
try{
 const file=path.join(temp,'context.mjs');await build({entryPoints:['src/llm/context.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {buildContext,validateImages}=await import(pathToFileURL(file));
 const m=(role,content,state='complete')=>({id:Math.random().toString(),role,content,state});
 const latest=m('user','new');
 const old=[m('user','old question'),m('assistant','old answer'),m('user','recent'),m('assistant','partial','cancelled')];
 const result=buildContext(old,latest,12);assert.equal(result.omitted,1);assert.deepEqual(result.messages.map(m=>m.content),['recent','new']);
 for(const state of ['error','cancelled','truncated','streaming'])assert.equal(buildContext([m('user','hi'),m('assistant','should not leak',state)],latest).messages.some(m=>m.content==='should not leak'),false);
 assert.throws(()=>buildContext([],m('user','x'.repeat(101)),100));
 assert.throws(()=>validateImages(Array(5).fill({mimeType:'image/png',dataUrl:'data:image/png;base64,AA=='})));
 assert.throws(()=>validateImages([{mimeType:'image/png',dataUrl:'https://example.com/p.png'}]));
 assert.throws(()=>validateImages([{mimeType:'image/png',dataUrl:'data:image/png;base64,AA==',byteSize:6*1024*1024}]));
 console.log('PASS complete-turn context budget, incomplete-reply exclusion, oversized latest input and attachment limits');
}finally{await rm(temp,{recursive:true,force:true});}
