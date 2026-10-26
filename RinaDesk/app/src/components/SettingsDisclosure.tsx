import {useState,type ReactNode} from 'react';

export function SettingsDisclosure({title,defaultOpen=false,children,className=''}:{title:string;defaultOpen?:boolean;children:ReactNode;className?:string}){
 const [open,setOpen]=useState(defaultOpen);
 return <details className={`settings-disclosure ${className}`.trim()} open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
  <summary><span><strong>{title}</strong></span><i aria-hidden="true">⌄</i></summary>
  <div className="settings-disclosure-body">{children}</div>
 </details>;
}
