import {Children,isValidElement,useMemo,type ReactNode} from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import rust from 'highlight.js/lib/languages/rust';

for(const [name,grammar] of Object.entries({python,javascript,typescript,json,bash,css,xml,rust}))hljs.registerLanguage(name,grammar);

export function CodeBlock({children}:{children?:ReactNode}) {
  const child=Children.toArray(children)[0];
  const props=isValidElement<{className?:string;children?:ReactNode}>(child)?child.props:null;
  const language=/\blanguage-([^\s]+)/.exec(props?.className??'')?.[1]??'';
  const source=typeof props?.children==='string'?props.children:null;
  const highlighted=useMemo(()=>{
    if(source===null || source.length>20000 || !language || !hljs.getLanguage(language))return null;
    try{return hljs.highlight(source,{language,ignoreIllegals:true}).value;}catch{return null;}
  },[source,language]);
  return <div className="markdown-code-block"><div className="code-language">{language || 'text'}</div>
    <pre>{highlighted!==null
      ? <code className={`hljs language-${language}`} dangerouslySetInnerHTML={{__html:highlighted}}/>
      : children}</pre>
  </div>;
}
