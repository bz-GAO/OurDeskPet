// Reuse verified developer fixtures to capture the real React interfaces.
// All bridge data are synthetic; no account, microphone or paid API is used.
const {readFileSync,mkdirSync}=require('node:fs');
const {spawnSync,spawn}=require('node:child_process');
const {createServer}=require('node:net');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const output=process.argv[2];
if(!output||!path.isAbsolute(output))throw new Error('Pass an absolute screenshot output directory.');
mkdirSync(output,{recursive:true});
const capture=String.raw`
async function guideShot(page,name,selectors=[]){
 await page.waitForTimeout(220);
 const marks=await page.evaluate(selectors=>{
  const marks=[];
  for(const selector of selectors)for(const node of document.querySelectorAll(selector)){
   const rect=node.getBoundingClientRect();if(rect.width===0||rect.height===0)continue;
   const mark=document.createElement('div');mark.style.cssText='position:fixed;pointer-events:none;z-index:2147483646;border:2px solid #d32642;box-sizing:border-box';
   Object.assign(mark.style,{left:rect.left+'px',top:rect.top+'px',width:rect.width+'px',height:rect.height+'px'});document.body.append(mark);marks.push(mark);
  }
  const note=document.createElement('div');note.textContent='开发者演示 · 示例数据 · @bz-GAO';note.style.cssText='position:fixed;bottom:4px;left:6px;z-index:2147483647;background:#fffef2;color:#26384a;padding:3px 8px;font:12px sans-serif;border:1px solid #aab3bd;pointer-events:none';document.body.append(note);marks.push(note);
  window.__guideMarks=marks;return marks.length;
 },selectors);
 await page.screenshot({path:require('node:path').join(process.env.GUIDE_OUTPUT,name)});
 await page.evaluate(()=>{window.__guideMarks.forEach(node=>node.remove());delete window.__guideMarks;});
}
`;
function inject(source,marker,addition){
 if(!source.includes(marker))throw new Error('Capture marker changed: '+marker);
 return source.replace(marker,addition+'\n'+marker);
}
async function main(){
 const port=await new Promise(resolve=>{const server=createServer();server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));});});
 const base=`http://127.0.0.1:${port}`;
 const env={...process.env,GUIDE_OUTPUT:output,RINADESK_PREVIEW_URL:base,ART_TEST_URL:base+'/?view=settings',PROJECT_SETTINGS_TEST_URL:base+'/?view=dialogue',TOMO_TEST_URL:base+'/tomo-ui-test',YAKI_TEST_URL:base+'/?view=settings'};
 const vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,env,stdio:['ignore','ignore','inherit']});
 try{
  let ready=false;for(let n=0;n<100;n++){try{if((await fetch(base)).ok){ready=true;break;}}catch{}await new Promise(resolve=>setTimeout(resolve,100));}
  if(!ready)throw new Error('Preview server did not start.');
  for(const fixture of ['settings-ui','project-settings-ui','yaki-ui','tomo-ui']){
   let source=readFileSync(path.join(root,'tests',fixture+'.test.cjs'),'utf8');
   if(fixture==='settings-ui'){
    source=inject(source,' const beforeArt='," await guideShot(page,'07-美术音效.png',['.art-tab .settings-disclosure']);");
    source=inject(source," await page.getByLabel('配置代号').fill", " await guideShot(page,'02-API配置.png',['.api-profile-form','.get-api']);");
    source=inject(source," await popup.dispatchEvent", " await page.setViewportSize({width:420,height:410});await page.waitForTimeout(200);await guideShot(page,'01-桌宠入口.png',['.board-star','.pet-settings-face']);await page.setViewportSize({width:280,height:410});");
   }
   if(fixture==='project-settings-ui')source=inject(source,"  await modal.getByRole('button'", "  await guideShot(page,'03-项目助手确认.png',['.chat-mode-switch','dialog']);");
   if(fixture==='yaki-ui'){
    source=inject(source,"  assert.equal(await page.getByLabel('字体'", "  await guideShot(page,'04-字幕导出.png',['.yaki-style-fields']);");
    source=inject(source,'  await page.evaluate(()=>{window.testJob.state.total=0;',"  await guideShot(page,'05-任务进度.png',['progress']);");
   }
   if(fixture==='tomo-ui')source=inject(source,'  const layout=',"  await page.getByText('通知与深夜休眠',{exact:true}).scrollIntoViewIfNeeded();await guideShot(page,'06-Tomo设置.png',['.tomo-night-range','.tomo-open-panel']);");
   const result=spawnSync(process.execPath,['-e',capture+'\n'+source],{cwd:root,env,stdio:'inherit'});
   if(result.status!==0)throw new Error('Capture failed: '+fixture);
  }
 }finally{vite.kill();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
