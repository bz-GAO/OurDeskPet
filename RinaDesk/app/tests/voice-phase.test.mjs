import {build} from 'esbuild';
import {mkdtemp, rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp = await mkdtemp(path.resolve('node_modules/.voice-phase-test-'));
try {
  const file = path.join(temp, 'phase.mjs');
  await build({entryPoints: ['src/voice/voicePhase.ts'], outfile: file, bundle: true, platform: 'node', format: 'esm'});
  const {voicePrimary, voiceHint} = await import(pathToFileURL(file));

  // 三态推进：开始录音 → 停止录音 → 发送
  assert.deepEqual(voicePrimary('idle', false), {label: '开始录音', kind: 'start', disabled: false});
  assert.deepEqual(voicePrimary('recording', true), {label: '停止录音', kind: 'stop', disabled: false});
  assert.deepEqual(voicePrimary('done', true), {label: '发送', kind: 'send', disabled: false});

  // 等待阶段禁用、无动作
  assert.equal(voicePrimary('starting', false).disabled, true);
  assert.equal(voicePrimary('starting', false).kind, 'none');
  assert.equal(voicePrimary('finishing', true).kind, 'none');
  assert.equal(voicePrimary('finishing', true).disabled, true);

  // 空结果与出错都回到开始录音，不出现发送
  assert.deepEqual(voicePrimary('done', false), {label: '开始录音', kind: 'start', disabled: false});
  assert.deepEqual(voicePrimary('error', true), {label: '开始录音', kind: 'start', disabled: false});

  // 提示行
  assert.equal(voiceHint('idle', false, ''), '单击开始或结束对话');
  assert.equal(voiceHint('recording', false, ''), '单击开始或结束对话');
  assert.equal(voiceHint('finishing', false, ''), '正在整理识别结果…');
  assert.equal(voiceHint('done', true, ''), '识别完成，确认后发送');
  assert.equal(voiceHint('done', false, ''), '没听到内容，再试一次');
  assert.equal(voiceHint('error', false, '密钥无效'), '密钥无效');
  console.log('voice-phase: all assertions passed');
} finally {
  await rm(temp, {recursive: true, force: true});
}
