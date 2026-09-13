import {PreviewRail} from './PreviewRail';
import {useState} from 'react';
import {artPacks,imageForArt,type ArtPackId} from '../pet/art/artPacks';
import {useArtPack} from '../pet/art/useArtPack';

export function ArtPicker(){
 const art=useArtPack();
 const [choice,setChoice]=useState<ArtPackId>(art.id);
 const pack=artPacks.find(p=>p.id===choice)!;
 return <div className="art-picker">
  <p className="settings-note">先选择方案查看效果，确认后再启用。</p>
  <div className="art-picker-layout">
   <nav className="art-catalog" aria-label="美术方案">
    {artPacks.map(p=><button key={p.id} type="button" aria-pressed={choice===p.id} onClick={()=>setChoice(p.id)}><strong>{p.label}</strong><span>{p.code}{art.id===p.id?' · 使用中':''}</span></button>)}
   </nav>
   <section className="art-detail" aria-label="所选方案预览">
    <div className="art-detail-heading"><h2>{pack.label}</h2><span>{art.id===choice?'当前使用':'预览中'}</span></div>
    <PreviewRail key={choice}>
     <figure><img src={imageForArt(choice,'idle',false)} alt={`${pack.label}待机效果`}/><figcaption>待机</figcaption></figure>
     <figure><img src={imageForArt(choice,'idle',true)} alt={`${pack.label}拖动效果`}/><figcaption>拖动{choice==='rina-astromeda-v1'?' · 通用图':''}</figcaption></figure>
     <figure><img src={imageForArt(choice,'talk',false)} alt={`${pack.label}说话效果`}/><figcaption>说话</figcaption></figure>
     <figure><img src={imageForArt(choice,'sleep',false)} alt={`${pack.label}睡眠效果`}/><figcaption>睡眠</figcaption></figure>
     <figure><img src={pack.notificationBoard} alt={`${pack.label}电子通知板效果`}/><figcaption>通知板</figcaption></figure>
    </PreviewRail>
    <div className="art-enable-row"><span>仅预览不会更改当前外观</span><button type="button" className="art-enable" disabled={art.id===choice} onClick={()=>art.select(choice)}>{art.id===choice?'已启用':'启用此方案'}</button></div>
   </section>
  </div>
 </div>;
}
