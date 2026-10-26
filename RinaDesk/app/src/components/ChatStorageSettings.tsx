import {useStorageSettings} from '../llm/useConversationStorage';
import {displayConfigPath} from './displayConfigPath';
export function ChatStorageSettings(){
 const storage=useStorageSettings();
 return <div className="chat-storage-settings">
  <label>保存方式<select aria-label="默认对话保存方式" value={storage.settings?.enabled?'auto':'off'} disabled={!storage.settings||storage.busy} onChange={event=>void storage.change('chat_storage_enable',{enabled:event.target.value==='auto'})}><option value="auto">自动保存</option><option value="off">不保存</option></select></label>
  <label>保存目录<input readOnly aria-label="对话保存目录" value={displayConfigPath(storage.settings?.directory??'')} /></label>
  <button type="button" disabled={storage.busy||!storage.settings} onClick={()=>void storage.change('chat_storage_choose')}>更改目录</button>
  {storage.error&&<p role="alert" className="settings-error">{storage.error}</p>}
 </div>;
}
