import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {invoke,isTauri} from '@tauri-apps/api/core';
import './ProjectSettingsProposal.css';
import {ConfirmDialog} from './ConfirmDialog';

type Change={key:string;label:string;before:string|number|boolean;after:string|number|boolean};
type Proposal={id:string;session:string;turn:string;page:string;changes:Change[]};
const display=(value:Change['before'])=>typeof value==='boolean'?(value?'开启':'关闭'):({auto:'自动判断',off:'不联网',required:'必须搜索'}[String(value)]??String(value));

// Only typed backend proposals render controls. Markdown, imported JSON and model text
// cannot create executable cards. The server owns the patch; the UI sends only its ID.
export function ProjectSettingsProposal({session,busy,visible}:{session:string;busy:boolean;visible:boolean}){
 const [proposal,setProposal]=useState<Proposal|null>(null);
 const [working,setWorking]=useState(false),[error,setError]=useState('');
 const [results,setResults]=useState<{proposal:Proposal;text:string;failed:boolean}[]>([]);
 const lock=useRef(false),settled=useRef(new Set<string>());
 useEffect(()=>{
  if(!isTauri()||busy)return;
  let alive=true;
  void invoke<Proposal[]>('project_settings_pending',{session}).then(items=>{if(alive&&!lock.current){setProposal(items.find(item=>!settled.current.has(item.id))??null);setError('');}}).catch(error=>{if(alive)setError(String(error));});
  return()=>{alive=false;};
 },[session,busy,visible]);
 async function decide(apply:boolean){
  if(!proposal||busy||lock.current)return;
  lock.current=true;setWorking(true);setError('');
  try{const text=await invoke<string>('project_settings_decide',{session,id:proposal.id,apply});setResults(previous=>[...previous,{proposal,text,failed:false}]);}
  catch(error){setResults(previous=>[...previous,{proposal,text:String(error),failed:true}]);}
  finally{settled.current.add(proposal.id);setProposal(null);setWorking(false);lock.current=false;}
 }
 if(!visible)return null;
 return <>{proposal&&<ConfirmDialog title="设置修改确认" busy={busy||working} confirmLabel="确认修改" onConfirm={()=>void decide(true)} onCancel={()=>void decide(false)}>
  <strong>{proposal.page}</strong><div className="project-settings-comparison"><table><thead><tr><th>设置</th><th>当前</th><th>修改后</th></tr></thead><tbody>{proposal.changes.map(change=><tr key={change.key}><th scope="row">{change.label}</th><td>{display(change.before)}</td><td>{display(change.after)}</td></tr>)}</tbody></table></div>
 </ConfirmDialog>}{error&&<p role="alert">{error}</p>}{results.map(result=>{
  const anchor=[...document.querySelectorAll<HTMLElement>('[data-project-settings-turn]')].find(node=>node.dataset.projectSettingsTurn===result.proposal.turn);
  // Removed turns cannot leave orphaned action cards at the conversation bottom.
  return anchor?createPortal(<p className="project-settings-result" role={result.failed?'alert':'status'}>{result.text}</p>,anchor,result.proposal.id):null;
 })}</>;
}
