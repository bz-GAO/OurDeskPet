import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.delimited-file-parser-test-'));
try{
 const file=path.join(temp,'parser.mjs');await build({entryPoints:['src/llm/delimitedFileParser.ts'],outfile:file,bundle:true,platform:'node',format:'esm'});
 const {parseDelimitedText,fileToDelimitedPayload}=await import(pathToFileURL(file));
 const csv=parseDelimitedText('people.csv','text/csv',64,'name,note\r\n北斋,"第一行\n第二行"\r\n"A, B","说""你好"""');
 assert.equal(csv.kind,'spreadsheet');assert.equal(csv.parser,'delimited-table-v1');
 assert.match(csv.content,/Header \(row 1\) \| A: name \| B: note/);
 assert.match(csv.content,/Row 2 \| name: 北斋 \| note: 第一行 ↵ 第二行/);
 assert.match(csv.content,/Row 3 \| name: A, B \| note: 说"你好"/);
 const tsv=parseDelimitedText('data.tsv','text/tab-separated-values',20,'项目\t值\n甲\t10');
 assert.match(tsv.content,/Row 2 \| 项目: 甲 \| 值: 10/);
 const duplicate=parseDelimitedText('duplicate.csv','',20,'name,name,\nA,B,C');
 assert.match(duplicate.content,/name \(B\)/);assert.match(duplicate.content,/列 C: C/);
 assert.throws(()=>parseDelimitedText('broken.csv','',10,'a,b\n"open,b'),/未闭合/);
 assert.throws(()=>parseDelimitedText('broken.tsv','',10,'a\tb\n"x"oops\ty'),/格式无效/);
 let readOversized=false;
 await assert.rejects(()=>fileToDelimitedPayload({name:'huge.csv',type:'text/csv',size:8*1024*1024+1,arrayBuffer:async()=>{readOversized=true;throw new Error('unexpected read');}}),/文件过大/);
 assert.equal(readOversized,false,'oversized CSV must be rejected before reading it into memory');
 const large='name,note\n'+('item,'+'中'.repeat(512)+'\n').repeat(800);
 const bounded=parseDelimitedText('bounded.csv','text/csv',new TextEncoder().encode(large).length,large);
 assert.match(bounded.content,/已截断/);assert.ok(new TextEncoder().encode(bounded.content).length<=512*1024);
 console.log('PASS CSV/TSV quoted fields, multiline cells, headers and row labels');
}finally{await rm(temp,{recursive:true,force:true});}
