const politePrefixes=[
  /^(?:请问|请你|请帮我|麻烦你?|劳烦|能否|能不能|可以帮我|帮我|我想请你|我想让你|想请你)\s*/,
  /^(?:看看|看一下|检查一下|分析一下|解释一下|告诉我|说说)\s*/,
];

function clean(value:string){
  let text=value
    .replace(/```[\s\S]*?```/g,' ')
    .replace(/https?:\/\/\S+/gi,' ')
    .replace(/^\s*(?:[-*>#]+|\d+[.)、])\s*/gm,' ')
    .replace(/[`*_~\[\](){}<>]/g,' ')
    .replace(/\s+/g,' ').trim();
  for(let pass=0;pass<3;pass++){
    const before=text;
    for(const prefix of politePrefixes)text=text.replace(prefix,'');
    if(text===before)break;
  }
  return text.replace(/^[，。！？,.!?；;：:\s]+|[，。！？,.!?；;：:\s]+$/g,'');
}

function bounded(text:string){
  const clause=text.split(/[。！？!?；;\n]/,1)[0]?.trim()??'';
  if(!clause)return '';
  const mostlyLatin=(clause.match(/[A-Za-z0-9]/g)?.length??0)>clause.length/2;
  if(mostlyLatin){
    const words=clause.split(/\s+/).filter(Boolean);
    return words.slice(0,8).join(' ').slice(0,72).trim();
  }
  const chars=Array.from(clause);
  if(chars.length<=20)return clause;
  const window=chars.slice(0,20).join('');
  const boundary=Math.max(window.lastIndexOf('，'),window.lastIndexOf('、'),window.lastIndexOf('：'),window.lastIndexOf(' '));
  return Array.from(boundary>=8?window.slice(0,boundary):window).slice(0,20).join('').trim();
}

/** Deterministic, no-model title used immediately for the first eligible user turn. */
export function conversationTitle(text:string,{images=false,files=false}:{images?:boolean;files?:boolean}={}){
  const title=bounded(clean(text));
  if(title)return title;
  if(images&&files)return '附件分析';
  if(images)return '图片分析';
  if(files)return '文件分析';
  return '新对话';
}
