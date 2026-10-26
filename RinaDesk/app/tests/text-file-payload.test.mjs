import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.text-file-payload-test-'));
try{
 const file=path.join(temp,'payload.mjs');await build({entryPoints:['src/llm/textFilePayload.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {decodeTextFile,textFileLanguage}=await import(pathToFileURL(file));
 const bytes=text=>new TextEncoder().encode(text);
 const mixed=decodeTextFile('dialogue.ts','',bytes('const 挨拶 = "こんにちは";\nconsole.log(挨拶);'));
 assert.equal(mixed.language,'typescript');assert.equal(mixed.kind,'text');assert.match(mixed.content,/こんにちは/);
 assert.equal(textFileLanguage('captions.srt'),'srt');
 const overOldLimit=new Uint8Array(600*1024).fill(97);assert.equal(decodeTextFile('large.txt','text/plain',overOldLimit).byteSize,overOldLimit.length);
 assert.throws(()=>decodeTextFile('report.docx','application/octet-stream',bytes('PK')),/暂不支持/);
 assert.throws(()=>decodeTextFile('binary.bin','',new Uint8Array([0,1,2,3,4,5])),/可读取的文本|UTF-8/);
 // GBK/GB18030 encoded Chinese text falls back past strict UTF-8.
 const gbkBytes=new Uint8Array([0xC4,0xE3,0xBA,0xC3,0xA3,0xAC,0xCA,0xC0,0xBD,0xE7]);
 const gbk=decodeTextFile('notes.txt','',gbkBytes);
 assert.equal(gbk.content,'你好，世界');assert.equal(gbk.parser,'plain-text-gb18030-v1');
 assert.throws(()=>decodeTextFile('unknown.bin','',gbkBytes),/可识别的文本编码/);
 // UTF-16LE BOM is decoded directly.
 const utf16le=new Uint8Array([0xFF,0xFE,0x41,0x00,0x42,0x00]);
 const utf16Payload=decodeTextFile('u16.txt','',utf16le);
 assert.equal(utf16Payload.content,'AB');assert.equal(utf16Payload.parser,'plain-text-utf16-v1');
 assert.equal(decodeTextFile('be.txt','',new Uint8Array([0xFE,0xFF,0x4F,0x60])).content,'你');
 for(const damaged of [[0xFF,0xFE,0x41],[0xFE,0xFF,0xD8,0x00]]){
  assert.throws(()=>decodeTextFile('broken.txt','',new Uint8Array(damaged)),/文本编码无效/);
 }
 console.log('PASS UTF-8 text/mixed-language files, GB18030/UTF-16 fallback, office routing and binary limits');
}finally{await rm(temp,{recursive:true,force:true});}
