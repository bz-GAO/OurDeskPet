import {useEffect,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {displayConfigPath} from '../../components/displayConfigPath';
import {watchYakiJob} from './yakiJobWatch';
import {RinaYakiSettings,type YakiSettings} from './RinaYakiSettings';
import './RinaYakiPage.css';

export type RinaYakiToolCapability={id:'video'|'live';name:string;available:boolean;embeddedReady:boolean};
export type RinaYakiStatus={id:string;connected:boolean;available:boolean;embeddedReady:boolean;path:string|null;version:string|null;tools:RinaYakiToolCapability[]};
type VideoPreview={kind:'web'|'local';source:string;title:string;duration:number;thumbnail:string|null;acquisition:{session?:'anonymous'|'app';quality:string}|null;qualities:{id:string;label:string}[]};
type Sample={start_ms:number;length_ms:number;text:string;translation?:string};
type Job={job:string;projectName:string;source:{source:string;title:string;source_language?:string;target_language?:string};state:{status:string;stage?:string;phase?:string;completed?:number;total?:number;error?:string;provider_status?:string};prepared?:{key:string;speakers:Record<string,Sample>};styles?:Record<string,{color:string;font:string}>};
type ProjectScan={directory:string;canCreate:boolean;jobs:Job[]};
type StyleOptions={defaultFont:string;fonts:{label:string;value:string}[];presets:{label:string;value:string}[]};
type Screen='input'|'projects'|'project'|'progress'|'style'|'complete';
const stages=[['download','读取视频'],['audio','提取音频'],['asr','识别语音'],['translation','翻译字幕'],['refinement','校对字幕'],['export_and_mux','生成成片']] as const;
const sourceLanguages=[['auto','自动识别'],['zh','中文'],['en','English'],['ja','日本語']];
const targetLanguages=[['zh-Hans','简体中文'],['en','English'],['ja','日本語']];
async function yaki<T>(action:string,request:Record<string,unknown>={}):Promise<T>{return invoke<T>('extension_yaki_action',{action,request});}

export default function RinaYakiPage({tool,busy,onLaunch,onRelocate}:{tool:RinaYakiStatus;busy:boolean;onLaunch:()=>void;onRelocate:()=>void}){
 const [panel,setPanel]=useState<'work'|'settings'>('work');
 const [screen,setScreen]=useState<Screen>('input');
 const [working,setWorking]=useState(false);
 const [videoInput,setVideoInput]=useState('');
 const [video,setVideo]=useState<VideoPreview|null>(null);
 const [quality,setQuality]=useState('auto');
 const [jobs,setJobs]=useState<Job[]>([]);
 const [job,setJob]=useState<Job|null>(null);
 const [parent,setParent]=useState('');
 const [name,setName]=useState('');
 const [sourceLanguage,setSourceLanguage]=useState('auto');
 const [targetLanguage,setTargetLanguage]=useState('zh-Hans');
 const [speakerCount,setSpeakerCount]=useState('auto');
 const [styles,setStyles]=useState<Record<string,{color:string;font:string}>>({});
 const [speaker,setSpeaker]=useState('');
 const [sampleAudio,setSampleAudio]=useState('');
 const [styleOptions,setStyleOptions]=useState<StyleOptions|null>(null);
 const [preview,setPreview]=useState<{key:string;image:string;error:string}|null>(null);
 const defaultStyle={color:'#000000',font:styleOptions?.defaultFont??''};
 const [error,setError]=useState('');
 const [coverFailed,setCoverFailed]=useState(false);
 const [canCreateInParent,setCanCreateInParent]=useState(true);
 useEffect(()=>{let alive=true;void yaki<{settings:YakiSettings}>('settings').then(result=>{if(alive&&result.settings.defaultProjectDir)setParent(previous=>previous||result.settings.defaultProjectDir);}).catch(()=>{});return()=>{alive=false;};},[]);
 useEffect(()=>{let alive=true;setStyleOptions(null);void yaki<StyleOptions>('style_options').then(value=>{if(alive)setStyleOptions(value);}).catch(()=>{if(alive)setError('字幕样式接口不可用，请更新 RinaYaki。');});return()=>{alive=false;};},[tool.path]);
 useEffect(()=>{if(!job||screen!=='progress')return;let alive=true;
  const poll=()=>{void yaki<Job>('status',{job:job.job}).then(next=>{if(alive)setJob(next);}).catch(e=>{if(alive)setError(String(e));});};
  poll();const timer=window.setInterval(poll,2000);return()=>{alive=false;window.clearInterval(timer);};
 },[job?.job,screen]);
 useEffect(()=>{if(screen==='progress'&&job?.state.status==='complete'){
  setVideo(null);setVideoInput('');setJobs([]);setScreen('complete');
 }},[job?.state.status,screen]);
 function resetToInput(){setVideo(null);setVideoInput('');setJobs([]);setJob(null);setName('');setError('');setScreen('input');}
 function leaveProjectFolder(){setParent('');setJobs([]);setError('');setCanCreateInParent(true);setScreen('input');}
 function resumeJob(item:Job){setJob(item);if(item.state.status!=='complete')watchYakiJob(item.job);setScreen('progress');}
 async function previewVideo(value=videoInput){
  if(!value.trim())return;
  setWorking(true);setError('');setVideo(null);setCoverFailed(false);
  try{const next=await yaki<VideoPreview>('video_preview',{value});setVideo(next);setQuality('auto');setScreen('project');
   const found=parent?await yaki<ProjectScan>('scan',{parent,source:next.source}):await yaki<{jobs:Job[]}>('jobs',{source:next.source});setJobs(found.jobs.filter(item=>item.state.status!=='complete').reverse());
  }catch(e){setError(String(e));setScreen('input');}finally{setWorking(false);}
 }
 async function openLogin(){
  const value=video?.kind==='web'?video.source:videoInput;
  if(!value.trim())return;
  setWorking(true);setError('');
  try{await yaki('web_session_open',{value});}
  catch(e){setError(String(e));}
  finally{setWorking(false);}
 }
 async function selectVideo(){
  setError('');try{const value=await invoke<string|null>('extension_select_video');if(value){setVideoInput(value);void previewVideo(value);}}catch(e){setError(String(e));}
 }
 async function chooseParent(showProjects=false){
  setError('');try{const value=await invoke<string|null>('extension_select_destination');if(value){
   setWorking(true);const found=await yaki<ProjectScan>('scan',{parent:value,...(!showProjects&&video?{source:video.source}:{})});
   if(!showProjects&&!found.canCreate){setError('请选择用于保存项目的上级文件夹，而不是某个项目本身。');return;}
   setParent(found.directory);setCanCreateInParent(found.canCreate);setJobs(showProjects?found.jobs:found.jobs.filter(item=>item.state.status!=='complete').reverse());if(showProjects)setScreen('projects');
  }}catch(e){setError(String(e));}finally{setWorking(false);}
 }
 async function refreshProjects(){
  if(!parent)return;setWorking(true);setError('');try{const found=await yaki<ProjectScan>('scan',{parent});setCanCreateInParent(found.canCreate);setJobs(found.jobs);}catch(e){setError(String(e));}finally{setWorking(false);}
 }
 async function createJob(){
  if(!video)return;setWorking(true);setError('');
  try{const next=await yaki<Job>('create',{video:{kind:video.kind,source:video.source,title:video.title,acquisition:video.acquisition?{...video.acquisition,quality}:null},parent,name,sourceLanguage,targetLanguage,speakerCount:speakerCount==='auto'?null:Number(speakerCount)});watchYakiJob(next.job);setJob(next);setScreen('progress');}
  catch(e){setError(String(e));}finally{setWorking(false);}
 }
 async function retry(){
  if(!job)return;setWorking(true);setError('');
  try{setJob(await yaki<Job>('retry',{job:job.job}));}catch(e){setError(String(e));}finally{setWorking(false);}
 }
 function openStyle(){
  if(!job?.prepared)return;const ids=Object.keys(job.prepared.speakers);
  setStyles(Object.fromEntries(ids.map(id=>[id,job.styles?.[id]??defaultStyle])));setSpeaker(ids[0]??'');setSampleAudio('');setScreen('style');
 }
 async function listen(){
  if(!job||!speaker)return;setWorking(true);setError('');setSampleAudio('');
  try{const result=await yaki<{audio:string}>('sample',{job:job.job,speaker});setSampleAudio(result.audio);}
  catch(e){setError(String(e));}finally{setWorking(false);}
 }
 async function exportJob(){
  if(!job)return;setWorking(true);setError('');
  try{setJob(await yaki<Job>('export',{job:job.job,styles}));setScreen('progress');}
  catch(e){setError(String(e));}finally{setWorking(false);}
 }
 async function openFolder(){
  if(!job)return;try{await yaki('open',{job:job.job});}catch(e){setError(String(e));}
 }
 const shownPath=tool.path?displayConfigPath(tool.path):null;
 const stageIndex=stages.findIndex(([key])=>key===job?.state.stage);
 const state=job?.state.status;
 const selectedSample=job?.prepared?.speakers[speaker];
 const selectedColor=styles[speaker]?.color??'#000000';
 const selectedFont=styles[speaker]?.font??defaultStyle.font;
 const selectedPreset=styleOptions?.presets.find(({value})=>value===selectedColor)?.value??'custom';
 const previewText=Array.from(selectedSample?.translation||selectedSample?.text||'').slice(0,120).join('');
 const previewKey=JSON.stringify([tool.path,job?.job,speaker,previewText,selectedFont,selectedColor]);
 useEffect(()=>{
  if(screen!=='style'||!selectedFont||!/^#?[0-9a-fA-F]{6}$/.test(selectedColor))return;
  let alive=true;
  const timer=window.setTimeout(()=>{void yaki<{image:string}>('style_preview',{text:previewText,font:selectedFont,color:selectedColor}).then(value=>{
   if(!value.image.startsWith('data:image/png;base64,'))throw new Error('预览格式无效');
   if(alive)setPreview({key:previewKey,image:value.image,error:''});
  }).catch(()=>{if(alive)setPreview({key:previewKey,image:'',error:'预览不可用'});});},150);
  return()=>{alive=false;window.clearTimeout(timer);};
 },[screen,previewKey,previewText,selectedFont,selectedColor]);
 return <div className="extensions-tool-page">
  <div className="extensions-title-row"><h2>视频翻译</h2>{shownPath&&<span className="extensions-title-path" title={shownPath}>{shownPath}</span>}<button type="button" className="extensions-title-relocate" disabled={busy} onClick={onRelocate}>重新定位</button><button type="button" className="extensions-title-settings" onClick={()=>setPanel(value=>value==='work'?'settings':'work')}>{panel==='work'?'设置':'返回工作'}</button><button type="button" className="extensions-open-origin" disabled={busy||!tool.available} onClick={onLaunch}>打开 RinaYaki</button></div>
  <div className="extensions-tool-body">
  {panel==='settings'?<RinaYakiSettings onDefaultProjectDir={value=>{if(value&&!job)setParent(value);}}/>:<>
  {error&&<p className="extensions-error" role="alert">{error}</p>}
  {!tool.embeddedReady&&<p className="extensions-hint">此版本缺少板内接口，请更新 RinaYaki。</p>}
  {tool.available&&tool.embeddedReady&&<>
   {(screen==='input'||screen==='project')&&video?.kind!=='local'&&<div className="yaki-login-row"><button type="button" className="yaki-login-button" disabled={working||!videoInput.trim()} onClick={()=>void openLogin()}>登录</button></div>}
   {screen==='input'&&<div className="extensions-video">
    {parent&&<div className="extensions-workspace"><span title={parent}>{displayConfigPath(parent)}</span><button type="button" disabled={working} onClick={()=>setScreen('projects')}>查看项目</button><button type="button" disabled={working} onClick={()=>void chooseParent(true)}>更换</button></div>}
    <form className="extensions-video-input" onSubmit={e=>{e.preventDefault();void previewVideo();}}>
     <input aria-label="视频链接或视频号" placeholder="上传视频链接/视频号/本地视频" value={videoInput} onChange={e=>setVideoInput(e.target.value)} disabled={working}/>
      <button type="button" title="选择本地视频" aria-label="选择本地视频" disabled={working} onClick={()=>void selectVideo()}>📁</button>
      <button type="submit" disabled={working||!videoInput.trim()}>{working?'读取中…':'预览'}</button>
    </form>{!parent&&<button type="button" className="extensions-text-button" disabled={working} onClick={()=>void chooseParent(true)}>{working?'正在读取…':'选择项目文件夹'}</button>}
   </div>}
   {screen==='projects'&&<div className="extensions-flow extensions-project-browser">
    <div className="extensions-workspace"><span title={parent}>{displayConfigPath(parent)}</span><button type="button" disabled={working} onClick={()=>void chooseParent(true)}>更换</button></div>
    <div className="extensions-flow-heading"><strong>文件夹中的项目</strong><span>{jobs.length} 个</span></div>
    {jobs.length>0?<div className="extensions-jobs">{jobs.map(item=><button type="button" key={item.job} onClick={()=>resumeJob(item)}><strong>{item.projectName}</strong><span>{item.state.status==='complete'?'已完成':item.state.status==='awaiting_style'?'等待样式':item.state.status==='failed'?'需要重试':'处理中'}</span></button>)}</div>:<p className="extensions-empty">这个文件夹中还没有 RinaYaki 项目。</p>}
    <div className="extensions-flow-actions"><button type="button" onClick={leaveProjectFolder}>返回</button><button type="button" disabled={working} onClick={()=>void refreshProjects()}>刷新</button>{canCreateInParent&&<button type="button" className="extensions-primary" onClick={()=>{setJobs([]);setScreen('input');}}>在此新建项目</button>}</div>
   </div>}
   {screen==='project'&&video&&<div className="extensions-flow">
    {video.kind==='web'&&<div className="extensions-field"><label htmlFor="yaki-quality">画质</label><select id="yaki-quality" value={quality} disabled={working} onChange={e=>setQuality(e.target.value)}>{video.qualities.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></div>}
    <div className="extensions-preview"><div className="extensions-cover">{video.thumbnail&&!coverFailed?<img src={video.thumbnail} alt="视频封面" onError={()=>setCoverFailed(true)}/>:<span aria-hidden="true">▶</span>}</div><div><strong>{video.title}</strong><span>{Math.floor(video.duration/60)}:{String(Math.floor(video.duration%60)).padStart(2,'0')} · {video.kind==='local'?'本地视频':'在线视频'}</span></div></div>
    <div className="extensions-field"><label htmlFor="yaki-parent">保存位置</label><div className="extensions-inline"><input id="yaki-parent" value={parent} readOnly placeholder="选择项目的上级文件夹"/><button type="button" onClick={()=>void chooseParent()}>📁</button></div></div>
    <div className="extensions-field"><label htmlFor="yaki-name">项目名称</label><input id="yaki-name" value={name} onChange={e=>setName(e.target.value)} placeholder="输入新项目名称"/></div>
    <div className="extensions-languages"><div className="extensions-field"><label htmlFor="yaki-source">输入语言</label><select id="yaki-source" value={sourceLanguage} onChange={e=>setSourceLanguage(e.target.value)}>{sourceLanguages.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div><div className="extensions-field"><label htmlFor="yaki-target">输出语言</label><select id="yaki-target" value={targetLanguage} onChange={e=>setTargetLanguage(e.target.value)}>{targetLanguages.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div></div>
    <div className="extensions-field"><label htmlFor="yaki-speaker-count">说话人数</label><select id="yaki-speaker-count" value={speakerCount} onChange={e=>setSpeakerCount(e.target.value)}><option value="auto">自动识别</option>{Array.from({length:20},(_,index)=><option key={index+1} value={index+1}>{index+1} 人</option>)}</select></div>
    <div className="extensions-flow-actions"><button type="button" onClick={()=>{setVideo(null);setJobs([]);setScreen('input');}}>退出预览</button><button type="button" className="extensions-primary" disabled={working||!canCreateInParent||!parent.trim()||!name.trim()} onClick={()=>void createJob()}>{working?'正在创建…':'开始翻译'}</button></div>
    {jobs.length>0&&<div className="extensions-jobs"><small>未完成的同源项目</small>{jobs.map(item=><button type="button" key={item.job} onClick={()=>resumeJob(item)}><strong>{item.projectName}</strong><span>继续</span></button>)}</div>}
   </div>}
   {screen==='progress'&&job&&<div className="extensions-flow">
    <div className="extensions-flow-heading"><strong>{job.projectName}</strong><span>{state==='complete'?'已完成':state==='awaiting_style'?'等待样式设置':state==='failed'?'任务暂停':state==='new'?'准备启动…':'正在处理…'}</span></div>
    <div className="extensions-progress-list">{stages.filter(([key])=>key!=='export_and_mux'||state==='complete'||job.state.phase==='export'||job.state.stage==='export_and_mux').map(([key,label])=>{const index=stages.findIndex(([item])=>item===key);const isCurrent=stageIndex===index&&state==='running';const done=state==='complete'||(state==='awaiting_style'&&index<5)||(stageIndex>index&&state!=='failed');const measured=key==='download'||key==='translation'||key==='refinement';const percent=done?100:isCurrent&&job.state.total?Math.min(100,Math.max(0,Math.round(100*(job.state.completed??0)/job.state.total))):0;return <div className="extensions-progress-row" key={key}><div><span>{label}</span><span>{done?'完成':isCurrent?(measured&&job.state.total?`${percent}%`:'处理中'):'等待'}</span></div>{measured&&<progress aria-label={label} max="100" value={isCurrent&&!job.state.total?undefined:percent}/>}</div>;})}</div>
    {state==='failed'&&<p className="extensions-error">{job.state.error||'任务失败，请查看项目记录。'}</p>}
    <div className="extensions-flow-actions"><button type="button" onClick={resetToInput}>返回输入</button><button type="button" onClick={()=>void openFolder()}>打开项目文件夹</button>{state==='failed'&&<button type="button" disabled={working} onClick={()=>void retry()}>重试</button>}{state==='awaiting_style'&&<button type="button" className="extensions-primary" disabled={!styleOptions} onClick={openStyle}>继续 · 字幕样式</button>}</div>
   </div>}
   {screen==='complete'&&job&&<div className="extensions-flow extensions-complete">
    <div className="extensions-flow-heading"><strong>翻译完成</strong></div>
    <p>{job.projectName} 已导出。</p><p className="extensions-complete-path" title={job.job}>{displayConfigPath(job.job)}</p>
    <div className="extensions-flow-actions"><button type="button" onClick={resetToInput}>翻译新视频</button><button type="button" className="extensions-primary" onClick={()=>void openFolder()}>打开项目文件夹</button></div>
   </div>}
   {screen==='style'&&job?.prepared&&<div className="extensions-flow">
    <div className="extensions-flow-heading"><strong>字幕样式</strong><span>{Object.keys(job.prepared.speakers).length} 个说话人分组</span></div>
    <div className="extensions-field"><label htmlFor="yaki-speaker">说话人</label><select id="yaki-speaker" value={speaker} onChange={e=>{setSpeaker(e.target.value);setSampleAudio('');}}>{Object.keys(job.prepared.speakers).map((id,index)=><option key={id} value={id}>说话人 {index+1}</option>)}</select></div>
    {selectedSample&&<div className="extensions-sample"><div className="extensions-subtitle-preview" aria-label="字幕预览" aria-busy={preview?.key!==previewKey}>{preview?.key===previewKey&&(preview.image?<img src={preview.image} alt="字幕字体预览"/>:<span role="status">{preview.error}</span>)}</div><button type="button" disabled={working} onClick={()=>void listen()}>试听片段</button>{sampleAudio&&<audio key={sampleAudio} src={sampleAudio} controls autoPlay/>}</div>}
    <div className="extensions-field"><label htmlFor="yaki-font">字体</label><select id="yaki-font" value={selectedFont} onChange={e=>setStyles(previous=>({...previous,[speaker]:{color:previous[speaker]?.color??defaultStyle.color,font:e.target.value}}))}>{styleOptions?.fonts.map(({label,value})=><option key={value} value={value}>{label}</option>)}</select></div>
    <div className="extensions-field"><label htmlFor="yaki-preset">描边颜色</label><select id="yaki-preset" value={selectedPreset} onChange={e=>{if(e.target.value!=='custom')setStyles(previous=>({...previous,[speaker]:{color:e.target.value,font:previous[speaker]?.font??defaultStyle.font}}));}}>{styleOptions?.presets.map(({label,value})=><option key={label} value={value}>{label}</option>)}<option value="custom">自定义</option></select></div>
    <div className="extensions-inline extensions-color"><input aria-label="十六进制描边颜色" value={selectedColor} onChange={e=>setStyles(previous=>({...previous,[speaker]:{color:e.target.value,font:previous[speaker]?.font??defaultStyle.font}}))}/><span style={{background:/^#[0-9a-fA-F]{6}$/.test(selectedColor)?selectedColor:'#000000'}} title={selectedColor}/></div>
    <div className="extensions-flow-actions"><button type="button" onClick={()=>setScreen('progress')}>返回进度</button><button type="button" className="extensions-primary" disabled={working||Object.keys(styles).length!==Object.keys(job.prepared.speakers).length||Object.values(styles).some(item=>!/^#?[0-9a-fA-F]{6}$/.test(item.color))} onClick={()=>void exportJob()}>{working?'正在提交…':'继续 · 导出成片'}</button></div>
   </div>}
  </>}
  </>}
  </div>
 </div>;
}
