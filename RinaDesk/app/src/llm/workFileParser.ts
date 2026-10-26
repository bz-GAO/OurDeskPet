import {invoke} from '@tauri-apps/api/core';
import type {ParsedFilePayload} from './types';

const WORK_EXTENSIONS=new Set(['docx','xlsx']);
const MAX_WORK_FILE_BYTES=8*1024*1024;
const extension=(name:string)=>name.includes('.')?name.split('.').pop()!.toLowerCase():'';
export const isWorkFile=(name:string)=>WORK_EXTENSIONS.has(extension(name));

function bytesToBase64(bytes:Uint8Array){let value='';for(let index=0;index<bytes.length;index+=8192)value+=String.fromCharCode(...bytes.subarray(index,index+8192));return btoa(value);}

export async function fileToWorkPayload(file:File):Promise<ParsedFilePayload>{
 if(!isWorkFile(file.name))throw new Error(`${file.name} 不是当前支持的工作文件。`);
 if(file.size===0)throw new Error(`${file.name} 是空文件。`);
 if(file.size>MAX_WORK_FILE_BYTES)throw new Error(`${file.name} 超过 8 MiB；请先缩小文件。`);
 const bytes=new Uint8Array(await file.arrayBuffer());
 try{return await invoke<ParsedFilePayload>('parse_work_file',{request:{name:file.name,mimeType:file.type||'application/octet-stream',byteSize:bytes.byteLength,dataBase64:bytesToBase64(bytes)}});}
 catch(error){throw new Error(`无法解析 ${file.name}：${String(error)}`);}
}
