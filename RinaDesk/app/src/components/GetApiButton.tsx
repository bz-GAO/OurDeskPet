import {useState} from 'react';
import {openUrl} from '@tauri-apps/plugin-opener';

export function GetApiButton({provider='deepseek'}:{provider?:'deepseek'|'bailian'}){
 const [error,setError]=useState('');
 const url=provider==='bailian'?'https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key':'https://platform.deepseek.com/api_keys';
 return <div className="get-api"><button type="button" onClick={()=>{setError('');void openUrl(url).catch(()=>setError('暂时无法打开平台页面。'));}}>获取 API ↗</button>{error&&<span role="status">{error}</span>}</div>;
}
