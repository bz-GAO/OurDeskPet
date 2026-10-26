import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.file-parser-test-'));
try{
 const file=path.join(temp,'parser.mjs');await build({entryPoints:['src/llm/fileParser.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {describeParsedFile,validateParsedFiles}=await import(pathToFileURL(file));
 const parsed={name:'notes.md',mimeType:'text/plain',byteSize:5,language:'markdown',kind:'text',parser:'plain-text-v1',content:'hello'};
 assert.match(describeParsedFile(parsed),/文本/);assert.doesNotThrow(()=>validateParsedFiles(Array(8).fill(parsed)));assert.throws(()=>validateParsedFiles(Array(9).fill(parsed)),/太多/);
 assert.doesNotThrow(()=>validateParsedFiles([{...parsed,byteSize:600*1024,content:'x'.repeat(600*1024)}]));
 assert.throws(()=>validateParsedFiles([{...parsed,name:'large.docx',kind:'document',byteSize:8*1024*1024+1}]),/文件过大/);
 console.log('PASS parsed-file labels, count, content and work-file limits');
}finally{await rm(temp,{recursive:true,force:true});}
