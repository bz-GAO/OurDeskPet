import type {ParsedFilePayload} from './types';
import {MAX_TURN_ATTACHMENTS} from './context';
import {fileToCodePayload,isCodeFile} from './codeFileParser';
import {fileToDelimitedPayload,isDelimitedFile} from './delimitedFileParser';
import {fileToTextPayload} from './textFilePayload';
import {fileToWorkPayload,isWorkFile} from './workFileParser';

export async function parseAttachedFile(file:File):Promise<ParsedFilePayload>{
 if(isWorkFile(file.name))return fileToWorkPayload(file);
 if(isDelimitedFile(file.name))return fileToDelimitedPayload(file);
 if(isCodeFile(file.name))return fileToCodePayload(file);
 return fileToTextPayload(file);
}

export function validateParsedFiles(files:ParsedFilePayload[]){
 if(files.length>MAX_TURN_ATTACHMENTS)throw new Error('一次性文件上传太多了哦');
 const encoder=new TextEncoder();
 if(files.some(file=>encoder.encode(file.content).byteLength>8*1024*1024))throw new Error('文件解析结果过大。');
 if(files.some(file=>file.byteSize>8*1024*1024))throw new Error('文件过大。');
 if(files.reduce((sum,file)=>sum+encoder.encode(file.content).byteLength,0)>16*1024*1024)throw new Error('本轮文件内容过多。');
}

const LABELS:Record<ParsedFilePayload['kind'],string>={text:'文本',code:'代码',document:'文档',spreadsheet:'表格'};
export const describeParsedFile=(file:ParsedFilePayload)=>`${file.name} · ${file.kind==='code'&&file.codeMeta?.ast?'代码 AST':LABELS[file.kind]}`;
