import {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {PetView} from '../src/components/PetView';
import {usePetController} from '../src/pet/usePetController';
import '../src/App.css';
function Preview(){const controller=usePetController();const [actions,setActions]=useState<string[]>([]);const record=(name:string)=>()=>setActions(a=>[...a,name]);return <><PetView controller={controller} onStartDrag={record('drag')} onOpenDialogue={record('chat')} onMinimize={record('minimize')} onClose={record('close')}/><output hidden data-testid="actions">{actions.join(',')}</output></>};createRoot(document.getElementById('root')!).render(<Preview/>);
