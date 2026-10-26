import {spawn} from 'node:child_process';
import {rm} from 'node:fs/promises';
import {createServer} from 'node:net';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const cwd=fileURLToPath(new URL('../',import.meta.url));
const tests=[
 'billing-ui',
 'chat-storage-ui',
 'model-title-ui',
 'project-settings-ui',
 'rest-effect-ui',
 'restore-ui',
 'teleport-ui',
 'tomo-ui',
 'yaki-ui',
];

function freePort(){
 return new Promise((resolve,reject)=>{
  const server=createServer();
  server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
   const address=server.address();
   const port=typeof address==='object'&&address?address.port:0;
   server.close(error=>error?reject(error):resolve(port));
  });
 });
}

async function waitForServer(url,processHandle){
 for(let attempt=0;attempt<100;attempt++){
  if(processHandle.exitCode!==null)throw new Error(`Vite exited before UI tests started (${processHandle.exitCode}).`);
  try{
   const response=await fetch(url);
   if(response.ok)return;
  }catch{}
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw new Error(`Timed out waiting for ${url}`);
}

function runTest(test,env){
 return new Promise((resolve,reject)=>{
  const child=spawn(process.execPath,[`tests/${test}.test.cjs`],{cwd,env,stdio:'inherit'});
  child.once('error',reject);
  child.once('exit',(code,signal)=>{
   if(code===0)resolve();
   else reject(new Error(`${test} failed (${signal??code??'unknown'}).`));
  });
 });
}

const port=await freePort();
const base=`http://127.0.0.1:${port}`;
const screenshot=path.join(tmpdir(),`rinadesk-teleport-${process.pid}.png`);
const env={
 ...process.env,
 BILLING_TEST_URL:`${base}/?view=dialogue`,
 CHAT_TEST_URL:`${base}/?view=dialogue`,
 ART_TEST_URL:`${base}/?view=settings`,
 PROJECT_SETTINGS_TEST_URL:`${base}/?view=dialogue`,
 REST_EFFECT_TEST_URL:`${base}/rest-effect-test`,
 RESTORE_TEST_URL:`${base}/restore-test`,
 RINADESK_PREVIEW_URL:base,
 TELEPORT_TEST_URL:`${base}/teleport-test`,
 TELEPORT_SCREENSHOT:screenshot,
 TOMO_TEST_URL:`${base}/tomo-ui-test`,
 YAKI_TEST_URL:`${base}/?view=settings`,
};
const vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{
 cwd,
 env,
 stdio:['ignore','ignore','inherit'],
});

try{
 await waitForServer(base,vite);
 for(const test of tests)await runTest(test,env);
}finally{
 vite.kill();
 await rm(screenshot,{force:true});
}
