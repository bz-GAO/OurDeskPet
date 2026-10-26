import {PreviewRail} from './PreviewRail';
import {useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {effectsForArt,imageForArt,type ArtImages,type ArtPack} from '../pet/art/artPacks';
import {useArtPack} from '../pet/art/useArtPack';
import {currentTheme,selectTheme,type RinaTheme} from '../theme';
import {useConfirmDialog} from './ConfirmDialog';
import {SettingsDisclosure} from './SettingsDisclosure';
import {AdvancedEffects} from './AdvancedEffects';
import {ArtStatePreview} from './ArtStatePreview';
import {useEffectPreset} from '../pet/useEffectPreset';
import {VoiceSfxSettings} from '../voice/VoiceSfxSettings';

type Slot=keyof ArtImages;
const slots:Array<[Slot,string]>=[['idle','待机'],['drag','拖动'],['talk','说话'],['sleep','睡眠']];
const blank=():ArtImages=>({idle:'',drag:'',talk:'',sleep:''});

export function ArtPicker({onDirtyChange}:{onDirtyChange?:(dirty:boolean)=>void}){
 const {confirm,dialog}=useConfirmDialog();
 const art=useArtPack();
 const {preset}=useEffectPreset();
 const [theme,setTheme]=useState<RinaTheme>(()=>currentTheme());
 const [choice,setChoice]=useState(art.id),[editing,setEditing]=useState(false),[editId,setEditId]=useState<string|undefined>();
 const [renaming,setRenaming]=useState(false),[renameDraft,setRenameDraft]=useState('');
 const [name,setName]=useState(''),[images,setImages]=useState<ArtImages>(blank),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const files=useRef<Partial<Record<Slot,HTMLInputElement|null>>>({});
 useEffect(()=>{setChoice(art.id);},[art.id]);
 useEffect(()=>{onDirtyChange?.(editing||renaming);},[editing,renaming,onDirtyChange]);
 useEffect(()=>{if(!art.packs.some(item=>item.id===choice))setChoice(art.id);},[art.id,art.packs,choice]);
 const pack=art.packs.find(p=>p.id===choice)??art.packs[0];
 const previewEffects=effectsForArt(choice,art.packs);
 function startNew(){setEditId(undefined);setName('');setImages(blank());setError('');setEditing(true);}
 function startEdit(value:ArtPack){setEditId(value.id);setName(value.label);setImages(value.images??blank());setError('');setEditing(true);}
 function choose(slot:Slot,file?:File){
  if(!file)return;if(file.size>5*1024*1024){setError('每张图片需小于 5 MB。');return;}
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){setError('仅支持 PNG、JPEG 或 WebP。');return;}
  const reader=new FileReader();reader.onload=()=>{if(typeof reader.result==='string'){setImages(value=>({...value,[slot]:reader.result as string}));setError('');}};reader.onerror=()=>setError('无法读取这张图片。');reader.readAsDataURL(file);
 }
 async function save(){
  if(!name.trim()||slots.some(([slot])=>!images[slot])){setError('填写名称并选择四张人物图片。');return;}
  setBusy(true);setError('');
  try{
   if(!isTauri())throw new Error('桌面程序内才可保存人物方案。');
   const saved=await invoke<ArtPack>('art_custom_save',{request:{id:editId??null,label:name,images}});
   const next=await art.reload();setChoice(saved.id);setEditing(false);
   if(!next.some(item=>item.id===saved.id))setError('方案已保存，请重新打开设置查看。');
  }catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function rename(){
  const label=renameDraft.trim();if(!label){setError('方案名称不能为空。');return;}
  setBusy(true);setError('');
  try{await invoke('art_custom_rename',{id:pack.id,label});await art.reload();setRenaming(false);}catch(e){setError(String(e));}finally{setBusy(false);}
 }
 async function remove(){
  if(!pack.custom||!await confirm(`删除“${pack.label}”？`))return;
  setBusy(true);setError('');
  try{if(art.id===pack.id)art.select('rina-winter-v1');await invoke('art_custom_delete',{id:pack.id});const next=await art.reload();setChoice(next[0]?.id??'rina-winter-v1');}catch(e){setError(String(e));}finally{setBusy(false);}
 }
 function chooseTheme(value:RinaTheme){selectTheme(value);setTheme(value);}
 if(editing)return <div className="art-picker art-custom-editor">
  {dialog}
  <div className="art-detail-heading"><h2>{editId?'编辑人物方案':'新增人物方案'}</h2><button type="button" className="art-inline-action" onClick={async()=>{if(await confirm('放弃当前人物方案草稿？'))setEditing(false);}} disabled={busy}>返回</button></div>
  <label className="art-name">方案名称<input maxLength={40} value={name} onChange={event=>setName(event.target.value)} placeholder="例如：璃奈 · 自定义" disabled={busy}/></label>
  <div className="art-upload-grid">{slots.map(([slot,label])=><button type="button" key={slot} className="art-upload" onClick={()=>files.current[slot]?.click()} disabled={busy}>
   {images[slot]?<img src={images[slot]} alt={`${label}预览`}/>:<span aria-hidden="true">＋</span>}<strong>{label}</strong>
   <input ref={node=>{files.current[slot]=node;}} onClick={event=>event.stopPropagation()} tabIndex={-1} type="file" accept="image/png,image/jpeg,image/webp" onChange={event=>{choose(slot,event.target.files?.[0]);event.target.value='';}}/>
  </button>)}</div>
  {error&&<p className="settings-error" role="alert">{error}</p>}
  <div className="art-enable-row"><button type="button" className="art-enable" onClick={()=>void save()} disabled={busy}>{busy?'保存中…':'保存方案'}</button></div>
 </div>;
 return <div className="art-picker">
  {dialog}
  <SettingsDisclosure title="人物" defaultOpen><div className="art-picker-layout">
   <nav className="art-catalog" aria-label="人物方案">
    {art.packs.map(p=><button key={p.id} type="button" aria-pressed={choice===p.id} onClick={()=>{setChoice(p.id);setRenaming(false);}}><strong>{p.label}</strong><span>{p.code}{art.id===p.id?' · 使用中':''}</span></button>)}
    <button className="art-add" type="button" onClick={startNew}><strong>＋ 新增方案</strong><span>仅替换人物图</span></button>
   </nav>
   <section className="art-detail" aria-label="所选方案预览">
    <div className="art-detail-heading">{renaming?<input className="art-rename-input" aria-label="重命名人物方案" autoFocus maxLength={40} value={renameDraft} onChange={event=>setRenameDraft(event.target.value)} onKeyDown={event=>{if(event.key==='Enter')void rename();if(event.key==='Escape')setRenaming(false);}}/>:<h2>{pack.label}</h2>}<div className="art-heading-actions">{pack.custom&&!renaming?<button className="art-icon-action" type="button" aria-label={`重命名 ${pack.label}`} title="重命名" onClick={()=>{setRenameDraft(pack.label);setRenaming(true);}}>✎</button>:null}{renaming?<><button className="art-inline-action" type="button" disabled={busy} onClick={()=>void rename()}>确定</button><button className="art-inline-action" type="button" disabled={busy} onClick={()=>setRenaming(false)}>取消</button></>:<span>{art.id===choice?'当前使用':'预览中'}</span>}</div></div>
    <PreviewRail key={choice}>
     <figure aria-label={`${pack.label}待机效果`}><ArtStatePreview src={imageForArt(choice,'idle',false,art.packs)} state="idle" effects={previewEffects} preset={preset}/><figcaption>待机</figcaption></figure>
     <figure aria-label={`${pack.label}拖动效果`}><ArtStatePreview src={imageForArt(choice,'idle',true,art.packs)} state="drag" effects={previewEffects} preset={preset}/><figcaption>拖动{choice==='rina-astromeda-v1'?' · 通用图':''}</figcaption></figure>
     <figure aria-label={`${pack.label}说话效果`}><ArtStatePreview src={imageForArt(choice,'talk',false,art.packs)} state="talk" effects={previewEffects} preset={preset}/><figcaption>说话</figcaption></figure>
     <figure aria-label={`${pack.label}睡眠效果`}><ArtStatePreview src={imageForArt(choice,'sleep',false,art.packs)} state="sleep" effects={previewEffects} preset={preset}/><figcaption>睡眠</figcaption></figure>
     <figure><img src={pack.notificationBoard} alt="固定璃奈板"/><figcaption>璃奈板 · 固定</figcaption></figure>
    </PreviewRail>
    {error&&<p className="settings-error" role="alert">{error}</p>}
    <div className="art-enable-row">{pack.custom?<><button type="button" className="art-inline-action" onClick={()=>startEdit(pack)}>更换人物图</button><button type="button" className="art-inline-action art-delete-action" onClick={()=>void remove()}>删除</button></>:null}<button type="button" className="art-enable" disabled={art.id===choice} onClick={()=>art.select(choice)}>{art.id===choice?'已启用':'启用此方案'}</button></div>
   </section>
  </div></SettingsDisclosure>
  <SettingsDisclosure title="主题"><section className="art-theme-panel" aria-label="界面主题"><div className="art-theme-options">
   <button type="button" aria-pressed={theme==='paper'} onClick={()=>chooseTheme('paper')}><span className="art-theme-swatches" data-theme="paper"><i/><i/></span><strong>纸白灰</strong></button>
   <button type="button" aria-pressed={theme==='rose'} onClick={()=>chooseTheme('rose')}><span className="art-theme-swatches" data-theme="rose"><i/><i/></span><strong>粉色</strong></button>
  </div><p className="settings-note">璃奈板固定。</p></section></SettingsDisclosure>
  <SettingsDisclosure title="高级特效"><AdvancedEffects src={imageForArt(choice,'idle',false,art.packs)} artEffects={previewEffects}/></SettingsDisclosure>
  <SettingsDisclosure title="音效" defaultOpen className="art-sfx-section"><VoiceSfxSettings/></SettingsDisclosure>
 </div>;
}
