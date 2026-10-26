import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.code-file-parser-test-'));
try{
 const file=path.join(temp,'parser.mjs');await build({entryPoints:['src/llm/codeFileParser.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {decodeCodeFile,isCodeFile,fileToCodePayload}=await import(pathToFileURL(file));const bytes=text=>new TextEncoder().encode(text);
 const parsed=decodeCodeFile('hello.ts','text/plain',bytes("import x from 'x';\nexport function greet(name:string){ return `你好 ${name}`; }"));
 assert.equal(parsed.kind,'code');assert.equal(parsed.parser,'code-outline-v1');assert.match(parsed.content,/Imports:/);assert.match(parsed.content,/L2: greet/);assert.match(parsed.content,/2 \| export function/);
 assert.equal(isCodeFile('main.rs'),true);assert.equal(isCodeFile('notes.md'),false);
 const bom=bytes('\uFEFFexport function 你好() {}');
 globalThis.window={__TAURI_INTERNALS__:{invoke:async(command,{request})=>{assert.equal(command,'parse_code_file');assert.equal(bytes(request.content).length,request.byteSize);assert.equal(request.content.charCodeAt(0),0xFEFF);return {...parsed,parser:'tree-sitter-ast-v1'};}}};
 assert.equal((await fileToCodePayload({name:'bom.ts',type:'text/plain',size:bom.length,arrayBuffer:async()=>bom.buffer})).parser,'tree-sitter-ast-v1');
 globalThis.window.__TAURI_INTERNALS__.invoke=async()=>{throw new Error('backend unavailable');};
 const overOldLimit=new Uint8Array(600*1024).fill(97);assert.equal((await fileToCodePayload({name:'large.ts',type:'text/plain',size:overOldLimit.length,arrayBuffer:async()=>overOldLimit.buffer})).byteSize,overOldLimit.length);
 await assert.rejects(()=>fileToCodePayload({name:'huge.ts',size:9*1024*1024,arrayBuffer:async()=>{throw new Error('should not read oversized file');}}),/文件过大/);
 assert.equal((await fileToCodePayload({name:'bom.ts',type:'text/plain',size:bom.length,arrayBuffer:async()=>bom.buffer})).parser,'code-outline-v1');
 console.log('PASS code outlines, BOM transport byte counts, expanded size and AST fallback');
}finally{await rm(temp,{recursive:true,force:true});}
