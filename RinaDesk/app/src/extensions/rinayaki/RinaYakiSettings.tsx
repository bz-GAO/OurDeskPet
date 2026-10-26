import {useEffect,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {GetApiButton} from '../../components/GetApiButton';

export type YakiSettings={hasApiKey:boolean;baseUrl:string;httpApiUrl:string;websocketUrl:string;minimumIntervalSeconds:number;asrModel:string;translationModel:string;refinementModel:string;defaultProjectDir:string;liveEngine:'asr-mt'|'livetranslate'};
type Tab='api'|'models'|'general';
const defaults={
 baseUrl:'https://dashscope.aliyuncs.com/compatible-mode/v1',
 httpApiUrl:'https://dashscope.aliyuncs.com/api/v1',
 websocketUrl:'wss://dashscope.aliyuncs.com/api-ws/v1/inference',
 asrModel:'qwen-audio-3.1-asr-flash-filetrans',translationModel:'qwen-mt-flash',refinementModel:'qwen3.8-flash'
};
async function yaki<T>(action:string,request:Record<string,unknown>={}):Promise<T>{return invoke<T>('extension_yaki_action',{action,request});}

export function RinaYakiSettings({onDefaultProjectDir}:{onDefaultProjectDir:(value:string)=>void}){
 const [tab,setTab]=useState<Tab>('api');
 const [settings,setSettings]=useState<YakiSettings|null>(null);
 const [key,setKey]=useState('');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [message,setMessage]=useState('');
 const [help,setHelp]=useState(false);
 useEffect(()=>{let alive=true;void yaki<{settings:YakiSettings}>('settings').then(result=>{if(alive)setSettings(result.settings);}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[]);
 function change<K extends keyof YakiSettings>(name:K,value:YakiSettings[K]){setSettings(previous=>previous?{...previous,[name]:value}:previous);setMessage('');}
 async function chooseDirectory(){try{const value=await invoke<string|null>('extension_select_destination');if(value)change('defaultProjectDir',value);}catch(e){setError(String(e));}}
 async function save(){if(!settings)return;setBusy(true);setError('');setMessage('');try{
  const result=await yaki<{settings:YakiSettings}>('settings_save',{...settings,apiKey:key.trim()||null});setSettings(result.settings);setKey('');onDefaultProjectDir(result.settings.defaultProjectDir);setMessage('已保存；新项目会使用这套配置。');
 }catch(e){setError(String(e));}finally{setBusy(false);}}
 if(!settings)return <p className="extensions-hint">正在读取 RinaYaki 设置…</p>;
 return <div className="yaki-settings">
  <nav className="yaki-settings-tabs" aria-label="RinaYaki 设置分类">{([['api','API'],['models','模型'],['general','通用']] as const).map(([id,label])=><button type="button" key={id} aria-current={tab===id?'page':undefined} onClick={()=>setTab(id)}>{label}</button>)}</nav>
  {error&&<p className="extensions-error" role="alert">{error}</p>}{message&&<p className="yaki-settings-success" role="status">{message}</p>}
  {tab==='api'&&<div className="yaki-settings-fields">
   <GetApiButton provider="bailian"/>
   <label>服务商<input value="阿里云百炼" readOnly/></label>
   <label>API Key<div className="yaki-setting-inline"><input type="password" autoComplete="new-password" value={key} onChange={event=>setKey(event.target.value)} placeholder={settings.hasApiKey?'已配置；留空保留原密钥':'输入 DASHSCOPE API Key'}/><button type="button" className="yaki-square-button" aria-label="查看 API Key 获取方法" title="获取方法" onClick={()=>setHelp(true)}>?</button></div></label>
   <label>兼容 API 地址<div className="yaki-setting-inline"><input value={settings.baseUrl} onChange={event=>change('baseUrl',event.target.value)}/><button type="button" className="yaki-square-button yaki-fill-button" title="填入阿里云默认地址" aria-label="填入阿里云默认地址" onClick={()=>setSettings({...settings,baseUrl:defaults.baseUrl,httpApiUrl:defaults.httpApiUrl,websocketUrl:defaults.websocketUrl})}>→</button></div></label>
   <label>最小请求间隔（秒）<input type="number" min="0" max="60" step="0.1" value={settings.minimumIntervalSeconds} onChange={event=>change('minimumIntervalSeconds',Number(event.target.value))}/></label>
   <details><summary>高级地址</summary><label>语音 HTTP API<input value={settings.httpApiUrl} onChange={event=>change('httpApiUrl',event.target.value)}/></label><label>实时语音 WebSocket<input value={settings.websocketUrl} onChange={event=>change('websocketUrl',event.target.value)}/></label></details>
  </div>}
  {tab==='models'&&<div className="yaki-settings-fields">
   <label>实时翻译方式<select value={settings.liveEngine??'asr-mt'} onChange={event=>change('liveEngine',event.target.value as YakiSettings['liveEngine'])}><option value="asr-mt">标准（ASR＋MT）</option><option value="livetranslate">LiveTranslate</option></select></label>
   <label>语音识别<div className="yaki-setting-inline"><input value={settings.asrModel} onChange={event=>change('asrModel',event.target.value)}/><button type="button" className="yaki-square-button yaki-fill-button" aria-label="恢复默认语音识别模型" onClick={()=>change('asrModel',defaults.asrModel)}>→</button></div></label>
   <label>字幕翻译<div className="yaki-setting-inline"><input value={settings.translationModel} onChange={event=>change('translationModel',event.target.value)}/><button type="button" className="yaki-square-button yaki-fill-button" aria-label="恢复默认翻译模型" onClick={()=>change('translationModel',defaults.translationModel)}>→</button></div></label>
   <label>字幕精修<div className="yaki-setting-inline"><input value={settings.refinementModel} onChange={event=>change('refinementModel',event.target.value)}/><button type="button" className="yaki-square-button yaki-fill-button" aria-label="恢复默认精修模型" onClick={()=>change('refinementModel',defaults.refinementModel)}>→</button></div></label>
  </div>}
  {tab==='general'&&<div className="yaki-settings-fields"><label>默认项目目录<div className="yaki-setting-inline"><input value={settings.defaultProjectDir} readOnly placeholder="未设置；创建项目时手动选择"/><button type="button" className="yaki-square-button" aria-label="选择默认项目目录" onClick={()=>void chooseDirectory()}>📁</button></div></label></div>}
  <div className="yaki-settings-actions"><button type="button" className="extensions-primary" disabled={busy} onClick={()=>void save()}>{busy?'正在保存…':'保存设置'}</button></div>
  {help&&<div className="yaki-help-backdrop"><section className="yaki-help-dialog" role="dialog" aria-modal="true" aria-labelledby="yaki-key-help"><h3 id="yaki-key-help">获取阿里云 API Key</h3><ol><li>登录阿里云百炼控制台。</li><li>在 API Key 管理页面创建按量付费 Key。</li><li>复制通常以 sk- 开头的 Key，粘贴到这里并保存。</li></ol><p>Key 只写入当前 Windows 用户的本地配置目录，不会写入项目或任务记录。</p><button type="button" onClick={()=>setHelp(false)}>知道了</button></section></div>}
 </div>;
}
