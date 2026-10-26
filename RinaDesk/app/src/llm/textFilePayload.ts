import type {ParsedFilePayload} from './types';

const MAX_FILE_BYTES=8*1024*1024;
const OFFICE_OR_BINARY=new Set(['doc','docx','xls','xlsx','xlsm','ppt','pptx','pdf','odt','ods','zip','7z','rar']);
const LANGUAGES:Record<string,string>={
 ts:'typescript',tsx:'tsx',js:'javascript',jsx:'jsx',mjs:'javascript',cjs:'javascript',py:'python',rs:'rust',go:'go',java:'java',kt:'kotlin',
 c:'c',h:'c',cpp:'cpp',cc:'cpp',hpp:'cpp',cs:'csharp',swift:'swift',rb:'ruby',php:'php',sh:'shell',ps1:'powershell',bat:'batch',cmd:'batch',
 html:'html',htm:'html',css:'css',scss:'scss',less:'less',vue:'vue',svelte:'svelte',sql:'sql',graphql:'graphql',
 json:'json',jsonl:'json',yaml:'yaml',yml:'yaml',toml:'toml',xml:'xml',md:'markdown',markdown:'markdown',csv:'csv',tsv:'tsv',txt:'text',log:'text',ini:'ini',env:'dotenv',
};
const LEGACY_TEXT_EXTENSIONS=new Set([...Object.keys(LANGUAGES),'srt','vtt','rst','conf','cfg','properties']);

const extension=(name:string)=>name.includes('.')?name.split('.').pop()!.toLowerCase():'';
export const textFileLanguage=(name:string)=>LANGUAGES[extension(name)]??(extension(name)||'text');

function decodeTextBytes(name:string,mimeType:string,ext:string,bytes:Uint8Array):{content:string;parser:string}{
 const utf16=bytes[0]===0xFF&&bytes[1]===0xFE?'utf-16le':bytes[0]===0xFE&&bytes[1]===0xFF?'utf-16be':null;
 if(utf16){
  try{return{content:new TextDecoder(utf16,{fatal:true}).decode(bytes),parser:'plain-text-utf16-v1'};}
  catch{throw new Error(`${name} 文本编码无效。`);}
 }
 try{return{content:new TextDecoder('utf-8',{fatal:true}).decode(bytes),parser:'plain-text-v1'};}
 catch{}
 const allowLegacy=LEGACY_TEXT_EXTENSIONS.has(ext)||mimeType.toLowerCase().startsWith('text/');
 if(allowLegacy){
  try{return{content:new TextDecoder('gb18030',{fatal:true}).decode(bytes),parser:'plain-text-gb18030-v1'};}
  catch{}
 }
 throw new Error(`${name} 不是可识别的文本编码；当前支持 UTF-8、UTF-16 和文本文件中的 GB18030。`);
}

export function decodeTextFile(name:string,mimeType:string,bytes:Uint8Array):ParsedFilePayload{
 if(!name.trim()||name.length>260)throw new Error('文件名无效。');
 const ext=extension(name);if(OFFICE_OR_BINARY.has(ext))throw new Error(`${name} 暂不支持；当前支持 UTF-8/UTF-16/中文编码文本、代码与 DOCX/XLSX 工作文件。`);
 if(bytes.byteLength===0)throw new Error(`${name} 是空文件。`);
 if(bytes.byteLength>MAX_FILE_BYTES)throw new Error(`${name} 文件过大。`);
 const {content:decoded,parser}=decodeTextBytes(name,mimeType,ext,bytes);
 const content=decoded.replace(/^\uFEFF/,'');
 let controls=0;const maxControls=Math.max(2,content.length/200);
 for(let index=0;index<content.length;index++){
  const code=content.charCodeAt(index);
  if(code<32&&code!==9&&code!==10&&code!==13&&++controls>maxControls)throw new Error(`${name} 看起来不是可读取的文本文件。`);
 }
 if(!content.trim())throw new Error(`${name} 看起来不是可读取的文本文件。`);
 return {name,mimeType:mimeType||'text/plain',byteSize:bytes.byteLength,language:textFileLanguage(name),kind:'text',parser,content};
}

export async function fileToTextPayload(file:File):Promise<ParsedFilePayload>{
 if(file.size>MAX_FILE_BYTES)throw new Error(`${file.name} 文件过大。`);
 return decodeTextFile(file.name,file.type,new Uint8Array(await file.arrayBuffer()));
}
