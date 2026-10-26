import {useCallback,useEffect,useRef,useState} from 'react';
import {invoke,isTauri} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import {openUrl} from '@tauri-apps/plugin-opener';
import './BillingStatus.css';
import {useConfirmDialog} from './ConfirmDialog';
import {GetApiButton} from './GetApiButton';

type Usage={day:string;amount_micro:number;calls:number;unknown:number;tokens:number};
type Account={id:string;label:string;active?:boolean;day:string;incomplete:boolean;billingConnected:boolean;balance:{values:Array<[string,string]>;updatedAt:string;message:string};today:{amount_micro:number;calls:number;unknown:number;tokens:number};history?:Usage[]};
const selectionKey='rinadesk.billing-account';
function formatMicroCny(value:number,detailed:boolean){
 const micro=Math.max(0,Math.trunc(value));
 if(!detailed)return `¥ ${(micro/1_000_000).toFixed(2)}`;
 return `¥ ${Math.floor(micro/1_000_000)}.${String(micro%1_000_000).padStart(6,'0')}`;
}
export function BillingStatus({compact=false,onDirtyChange}:{compact?:boolean;onDirtyChange?:(dirty:boolean)=>void}){
 const {confirm,dialog}=useConfirmDialog();
 const [accounts,setAccounts]=useState<Account[]>([]),[selected,setSelected]=useState(()=>localStorage.getItem(selectionKey)??''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [statsOpen,setStatsOpen]=useState(false);
 const [editingConnection,setEditingConnection]=useState(false);
 const locked=useRef(false),queued=useRef<boolean|null>(null),mounted=useRef(false),draftAccount=useRef('');
 const [accessId,setAccessId]=useState(''),[accessSecret,setAccessSecret]=useState(''),[saving,setSaving]=useState(false),[connectionResult,setConnectionResult]=useState('');
 useEffect(()=>{onDirtyChange?.(Boolean(accessId||accessSecret));},[accessId,accessSecret,onDirtyChange]);
 useEffect(()=>()=>onDirtyChange?.(false),[onDirtyChange]);
 const refresh=useCallback(async(force=false)=>{
  if(!isTauri()||!mounted.current)return;
  // A usage event can arrive while the balance request is in flight. Keep one
  // follow-up refresh, preserving an explicit forced refresh if requested.
  if(locked.current){queued.current=Boolean(queued.current||force);return;}
  locked.current=true;setBusy(true);
  try{
   const values=await invoke<Account[]>('billing_status',{force:false,localOnly:true});
   if(!mounted.current)return;
   setAccounts(previous=>values.map(value=>({...value,balance:value.balance.updatedAt?value.balance:previous.find(a=>a.id===value.id)?.balance??value.balance})));setError('');
   await Promise.all(values.filter(value=>value.active!==false).map(async value=>{
    try{
     const balance=await invoke<Account['balance']>('billing_balance',{account:value.id,force});
     if(!balance||!Array.isArray(balance.values))throw new Error('余额响应无效');
     if(mounted.current)setAccounts(previous=>previous.map(a=>a.id===value.id?{...a,balance}:a));
    }catch(e){if(mounted.current)setError(String(e));}
   }));
  }
  catch(e){if(mounted.current)setError(String(e));}finally{locked.current=false;if(mounted.current){setBusy(false);if(queued.current!==null){const next=queued.current;queued.current=null;void refresh(next);}}}
 },[]);
 useEffect(()=>{
  mounted.current=true;void refresh();let alive=true;let off:(()=>void)|undefined;
  const timer=setInterval(()=>{if(!document.hidden)void refresh();},15000);
  const focus=()=>void refresh();window.addEventListener('focus',focus);
  const visible=()=>{if(!document.hidden)void refresh();};document.addEventListener('visibilitychange',visible);
  if(isTauri())void listen('deskpet-billing-updated',()=>void refresh()).then(fn=>{if(alive)off=fn;else fn();}).catch(()=>{});
  return()=>{alive=false;mounted.current=false;queued.current=null;clearInterval(timer);window.removeEventListener('focus',focus);document.removeEventListener('visibilitychange',visible);off?.();};
 },[refresh]);
 const account=accounts.find(a=>a.id===selected)??accounts[0];
 const consoleUrl=account?.id.startsWith('deepseek:')?'https://platform.deepseek.com/usage':account?.id.startsWith('bailian:')?'https://billing-cost.console.aliyun.com/fortune/billing-account':account?.id.startsWith('qianwen:')?'https://platform.qianwenai.com/':null;
 // A profile may disappear after settings change in another window. Its draft
 // must never silently attach to the fallback account chosen for display.
 useEffect(()=>{draftAccount.current=account?.id??'';setAccessId('');setAccessSecret('');setConnectionResult('');setEditingConnection(false);},[account?.id]);
 const balance=account?.balance.values.map(([currency,value])=>`${currency==='CNY'?'¥':currency==='JPY'?'JP¥':'$'} ${value}`).join(' / ')||account?.balance.message||'—';
 const amountMicro=account?.today.amount_micro??0;
 const history=account?.history??[];
 const historyAmount=history.reduce((sum,item)=>sum+item.amount_micro,0),historyCalls=history.reduce((sum,item)=>sum+item.calls,0),historyMax=Math.max(1,...history.map(item=>item.amount_micro));
 const historyPartial=history.some(item=>item.unknown>0)||Boolean(account?.incomplete);
 const partial=Boolean(account?.incomplete||account?.today.unknown);
 const today=account?(partial&&amountMicro===0?'暂不可用':`${formatMicroCny(amountMicro,!compact)}${partial?'*':''}`):'—';
 async function connect(clear=false){
  if(!account||saving)return;
  if(clear&&!await confirm('断开此账户的余额查询？'))return;
  if(!clear&&draftAccount.current!==account.id){setConnectionResult('账户已变化，请重新填写授权。');return;}
  setSaving(true);setConnectionResult('');
  try{await invoke('billing_connection_save',{account:account.id,id:accessId,secret:accessSecret,clear});setAccessId('');setAccessSecret('');setEditingConnection(false);setConnectionResult(clear?'已断开':'已保存');await refresh(true);}
  catch(e){setConnectionResult(String(e));}finally{setSaving(false);}
 }
 const balanceHint=account?.balance.updatedAt?`${account.balance.message?`${account.balance.message}；显示上次结果。`:'账户可用余额。'}更新于 ${new Date(account.balance.updatedAt).toLocaleString()}`:account?.balance.message;
 const usageHint=`${account?.day??''} 本机三个项目按参考价累计，含 Chat 标题、摘要及助手工具轮次。赠金、免费额度和优惠未抵扣；DeepSeek 暂按高峰价计算。${partial?'部分用量或单价缺失，金额不完整。':''}`;
 if(!account)return <section className={`billing-status ${compact?'is-compact':'is-settings'}`} aria-label="API 账户状态">{busy?<span role="status">读取账户…</span>:error?<><span role="status">账户读取失败</span><button type="button" onClick={()=>void refresh(true)}>重试</button></>:<GetApiButton/>}</section>;
 return <section className={`billing-status ${compact?'is-compact':'is-settings'}`} aria-label="API 账户状态">
  {dialog}
  <div className="billing-status-heading"><select aria-label="计费账户" value={account?.id??''} onChange={async event=>{const value=event.target.value;if((accessId||accessSecret)&&!await confirm('放弃尚未保存的账务授权？'))return;setAccessId('');setAccessSecret('');setConnectionResult('');setSelected(value);localStorage.setItem(selectionKey,value);}} disabled={!accounts.length||saving}>{accounts.length?accounts.map(a=><option key={a.id} value={a.id}>{a.label}</option>):<option value="">API 账户</option>}</select>
   <button type="button" aria-label="刷新账户状态" title="刷新" disabled={busy||!isTauri()} onClick={()=>void refresh(true)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 7v5h-5M5 17v-5h5M18 12a6 6 0 0 0-10-4L5 12m14 0-3 4a6 6 0 0 1-10-4"/></svg></button>
   {consoleUrl&&<button type="button" aria-label="打开账务控制台" title="账务控制台" onClick={()=>void openUrl(consoleUrl).catch(e=>setError(String(e)))}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6m0-6L10 14M10 4H4v16h16v-6"/></svg></button>}
  </div>
  <dl><div title={balanceHint}><dt>账户余额</dt><dd data-stale={Boolean(account?.balance.message)}>{balance}</dd></div><div title={usageHint}><dt>今日花费</dt><dd>{today}</dd></div></dl>
  {account?.balance.message&&account.balance.values.length>0&&account.balance.updatedAt&&<span className="billing-status-note">上次更新 {new Date(account.balance.updatedAt).toLocaleString()}</span>}
  {!compact&&<>{partial&&<p className="billing-status-note">部分用量或单价未适配，金额不完整。</p>}
   {account?.active!==false&&account?.id.startsWith('bailian:')&&<details className="billing-connection"><summary>{account.billingConnected?'余额查询已连接':'查询阿里云余额'}</summary>
    {account.billingConnected&&!editingConnection?<div className="billing-connection-links"><button type="button" disabled={saving} onClick={()=>{setEditingConnection(true);setConnectionResult('');}}>更新授权</button><button type="button" disabled={saving} onClick={()=>void connect(true)}>断开</button></div>:<>
     <p>RAM 只读权限：<code>bss:DescribeAcccount</code></p><div className="billing-connection-links"><button type="button" onClick={()=>void openUrl('https://ram.console.aliyun.com/').catch(e=>setError(String(e)))}>配置授权 ↗</button><button type="button" onClick={()=>void openUrl('https://help.aliyun.com/zh/user-center/developer-reference/api-calling-authorization').catch(e=>setError(String(e)))}>授权说明 ↗</button></div>
     <form onSubmit={e=>{e.preventDefault();void connect();}}><label>AccessKey ID<input value={accessId} autoComplete="off" required disabled={saving} onChange={e=>setAccessId(e.target.value)}/></label><label>AccessKey Secret<input type="password" value={accessSecret} autoComplete="new-password" required disabled={saving} onChange={e=>setAccessSecret(e.target.value)}/></label><div><button type="submit" disabled={saving||!isTauri()}>{account.billingConnected?'保存授权':'连接查询'}</button>{account.billingConnected&&<button type="button" disabled={saving} onClick={()=>{setEditingConnection(false);setAccessId('');setAccessSecret('');}}>取消</button>}</div></form>
    </>}{connectionResult&&<p role="status">{connectionResult}</p>}</details>}
   {!accounts.length&&<p className="billing-status-note">配置 API 后会自动识别支持的平台。</p>}</>}
  {error&&<span className="billing-status-error" role="status" title={error}>账户状态暂不可用</span>}
  {!compact&&<>
   {statsOpen&&<div className="billing-history" aria-label="近 7 天用量统计">
    <div className="billing-history-summary"><span>近 7 天</span><strong>{formatMicroCny(historyAmount,true)}{historyPartial?'*':''}</strong><span>{historyCalls} 次</span></div>
    <div className="billing-history-chart">{history.map(item=><div className="billing-history-day" key={item.day} title={`${item.day} · ${formatMicroCny(item.amount_micro,true)} · ${item.calls} 次`}>
     <div className="billing-history-track"><i style={{height:item.amount_micro?`${Math.max(8,item.amount_micro/historyMax*100)}%`:'2px'}}/></div><span>{item.day.slice(5).replace('-','/')}</span>
    </div>)}</div>
   </div>}
   <button type="button" className="billing-history-toggle" aria-label={statsOpen?'收起用量统计':'展开用量统计'} aria-expanded={statsOpen} onClick={()=>setStatsOpen(value=>!value)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
  </>}
 </section>;
}
