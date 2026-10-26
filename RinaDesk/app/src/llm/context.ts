import {isStoredImage} from './imageStore';
import type {ImagePayload,ParsedFilePayload} from './types';

export const MAX_TURN_ATTACHMENTS=8;

export function validateImages(images:ImagePayload[]){
 if(images.length>MAX_TURN_ATTACHMENTS)throw new Error('一次性文件上传太多了哦');
 for(const image of images){
  if(!['image/png','image/jpeg'].includes(image.mimeType)||(!isStoredImage(image)&&!image.dataUrl.startsWith(`data:${image.mimeType};base64,`)))throw new Error('仅支持 PNG/JPEG 图片。');
  if((image.byteSize??0)>5*1024*1024||image.dataUrl.length>7*1024*1024)throw new Error('单张图片请控制在 5 MiB 以内。');
  if((image.width??0)>8192||(image.height??0)>8192)throw new Error('图片边长请控制在 8192 像素以内。');
 }
}

export function validateAttachmentCount(images:ImagePayload[],files:ParsedFilePayload[]){
 if(images.length+files.length>MAX_TURN_ATTACHMENTS)throw new Error('一次性文件上传太多了哦');
}
