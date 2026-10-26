import {useEffect,useMemo,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {displayConfigPath} from '../../components/displayConfigPath';
import {RinaYakiSettings} from './RinaYakiSettings';
import type {RinaYakiStatus,RinaYakiToolCapability} from './RinaYakiPage';
import './RinaYakiPage.css';

type LiveDevice={id:string;name:string};
type GuidancePack={id:string;name:string;version:string;sourceLanguage:string;targetLanguage:string;draft:boolean};
type LiveOptions={translationStreaming?:boolean;devices:LiveDevice[];deviceError:string|null;fonts:string[];colorPresets:{name:string;color:string}[];guidancePacks:GuidancePack[];guidanceErrors:string[]};
const sourceLanguages=[['ja','日本語'],['zh','中文'],['en','English']] as const;
const targetLanguages=[['zh-Hans','简体中文'],['en','English'],['ja','日本語']] as const;
const displayModes=[['source','只显示原文'],['translation','只显示译文'],['bilingual','双语显示']] as const;

async function yaki<T>(action:string,request:Record<string,unknown>={}):Promise<T>{return invoke<T>('extension_yaki_action',{action,request});}

export default function RinaYakiLivePage({tool,capability,busy,onLaunch,onRelocate}:{
 tool:RinaYakiStatus;capability:RinaYakiToolCapability;busy:boolean;
 onLaunch:()=>void;onRelocate:()=>void;
}){
 const [panel,setPanel]=useState<'work'|'settings'>('work');
 const [step,setStep]=useState<1|2>(1);
 const [options,setOptions]=useState<LiveOptions|null>(null);
 const [loading,setLoading]=useState(false);
 const [starting,setStarting]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [sourceType,setSourceType]=useState('local');
 const [device,setDevice]=useState('');
 const [sessionName,setSessionName]=useState('');
 const [recordSession,setRecordSession]=useState(true);
 const [sourceLanguage,setSourceLanguage]=useState('ja');
 const [targetLanguage,setTargetLanguage]=useState('zh-Hans');
 const [displayMode,setDisplayMode]=useState('bilingual');
 const [fontFamily,setFontFamily]=useState('Noto Sans CJK SC Medium');
 const [fontSize,setFontSize]=useState(14);
 const [subtitleColor,setSubtitleColor]=useState('#000000');
 const [previewImage,setPreviewImage]=useState('');
 const [guidancePacks,setGuidancePacks]=useState<string[]>([]);
 const shownPath=tool.path?displayConfigPath(tool.path):null;
 const ready=tool.available&&capability.available&&capability.embeddedReady;

 async function refreshOptions(){
  setLoading(true);setError('');
  try{setOptions(await yaki<LiveOptions>('live_options'));}
  catch(e){setError(String(e));}
  finally{setLoading(false);}
 }
 useEffect(()=>{if(panel==='work'&&ready&&!options)void refreshOptions();},[panel,ready]);
 const compatiblePacks=useMemo(()=>options?.guidancePacks.filter(pack=>pack.sourceLanguage===sourceLanguage&&pack.targetLanguage===targetLanguage)??[],[options,sourceLanguage,targetLanguage]);
 const activePackIds=guidancePacks.filter(id=>compatiblePacks.some(pack=>pack.id===id));
 const previewSource=sourceLanguage==='ja'?'テスト':sourceLanguage==='en'?'Test':'测试';
 const previewTranslation=targetLanguage==='ja'?'テスト':targetLanguage==='en'?'Test':'测试';
 const selectedPreset=options?.colorPresets?.find(item=>item.color.toUpperCase()===subtitleColor.toUpperCase())?.color??'custom';
 const captionShadow=[[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]].map(([x,y])=>`${x}px ${y}px ${subtitleColor}`).join(', ');
 useEffect(()=>{
  if(!ready||step!==2||fontSize<10||fontSize>96||!/^#[0-9a-fA-F]{6}$/.test(subtitleColor))return;
  let active=true;
  setPreviewImage('');
  const timer=window.setTimeout(()=>{
   void yaki<{image:string}>('live_style_preview',{fontFamily,fontSize,subtitleColor,displayMode,sourceLanguage,targetLanguage})
    .then(result=>{if(active)setPreviewImage(result.image);})
    .catch(()=>{if(active)setPreviewImage('');});
  },180);
  return()=>{active=false;window.clearTimeout(timer);};
 },[ready,step,fontFamily,fontSize,subtitleColor,displayMode,sourceLanguage,targetLanguage]);

 async function startLive(){
  setStarting(true);setError('');setNotice('');
  try{
   await yaki('live_start',{sourceType,device:device||null,sessionName,recordSession,sourceLanguage,targetLanguage,displayMode,fontFamily,fontSize,subtitleColor,guidancePacks:displayMode==='source'?[]:activePackIds,allowDraftGuidance:compatiblePacks.some(pack=>pack.draft&&activePackIds.includes(pack.id))});
   setNotice(displayMode==='source'?'实时识别窗口已启动。':options?.translationStreaming?'实时翻译窗口已启动；原文与译文会逐段流式更新。':'实时翻译窗口已启动。');
  }catch(e){setError(String(e));}
  finally{setStarting(false);}
 }
 function togglePack(id:string){setGuidancePacks(previous=>previous.includes(id)?previous.filter(item=>item!==id):[...previous,id]);}

 return <div className="extensions-tool-page">
  <div className="extensions-title-row"><h2>实时翻译</h2>{shownPath&&<span className="extensions-title-path" title={shownPath}>{shownPath}</span>}<button type="button" className="extensions-title-relocate" disabled={busy} onClick={onRelocate}>重新定位</button><button type="button" className="extensions-title-settings" onClick={()=>setPanel(value=>value==='work'?'settings':'work')}>{panel==='work'?'设置':'返回工作'}</button><button type="button" className="extensions-open-origin" disabled={busy||!tool.available} onClick={onLaunch}>打开 RinaYaki</button></div>
  <div className={`extensions-tool-body ${panel==='work'?'extensions-live-tool-body':''}`}>
   {panel==='settings'?<RinaYakiSettings onDefaultProjectDir={()=>{}}/>:<>
    {!capability.embeddedReady&&<p className="extensions-hint">此版本缺少板内实时启动接口，请更新 RinaYaki。</p>}
    {ready&&<div className="extensions-live-shell">
     <div className="extensions-live-scroll">
      <div className="extensions-live-heading"><strong>{step===1?'第 1 步 · 音频与会话':'第 2 步 · 语言与显示'}</strong><span>{step}/2</span></div>
      {step===1?<div className="extensions-live-form">
       <div className="extensions-field"><label htmlFor="live-source-type">来源类型</label><select id="live-source-type" value={sourceType} onChange={e=>setSourceType(e.target.value)}><option value="local">本机音轨</option><option value="stream" disabled>直播音频（暂未开放）</option></select></div>
       <div className="extensions-field"><label htmlFor="live-device">本机播放设备</label><div className="extensions-inline"><select id="live-device" value={device} onChange={e=>setDevice(e.target.value)}><option value="">跟随系统默认输出设备</option>{options?.devices.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" disabled={loading} onClick={()=>void refreshOptions()}>{loading?'读取中…':'刷新'}</button></div></div>
       {options?.deviceError&&<p className="extensions-live-note extensions-error">{options.deviceError}</p>}
       <div className="extensions-field"><label htmlFor="live-stream-address">直播地址</label><input id="live-stream-address" disabled placeholder="接口预留，当前不启用"/></div>
       <div className="extensions-field"><label htmlFor="live-session-name">会话名称</label><input id="live-session-name" value={sessionName} maxLength={120} onChange={e=>setSessionName(e.target.value)} placeholder="可选，用于区分会话记录"/></div>
       <label className="extensions-live-check"><input type="checkbox" checked={recordSession} onChange={e=>setRecordSession(e.target.checked)}/><span>保存有关结果</span></label>
      </div>:<div className="extensions-live-form">
       <div className="extensions-languages"><div className="extensions-field"><label htmlFor="live-source-language">原语言</label><select id="live-source-language" value={sourceLanguage} onChange={e=>setSourceLanguage(e.target.value)}>{sourceLanguages.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div><div className="extensions-field"><label htmlFor="live-target-language">目标语言</label><select id="live-target-language" value={targetLanguage} disabled={displayMode==='source'} onChange={e=>setTargetLanguage(e.target.value)}>{targetLanguages.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div></div>
       <div className="extensions-field"><label htmlFor="live-display-mode">显示内容</label><select id="live-display-mode" value={displayMode} onChange={e=>setDisplayMode(e.target.value)}>{displayModes.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div>
       <fieldset className="extensions-live-guidance" disabled={displayMode==='source'}><legend>翻译指导</legend>{displayMode==='source'?<p>只显示原文时仅调用实时语音识别，不发送翻译请求。</p>:compatiblePacks.length?<>{compatiblePacks.map(pack=><label key={pack.id}><input type="checkbox" checked={activePackIds.includes(pack.id)} onChange={()=>togglePack(pack.id)}/><span>{pack.name} <small>v{pack.version}{pack.draft?' · 草案试用':''}</small></span></label>)}</>:<p>当前语言方向没有可用术语包。</p>}<button type="button" onClick={()=>void yaki('live_guidance_open').catch(e=>setError(String(e)))}>打开指导文件夹</button>{options?.guidanceErrors.map(item=><p className="extensions-error" key={item}>{item}</p>)}</fieldset>
       <div className="extensions-languages"><div className="extensions-field"><label htmlFor="live-font-family">字体</label><select id="live-font-family" value={fontFamily} onChange={e=>setFontFamily(e.target.value)}>{(options?.fonts??['Noto Sans CJK SC Medium']).map(value=><option key={value} value={value}>{value}</option>)}</select></div><div className="extensions-field"><label htmlFor="live-font-size">字号（pt）</label><input id="live-font-size" type="number" min="10" max="96" value={fontSize} onChange={e=>setFontSize(Number(e.target.value))}/></div></div>
       <div className="extensions-field"><label htmlFor="live-color-preset">描边颜色</label><select id="live-color-preset" value={selectedPreset} onChange={e=>{if(e.target.value!=='custom')setSubtitleColor(e.target.value);}}>{options?.colorPresets?.map(item=><option key={item.name} value={item.color}>{item.name}</option>)}<option value="custom">自定义</option></select></div>
       <div className="extensions-field"><label htmlFor="live-subtitle-color">颜色代码</label><div className="extensions-live-color"><input id="live-subtitle-color" value={subtitleColor} onChange={e=>setSubtitleColor(e.target.value)}/><input type="color" aria-label="选择描边颜色" value={/^#[0-9a-fA-F]{6}$/.test(subtitleColor)?subtitleColor:'#000000'} onChange={e=>setSubtitleColor(e.target.value.toUpperCase())}/></div></div>
       <div className="extensions-live-preview" style={{color:'#FFFFFF',textShadow:captionShadow,fontFamily,fontSize:`${Math.min(28,Math.max(10,fontSize))}px`}}>{previewImage?<img src={previewImage} alt="字幕预览"/>:<>{displayMode!=='translation'&&<span>{previewSource}</span>}{displayMode==='bilingual'&&<span className="extensions-live-preview-divider"> / </span>}{displayMode!=='source'&&<strong>{previewTranslation}</strong>}</>}</div>
      </div>}
     </div>
     <div className="extensions-live-actionbar">
      {error&&<p className="extensions-error" role="alert">{error}</p>}{notice&&<p className="extensions-live-success" role="status">{notice}</p>}
      <div>{step===2&&<button type="button" disabled={starting} onClick={()=>{setStep(1);setError('');setNotice('');}}>返回音频设置</button>}{step===1?<button type="button" className="extensions-primary" disabled={loading} onClick={()=>{setStep(2);setError('');setNotice('');}}>继续 · 语言与显示</button>:<button type="button" className="extensions-primary" disabled={starting||fontSize<10||fontSize>96||!/^#[0-9a-fA-F]{6}$/.test(subtitleColor)} onClick={()=>void startLive()}>{starting?'正在启动…':'开始实时翻译'}</button>}</div>
     </div>
    </div>}
   </>}
  </div>
 </div>;
}
