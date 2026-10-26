import type {ImagePayload} from './types';
// One binary resource per attachment, shared by pending and historical messages.
const resources=new Map<string,Blob>();
export const isStoredImage=(image:ImagePayload)=>resources.has(image.dataUrl);
export function storeImage(image:ImagePayload):ImagePayload {
 if(isStoredImage(image))return image;
 const prefix=`data:${image.mimeType};base64,`;
 if(!image.dataUrl.startsWith(prefix))throw new Error('图片资源已失效，请重新附加。');
 const bytes=Uint8Array.from(atob(image.dataUrl.slice(prefix.length)),c=>c.charCodeAt(0));
 if(bytes.length>5*1024*1024)throw new Error('单张图片请控制在 5 MiB 以内。');
 const blob=new Blob([bytes],{type:image.mimeType});const url=URL.createObjectURL(blob);resources.set(url,blob);
 return {...image,dataUrl:url,byteSize:bytes.length};
}
export async function transportImage(image:ImagePayload):Promise<ImagePayload>{
 const blob=resources.get(image.dataUrl);if(!blob)return image;
 const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
 for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
 return {...image,dataUrl:`data:${image.mimeType};base64,${btoa(binary)}`};
}
export function releaseImageResources(images:ImagePayload[]){
 for(const url of new Set(images.map(image=>image.dataUrl))){
  if(resources.delete(url))URL.revokeObjectURL(url);
 }
}
export function releaseImages(){for(const url of resources.keys())URL.revokeObjectURL(url);resources.clear();}
