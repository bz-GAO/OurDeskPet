import {useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import './VoiceSfx.css';

type SfxSettings = {enabled: boolean; events: {notify: boolean; teleport: boolean; task: boolean}; volume: number; pack: string; ttsVoice?: string | null};
type SfxPayload = {settings: SfxSettings; pack: {name: string; title: string; found: boolean; clips: Record<string, {transcript: string; reviewed: boolean; present: boolean}>}};

const DEFAULT_SETTINGS:SfxSettings={enabled:true,events:{notify:true,teleport:true,task:true},volume:.8,pack:'default',ttsVoice:null};
const DEFAULT_PAYLOAD:SfxPayload={settings:DEFAULT_SETTINGS,pack:{name:'default',title:'',found:false,clips:{}}};

function object(value:unknown):Record<string,unknown>|null{return value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:null;}
function normalizePayload(value:unknown):{payload:SfxPayload;valid:boolean}{
  const root=object(value),rawSettings=object(root?.settings),rawEvents=object(rawSettings?.events),rawPack=object(root?.pack);
  const valid=Boolean(rawSettings&&rawEvents&&rawPack);
  const volume=typeof rawSettings?.volume==='number'&&Number.isFinite(rawSettings.volume)?Math.min(1,Math.max(0,rawSettings.volume)):DEFAULT_SETTINGS.volume;
  const packName=typeof rawSettings?.pack==='string'&&/^[a-z0-9_-]{1,64}$/.test(rawSettings.pack)?rawSettings.pack:DEFAULT_SETTINGS.pack;
  return {valid,payload:{
    settings:{
      enabled:typeof rawSettings?.enabled==='boolean'?rawSettings.enabled:DEFAULT_SETTINGS.enabled,
      events:{
        notify:typeof rawEvents?.notify==='boolean'?rawEvents.notify:DEFAULT_SETTINGS.events.notify,
        teleport:typeof rawEvents?.teleport==='boolean'?rawEvents.teleport:DEFAULT_SETTINGS.events.teleport,
        task:typeof rawEvents?.task==='boolean'?rawEvents.task:DEFAULT_SETTINGS.events.task,
      },
      volume,pack:packName,
      ttsVoice:typeof rawSettings?.ttsVoice==='string'?rawSettings.ttsVoice:null,
    },
    pack:{
      name:typeof rawPack?.name==='string'?rawPack.name:packName,
      title:typeof rawPack?.title==='string'?rawPack.title:'',
      found:rawPack?.found===true,
      clips:object(rawPack?.clips) as SfxPayload['pack']['clips']??{},
    },
  }};
}

const EVENT_LABELS: Array<[keyof SfxSettings['events'], string]> = [
  ['notify', '消息提醒'],
  ['teleport', '量子传送'],
  ['task', '任务结果'],
];

/** 音效设置（美术大类）：总开关 + 按事件勾选 + 音量；即改即存，不进脏标记流程。 */
export function VoiceSfxSettings() {
  const [state, setState] = useState<SfxPayload | null>(()=>isTauri()?null:DEFAULT_PAYLOAD);
  const [error, setError] = useState('');
  const [saving,setSaving]=useState(false);
  const mounted=useRef(true),revision=useRef(0),confirmed=useRef(DEFAULT_SETTINGS),chain=useRef(Promise.resolve()),lastQueued=useRef('');
  useEffect(() => {
    mounted.current=true;
    if (!isTauri()) return()=>{mounted.current=false;};
    void invoke<unknown>('voice_output_settings_get').then(value=>{
      if(!mounted.current)return;
      const next=normalizePayload(value);confirmed.current=next.payload.settings;setState(next.payload);
      setError(next.valid?'':'音效设置返回格式异常，已显示安全默认值；修改后才会写入。');
    }).catch(e => {if(mounted.current)setError(String(e));});
    return()=>{mounted.current=false;};
  }, []);
  function save(next: SfxSettings) {
    setState(current => (current ? {...current, settings: next} : current));
    const serialized=JSON.stringify(next);if(serialized===lastQueued.current)return;
    lastQueued.current=serialized;const token=++revision.current;setSaving(true);
    chain.current=chain.current.then(async()=>{
      try{
        await invoke('voice_output_settings_save',{settings:next});confirmed.current=next;
        if(mounted.current&&token===revision.current)setError('');
      }catch(e){
        if(mounted.current&&token===revision.current){lastQueued.current='';setState(current=>current?{...current,settings:confirmed.current}:current);setError(`音效设置未保存：${String(e)}`);}
      }finally{if(mounted.current&&token===revision.current)setSaving(false);}
    });
  }
  if (!state) return <div className="voice-sfx">{error ? <p className="settings-error" role="status">{error}</p> : <p className="voice-sfx-loading" role="status">读取音效设置…</p>}</div>;
  const {settings, pack} = state;
  return (
    <div className="voice-sfx">
      <label className="voice-sfx-master setting-row">
        <strong>事件音效</strong>
        <input type="checkbox" checked={settings.enabled} onChange={e => void save({...settings, enabled: e.target.checked})}/>启用
      </label>
      {settings.enabled && (
        <>
          <div className="voice-sfx-events" role="group" aria-label="音效事件">
            {EVENT_LABELS.map(([key, label]) => (
              <label key={key}>
                <input type="checkbox" checked={settings.events[key]} onChange={e => void save({...settings, events: {...settings.events, [key]: e.target.checked}})}/>{label}
              </label>
            ))}
          </div>
          <label className="voice-sfx-volume">
            音量 <input type="range" min="0" max="100" value={Math.round(settings.volume * 100)} aria-label="音效音量"
              onChange={e=>setState(current=>current?{...current,settings:{...current.settings,volume:Number(e.target.value)/100}}:current)}
              onPointerUp={e=>save({...settings,volume:Number(e.currentTarget.value)/100})}
              onKeyUp={e=>save({...settings,volume:Number(e.currentTarget.value)/100})}
              onBlur={e=>save({...settings,volume:Number(e.currentTarget.value)/100})}/>
            <span>{Math.round(settings.volume * 100)}%</span>
          </label>
          <p className="voice-sfx-pack">
            音效包：{pack.found ? `${pack.name}${pack.title ? ` · ${pack.title}` : ''}` : `未找到「${pack.name}」的 pack.json`}
          </p>
        </>
      )}
      {saving&&<p className="voice-sfx-saving" role="status">正在保存…</p>}
      {error && <p className="settings-error" role="status">{error}</p>}
    </div>
  );
}
