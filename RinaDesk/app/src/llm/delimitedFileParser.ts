import type {ParsedFilePayload} from './types';
import {fileToTextPayload} from './textFilePayload';

const DELIMITED_EXTENSIONS=new Set(['csv','tsv']);
const MAX_COLUMNS=512;
const MAX_CELLS=200_000;
const MAX_OUTPUT_BYTES=512*1024;
const TRUNCATED_NOTE='[解析结果已截断到附件上限]';
const MAX_CELL_CHARS=512;

const extension=(name:string)=>name.includes('.')?name.split('.').pop()!.toLowerCase():'';
export const isDelimitedFile=(name:string)=>DELIMITED_EXTENSIONS.has(extension(name));

function parseRows(name:string,content:string,delimiter:string):string[][]{
 const rows:string[][]=[];let row:string[]=[];let field='';let quoted=false;let afterQuote=false;let cells=0;
 const pushField=()=>{
  if(row.length>=MAX_COLUMNS)throw new Error(`${name} 的列数过多。`);
  row.push(field);field='';afterQuote=false;cells++;
  if(cells>MAX_CELLS)throw new Error(`${name} 的单元格过多。`);
 };
 const pushRow=()=>{pushField();rows.push(row);row=[];};
 for(let index=0;index<content.length;index++){
  const char=content[index];
  if(quoted){
   if(char==='"'){
    if(content[index+1]==='"'){field+='"';index++;}
    else {quoted=false;afterQuote=true;}
   }else field+=char;
   continue;
  }
  if(afterQuote){
   if(char===delimiter){pushField();continue;}
   if(char==='\r'||char==='\n'){
    if(char==='\r'&&content[index+1]==='\n')index++;
    pushRow();continue;
   }
   if(char===' '||(delimiter!=="\t"&&char==='\t'))continue;
   throw new Error(`${name} 的引号字段格式无效。`);
  }
  if(char==='"'){
   if(field.length>0)throw new Error(`${name} 的引号字段格式无效。`);
   quoted=true;continue;
  }
  if(char===delimiter){pushField();continue;}
  if(char==='\r'||char==='\n'){
   if(char==='\r'&&content[index+1]==='\n')index++;
   pushRow();continue;
  }
  field+=char;
 }
 if(quoted)throw new Error(`${name} 存在未闭合的引号字段。`);
 if(afterQuote||field.length>0||row.length>0)pushRow();
 return rows;
}

function columnName(index:number):string{
 let value=index+1;let result='';
 while(value>0){value--;result=String.fromCharCode(65+value%26)+result;value=Math.floor(value/26);}
 return result;
}

function compactCell(value:string):string{
 const normalized=value.replace(/\r\n?|\n/g,' ↵ ').replace(/\t/g,' ↹ ').replace(/\|/g,'\\|').trim();
 return normalized.length<=MAX_CELL_CHARS?normalized:`${normalized.slice(0,MAX_CELL_CHARS)}…[单元格已截断]`;
}

function uniqueHeaders(row:string[],columns:number):string[]{
 const seen=new Map<string,number>();
 return Array.from({length:columns},(_,index)=>{
  const base=compactCell(row[index]??'')||`列 ${columnName(index)}`;
  const count=(seen.get(base)??0)+1;seen.set(base,count);
  return count===1?base:`${base} (${columnName(index)})`;
 });
}

export function parseDelimitedText(name:string,mimeType:string,byteSize:number,content:string):ParsedFilePayload{
 const ext=extension(name);
 if(!DELIMITED_EXTENSIONS.has(ext))throw new Error(`${name} 不是 CSV 或 TSV 文件。`);
 const rows=parseRows(name,content,ext==='tsv'?'\t':',');
 if(rows.length===0||rows.every(row=>row.every(value=>!value.trim())))throw new Error(`${name} 中没有可读取的表格内容。`);
 const columns=rows.reduce((maximum,row)=>Math.max(maximum,row.length),0);
 const headers=uniqueHeaders(rows[0],columns);
 const encoder=new TextEncoder();let used=0;let truncated=false;const output:string[]=[];
 const contentLimit=MAX_OUTPUT_BYTES-encoder.encode(`\n${TRUNCATED_NOTE}`).byteLength;
 const append=(line:string)=>{const bytes=encoder.encode(`${line}\n`).byteLength;if(used+bytes>contentLimit){truncated=true;return false;}output.push(line);used+=bytes;return true;};
 append(`[${ext.toUpperCase()} table · rows: ${rows.length} · columns: ${columns} · row 1 used as header]`);
 const headerWritten=append(`Header (row 1) | ${headers.map((header,index)=>`${columnName(index)}: ${header}`).join(' | ')}`);
 if(headerWritten){
  for(let rowIndex=1;rowIndex<rows.length;rowIndex++){
   const cells=rows[rowIndex].map((value,index)=>`${headers[index]}: ${compactCell(value)}`);
   if(!append(`Row ${rowIndex+1} | ${cells.join(' | ')}`))break;
  }
 }
 if(truncated)output.push(TRUNCATED_NOTE);
 return {name,mimeType:mimeType||`text/${ext}`,byteSize,language:ext,kind:'spreadsheet',parser:'delimited-table-v1',content:output.join('\n')};
}

export async function fileToDelimitedPayload(file:File):Promise<ParsedFilePayload>{
 const decoded=await fileToTextPayload(file);
 return parseDelimitedText(file.name,file.type,decoded.byteSize,decoded.content);
}
