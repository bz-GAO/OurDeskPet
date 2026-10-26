import {invoke} from '@tauri-apps/api/core';
import type {CodeSymbol,ParsedFilePayload} from './types';
import {decodeTextFile,textFileLanguage} from './textFilePayload';

const CODE_EXTENSIONS=new Set(['ts','tsx','js','jsx','mjs','cjs','py','rs','go','java','kt','c','h','cpp','cc','hpp','cs','swift','rb','php','sh','ps1','bat','cmd','html','css','scss','less','vue','svelte','sql','graphql']);
const AST_EXTENSIONS=new Set(['ts','tsx','js','jsx','mjs','cjs','py','rs']);
const MAX_OUTLINE_ITEMS=80;
const MAX_CONTENT_BYTES=8*1024*1024;

const extension=(name:string)=>name.includes('.')?name.split('.').pop()!.toLowerCase():'';
export const isCodeFile=(name:string)=>CODE_EXTENSIONS.has(extension(name));

function isImport(line:string){return /^\s*(?:import\b|export\s+.+\s+from\b|from\s+\S+\s+import\b|use\b|mod\b|#\s*include\b|using\s+[\w.]+\s*;|(?:const|let|var)\s+\w+\s*=\s*require\s*\()/.test(line);}

function symbolLabel(line:string,language:string):string|null{
 const value=line.trim();
 const patterns:RegExp[] = language==='python'
  ? [/^(?:async\s+)?def\s+([\w_]+)/,/^class\s+([\w_]+)/]
  : language==='rust'
   ? [/^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([\w_]+)/,/^(?:pub\s+)?(?:struct|enum|trait|type|mod)\s+([\w_]+)/,/^impl(?:<[^>]+>)?\s+([^\s{]+)/]
   : [/^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([\w$]+)/,/^(?:export\s+)?(?:default\s+)?(?:class|interface|type|enum|namespace)\s+([\w$]+)/,/^(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[\w$]+)\s*=>/,/^(?:public|private|protected|static|final|abstract|async|synchronized|override|virtual|sealed|partial|extern|unsafe|\s)+[\w<>,?\[\].:]+\s+([\w$]+)\s*\([^;]*\)\s*[{=:]/];
 for(const pattern of patterns){const match=value.match(pattern);if(match)return match[1]??value.slice(0,80);}
 return null;
}

function takeUtf8(value:string,maxBytes:number){
 const encoder=new TextEncoder();if(encoder.encode(value).byteLength<=maxBytes)return value;
 let low=0,high=value.length;while(low<high){const middle=Math.ceil((low+high)/2);if(encoder.encode(value.slice(0,middle)).byteLength<=maxBytes)low=middle;else high=middle-1;}
 return value.slice(0,low);
}

export function decodeCodeFile(name:string,mimeType:string,bytes:Uint8Array):ParsedFilePayload{
 const base=decodeTextFile(name,mimeType,bytes);const language=textFileLanguage(name);const lines=base.content.split(/\r?\n/);const imports:string[]=[];const importSources:string[]=[];const symbols:string[]=[];const symbolMeta:CodeSymbol[]=[];
 for(let index=0;index<lines.length&&(imports.length+symbols.length)<MAX_OUTLINE_ITEMS;index++){
  const line=lines[index];if(isImport(line)){const value=line.trim().slice(0,180);imports.push(`L${index+1}: ${value}`);const match=value.match(/(?:from\s+|require\s*\(|use\s+|import\s+)(?:['"])?([^'";()\s]+)/);if(match)importSources.push(match[1]);continue;}
  const symbol=symbolLabel(line,language);if(symbol){symbols.push(`L${index+1}: ${symbol}`);symbolMeta.push({name:symbol,kind:'symbol',line:index+1});}
 }
 const summary=[`[Code outline · heuristic v1]`,`Language: ${language}`,`Lines: ${lines.length}`,imports.length?`Imports:\n${imports.map(item=>`- ${item}`).join('\n')}`:'Imports: none detected',symbols.length?`Symbols:\n${symbols.map(item=>`- ${item}`).join('\n')}`:'Symbols: none detected','',`[Source · ${name}]`,''].join('\n');
 const numbered=lines.map((line,index)=>`${index+1} | ${line}`).join('\n');const room=MAX_CONTENT_BYTES-new TextEncoder().encode(summary).byteLength-80;
 let source=takeUtf8(numbered,Math.max(0,room));if(source.length<numbered.length)source+='\n[Source truncated to attachment limit]';
 return {...base,kind:'code',parser:'code-outline-v1',language,content:summary+source,codeMeta:{ast:false,syntaxErrors:0,imports:importSources,symbols:symbolMeta}};
}

export async function fileToCodePayload(file:File){
 if(file.size>MAX_CONTENT_BYTES)throw new Error(`${file.name} 文件过大。`);
 const bytes=new Uint8Array(await file.arrayBuffer());const fallback=decodeCodeFile(file.name,file.type,bytes);if(!AST_EXTENSIONS.has(extension(file.name)))return fallback;
 try{return await invoke<ParsedFilePayload>('parse_code_file',{request:{name:file.name,mimeType:file.type||'text/plain',byteSize:bytes.byteLength,content:new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)}});}catch{return fallback;}
}
