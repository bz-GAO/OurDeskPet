import type {DialogueMessage,ChatMessagePayload,ImagePayload} from './types';

/** Keep complete recent turns; never silently truncate the user's newest request. */
export function buildContext(history:DialogueMessage[],latest:DialogueMessage,budget=24000){
 if(latest.content.length>budget)throw new Error(`这条消息超过当前 ${budget} 字符的上下文预算，请缩短后发送。`);
 const turns:ChatMessagePayload[][]=[];
 for(const m of history){
  if(m.id==='initial-assistant'||!m.content.trim())continue;
  if(m.role==='user')turns.push([{role:'user',content:m.content}]);
  else if(m.state==='complete'&&turns.length)turns[turns.length-1].push({role:'assistant',content:m.content});
 }
 let used=latest.content.length;const kept:ChatMessagePayload[][]=[];
 for(let i=turns.length-1;i>=0;i--){const size=turns[i].reduce((n,m)=>n+m.content.length,0);if(used+size>budget)break;kept.unshift(turns[i]);used+=size;}
 return {messages:[...kept.flat(),{role:'user' as const,content:latest.content}],omitted:turns.length-kept.length};
}

export function validateImages(images:ImagePayload[]){
 if(images.length>4)throw new Error('每次最多附加 4 张图片。');
 for(const image of images){
  if(!['image/png','image/jpeg'].includes(image.mimeType)||!image.dataUrl.startsWith(`data:${image.mimeType};base64,`))throw new Error('仅支持 PNG/JPEG 图片。');
  if((image.byteSize??0)>5*1024*1024||image.dataUrl.length>7*1024*1024)throw new Error('单张图片请控制在 5 MiB 以内。');
  if((image.width??0)>8192||(image.height??0)>8192)throw new Error('图片边长请控制在 8192 像素以内。');
 }
}
