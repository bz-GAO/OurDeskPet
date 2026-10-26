import {build} from 'esbuild';
import {mkdtemp, rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp = await mkdtemp(path.resolve('node_modules/.tool-calls-test-'));
try {
  const file = path.join(temp, 'tools.mjs');
  await build({entryPoints: ['src/llm/toolCalls.ts'], outfile: file, bundle: true, platform: 'node', format: 'esm'});
  const {applyToolEvent, toolLabel} = await import(pathToFileURL(file));

  // running 追加，done 就地更新最后一个同名 running 条目
  let calls = applyToolEvent([], {name: 'tomo_status', state: 'running'});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].state, 'running');
  calls = applyToolEvent(calls, {name: 'tomo_status', state: 'done', detail: '完成'});
  assert.equal(calls.length, 1);
  assert.equal(calls[0].state, 'done');
  assert.equal(calls[0].detail, '完成');

  // 同名多次调用：终态只更新最后一个 running
  calls = applyToolEvent(calls, {name: 'yaki_status', state: 'running'});
  calls = applyToolEvent(calls, {name: 'tomo_status', state: 'running'});
  calls = applyToolEvent(calls, {name: 'tomo_status', state: 'error', detail: '失败'});
  assert.deepEqual(calls.map(call => call.state), ['done', 'running', 'error']);
  assert.equal(calls[2].detail, '失败');

  // 补收终态（无对应 running）时直接追加
  const late = applyToolEvent([], {name: 'desk_diagnostics', state: 'done'});
  assert.equal(late.length, 1);
  assert.equal(late[0].state, 'done');

  // 展示名映射：已知工具用中文，未知工具保留原名
  assert.equal(toolLabel('tomo_status'), 'Tomo 状态');
  assert.equal(toolLabel('yaki_status'), 'Yaki 状态');
  assert.equal(toolLabel('desk_diagnostics'), 'Desk 诊断');
  assert.equal(toolLabel('something_new'), 'something_new');
  console.log('tool-calls: all assertions passed');
} finally {
  await rm(temp, {recursive: true, force: true});
}
