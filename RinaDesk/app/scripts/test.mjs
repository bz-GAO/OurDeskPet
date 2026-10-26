import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const cwd=fileURLToPath(new URL('../',import.meta.url));
for(const test of ['art','notifications','markdown','chat-context','image-store','text-file-payload','delimited-file-parser','code-file-parser','file-parser','tomo-state','voice-phase','tool-calls','agent-tasks','voice-reply']){
 const result=spawnSync(process.execPath,[`tests/${test}.test.mjs`],{cwd,stdio:'inherit'});
 if(result.error){console.error(result.error.message);process.exit(1);}
 if(result.status!==0)process.exit(result.status??1);
}
const particles=spawnSync(process.execPath,['tests/motion-particles.test.cjs'],{cwd,stdio:'inherit'});
if(particles.error){console.error(particles.error.message);process.exit(1);}
if(particles.status!==0)process.exit(particles.status??1);
