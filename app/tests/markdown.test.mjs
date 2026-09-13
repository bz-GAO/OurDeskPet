import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const temp = await mkdtemp(path.resolve('node_modules/.markdown-test-'));
try {
  const outfile = path.join(temp, 'renderer.mjs');
  await build({ entryPoints: ['src/components/MessageMarkdown.tsx'], outfile, bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic', plugins: [{name:'omit-css',setup(b){b.onResolve({filter:/\.css$/},a=>({path:a.path,namespace:'empty-css'}));b.onLoad({filter:/.*/,namespace:'empty-css'},()=>({contents:'',loader:'js'}));}}] });
  const {default: Message} = await import(pathToFileURL(outfile));
  const render = content => renderToStaticMarkup(React.createElement(Message,{content}));
  const code = render('```js\nconst x = "<tag>";\n```');
  assert.match(code, /code-language">js</);
  assert.match(code, /hljs-keyword/);
  assert.match(code, /&lt;tag&gt;/);
  assert.doesNotMatch(code, /<tag>/);
  assert.match(render('```python\nprint(10)\n```'), /code-language">python</);
  assert.match(render('```unknownlang\nplain <code>\n```'), /code-language">unknownlang</);
  assert.match(render('```\nplain\n```'), /code-language">text</);
  assert.match(render('Inline $x^2$\n\n$$\n\\frac{1}{2}\n$$'), /katex-display/);
  assert.match(render('| A | B |\n| - | - |\n| 1 | 2 |'), /<table>/);
  assert.doesNotMatch(render('<script>alert(1)</script>\n\n[bad](javascript:alert%281%29)'), /<script|href="javascript:/);
  assert.doesNotMatch(render('![remote](https://example.com/tracker.png)'), /<img/);
  const unfinished = 'Answer\n\n```python\nprint("hello")\n```\n\n$$\n\\frac{1}{2}\n$$';
  for (let i=1;i<=unfinished.length;i++) assert.doesNotThrow(()=>render(unfinished.slice(0,i)));
  assert.doesNotThrow(()=>render('$$\n\\unknowncommand{\n$$'));
  console.log('PASS: code, inline/display math, tables, unsafe HTML/URLs, remote images, streaming prefixes, invalid TeX');
} finally { await rm(temp,{recursive:true,force:true}); }
