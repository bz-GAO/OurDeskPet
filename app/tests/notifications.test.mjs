import {build} from 'esbuild';
import {mkdtemp,rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp=await mkdtemp(path.resolve('node_modules/.notice-test-'));
try {
  const outfile=path.join(temp,'controller.mjs');
  await build({entryPoints:['src/notifications/notificationController.ts'],outfile,bundle:true,platform:'node',format:'esm'});
  const {NotificationController,NOTICE_DURATION}=await import(pathToFileURL(outfile));
  const completed=(id='1')=>({source:'chat',taskId:id,status:'completed'});
  function fixture() {
    let reading=false,timer,state={phase:'idle',unread:0};const calls=[];
    const controller=new NotificationController({
      isReading:async()=>reading,reveal:async()=>calls.push('reveal'),minimize:async()=>calls.push('minimize'),
      attention:async(active)=>calls.push(active?'attention':'clear'),changed:value=>state=value,
      schedule:(cb,ms)=>{assert.equal(ms,NOTICE_DURATION);timer=cb;return()=>{timer=undefined;};},
    });
    return {controller,calls,get state(){return state;},read(value){reading=value;},async finish(){timer?.();await new Promise(resolve=>setImmediate(resolve));}};
  }
  {
    const f=fixture();await f.controller.receive(completed());await f.controller.receive(completed());await f.controller.receive(completed('2'));
    assert.deepEqual(f.state,{phase:'notifying',unread:2});assert.deepEqual(f.calls,['reveal']);
    await f.finish();assert.deepEqual(f.calls,['reveal','attention']);assert.equal(f.state.phase,'unread');
    f.controller.acknowledge('chat');assert.deepEqual(f.state,{phase:'idle',unread:0});assert.equal(f.calls.at(-1),'clear');
  }
  for(const status of ['started','cancelled','failed']) {const f=fixture();await f.controller.receive({...completed(),status});assert.deepEqual(f.calls,[]);}
  {const f=fixture();f.read(true);await f.controller.receive(completed());assert.equal(f.state.unread,0);assert.deepEqual(f.calls,[]);}
  {const f=fixture();await f.controller.receive(completed());await f.finish();assert(!f.calls.includes('minimize'));assert(f.calls.includes('attention'));}
  {const f=fixture();await f.controller.receive(completed());f.controller.dismiss();await f.finish();assert.equal(f.state.phase,'unread');assert(!f.calls.includes('minimize'));}
  {const f=fixture();await f.controller.receive(completed());f.read(true);await f.finish();assert.equal(f.state.unread,0);assert(!f.calls.includes('minimize'));}
  {const f=fixture();await f.controller.receive(completed());f.controller.dispose();await f.finish();assert(!f.calls.includes('minimize'));}
  {const f=fixture();const pending=f.controller.receive(completed());f.controller.acknowledge('chat');await pending;assert.equal(f.state.unread,0);assert(!f.calls.includes('reveal'));}
  {const f=fixture();await f.controller.receive({...completed(),status:'cancelled'});await f.controller.receive(completed());assert.equal(f.state.unread,0);}
  console.log('PASS: background completion, duplicate/concurrent events, cancellation/error, foreground reading, interaction, dismiss, focus race, disposal');
} finally {await rm(temp,{recursive:true,force:true});}
