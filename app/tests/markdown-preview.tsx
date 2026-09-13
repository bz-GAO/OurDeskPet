import React from 'react';
import {createRoot} from 'react-dom/client';
import MessageMarkdown from '../src/components/MessageMarkdown';
import '../src/App.css';
const text = '# 消息格式验证\n\n这里是 **粗体**、`inline_code` 和行内公式 $E=mc^2$。\n\n```python\ndef greet(name):\n    print(f"Hello, {name}")\n```\n\n$$\n\\int_0^1 x^2\\,dx = \\frac{1}{3}\n$$\n\n| 功能 | 状态 |\n| --- | --- |\n| 代码块 | 正常 |\n| 公式 | 正常 |\n\n- 列表与段落自动换行\n- 很长的代码和公式可以横向滚动\n\n> 未完成公式或代码不会中断消息显示。';
createRoot(document.getElementById('root')!).render(<div style={{padding:24,height:'100vh',overflow:'auto',boxSizing:'border-box',background:'#f4f7fb'}}><article className="dialogue-message" data-role="assistant"><span>Rina · 本地测试，无 API 请求</span><MessageMarkdown content={text}/></article></div>);
