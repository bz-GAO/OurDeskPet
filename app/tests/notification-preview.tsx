import {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {PetView} from '../src/components/PetView';
import {usePetController} from '../src/pet/usePetController';
import {NotificationController,type NoticeState} from '../src/notifications/notificationController';
import '../src/App.css';
function Preview(){
  const pet=usePetController();const [notice,setNotice]=useState<NoticeState>({phase:'idle',unread:0});
  const [logs,setLogs]=useState<string[]>([]);const [reading,setReading]=useState(false);const read=useRef(false);read.current=reading;
  const [hold,setHold]=useState(false);
  const [machine]=useState(()=>new NotificationController({
    isReading:async()=>read.current,
    reveal:async()=>setLogs(a=>[...a,'reveal']),attention:async(active)=>setLogs(a=>[...a,active?'attention':'clear']),
    changed:setNotice,schedule:(callback,ms)=>{const id=setTimeout(callback,ms);return()=>clearTimeout(id);},
  }));
  useEffect(()=>()=>machine.dispose(),[machine]);
  return <><style>{'.pet-popup-shell{width:280px;height:410px} .test-controls{position:fixed;left:300px;top:12px;width:270px;color:#eee} .test-controls button{margin:4px;padding:8px}'}</style>
    <PetView controller={pet} notificationPhase={hold?'notifying':notice.phase} unreadCount={notice.unread} onNoticeDismiss={()=>machine.dismiss()} onStartDrag={()=>machine.dismiss()} onMinimize={()=>setLogs(a=>[...a,'manual-minimize'])} onClose={()=>setLogs(a=>[...a,'close'])} onOpenDialogue={()=>{setReading(true);machine.acknowledge('chat');}}/>
    <aside className="test-controls"><h3>通知本地模拟</h3>
      <button onClick={()=>void machine.receive({source:'chat',taskId:crypto.randomUUID(),status:'completed'})}>模拟完成</button>
      <button onClick={()=>void machine.receive({source:'chat',taskId:crypto.randomUUID(),status:'cancelled'})}>模拟取消</button>
      <button onClick={()=>{machine.acknowledge('chat');setLogs([]);}}>清除未读</button>
      <label><input type="checkbox" checked={reading} onChange={e=>setReading(e.target.checked)}/>聊天正在前台</label>
      <button onClick={()=>setHold(v=>!v)}>切换持续外观预览</button>
      <p role="status">{notice.phase} / unread:{notice.unread}</p><output>{logs.join(', ')}</output>
    </aside></>;
}
createRoot(document.getElementById('root')!).render(<Preview/>);
