import {useEffect,useRef,useState,type ReactNode} from 'react';

export function PreviewRail({children}:{children:ReactNode}){
 const rail=useRef<HTMLDivElement>(null);
 const gesture=useRef<{id:number;x:number;scroll:number}|null>(null);
 const [overflow,setOverflow]=useState(false);
 const [dragging,setDragging]=useState(false);
 useEffect(()=>{
  const el=rail.current;if(!el)return;
  const measure=()=>setOverflow(el.scrollWidth>el.clientWidth+1);
  const observer=new ResizeObserver(measure);observer.observe(el);
  for(const child of el.children)observer.observe(child);
  measure();return()=>observer.disconnect();
 },[children]);
 function end(){gesture.current=null;setDragging(false);}
 return <div className="art-preview-strip">
  <div ref={rail} className="art-poses" role="region" aria-label="美术预览，可左右滚动" tabIndex={0} data-overflow={overflow} data-dragging={dragging}
   onDragStart={e=>e.preventDefault()}
   onPointerDown={e=>{if(e.pointerType!=='mouse'||e.button!==0||!overflow)return;gesture.current={id:e.pointerId,x:e.clientX,scroll:e.currentTarget.scrollLeft};e.currentTarget.setPointerCapture(e.pointerId);setDragging(true);e.preventDefault();}}
   onPointerMove={e=>{const start=gesture.current;if(start&&start.id===e.pointerId)e.currentTarget.scrollLeft=start.scroll+start.x-e.clientX;}}
   onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);end();}}
   onPointerCancel={end} onLostPointerCapture={end} onBlur={end}>
   {children}
  </div>
  {overflow&&<span className="art-scroll-hint">左右拖动查看更多 · 支持触控板滑动</span>}
 </div>;
}
