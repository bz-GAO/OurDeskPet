import {build} from 'esbuild';
import {mkdtemp, rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp = await mkdtemp(path.resolve('node_modules/.agent-tasks-test-'));
try {
  const file = path.join(temp, 'tasks.mjs');
  await build({entryPoints: ['src/llm/agentTasks.ts'], outfile: file, bundle: true, platform: 'node', format: 'esm'});
  const {applyProposalEvent, applyTaskEvent, phaseLabel, durationLabel, progressInfo, isTerminalPhase} = await import(pathToFileURL(file));

  // 提案事件：追加待确认卡；同 id 幂等
  let cards = applyProposalEvent([], {requestId: 'r', proposalId: 'p1', url: 'https://v.test/1'});
  assert.equal(cards.length, 1);
  assert.equal(cards[0].phase, 'confirm');
  cards = applyProposalEvent(cards, {requestId: 'r', proposalId: 'p1', url: 'https://v.test/1'});
  assert.equal(cards.length, 1);

  // ready 事件就地更新同一张卡
  cards = applyTaskEvent(cards, {proposalId: 'p1', phase: 'ready', title: '示例视频', duration: 600, estimate: '转写约 ¥0.13'});
  assert.equal(cards.length, 1);
  assert.equal(cards[0].title, '示例视频');
  assert.equal(cards[0].phase, 'ready');

  // 启动后按 jobPath 匹配（轮询事件没有 proposalId），且不冲掉原 proposalId
  cards = applyTaskEvent(cards, {proposalId: 'p1', phase: 'running', jobPath: '/runs/job1', status: 'running'});
  cards = applyTaskEvent(cards, {jobPath: '/runs/job1', phase: 'running', status: 'running', detail: 'downloading'});
  assert.equal(cards.length, 1);
  assert.equal(cards[0].proposalId, 'p1');
  assert.equal(cards[0].detail, 'downloading');
  assert.equal(cards[0].title, '示例视频');

  // 终态：awaiting_style / failed / declined / complete
  assert.equal(isTerminalPhase(cards[0]), false);
  cards = applyTaskEvent(cards, {jobPath: '/runs/job1', phase: 'awaiting_style'});
  assert.equal(cards[0].phase, 'awaiting_style');
  assert.equal(phaseLabel(cards[0]), '翻译完成');
  assert.equal(progressInfo(cards[0]), null);
  cards = applyTaskEvent(cards, {jobPath: '/runs/job1', phase: 'complete'});
  assert.equal(phaseLabel(cards[0]), '导出完成');
  assert.equal(isTerminalPhase(cards[0]), true);
  cards = applyTaskEvent(cards, {jobPath: '/runs/job1', phase: 'failed', status: 'download_error'});
  assert.ok(phaseLabel(cards[0]).includes('download_error'));

  // 进度条模型：measured 阶段带百分比；非 measured 阶段 0%；未知阶段不定态
  const running = {...cards[0], phase: 'running', stage: 'download', completed: 50, total: 200};
  assert.deepEqual(progressInfo(running), {label: '读取视频 25%', percent: 25});
  const translating = {...cards[0], phase: 'running', stage: 'translation', completed: 3, total: 10};
  assert.equal(progressInfo(translating)?.percent, 30);
  const asr = {...cards[0], phase: 'running', stage: 'asr'};
  assert.deepEqual(progressInfo(asr), {label: '识别语音 · 处理中', percent: null});
  const unknown = {...cards[0], phase: 'running', stage: '', detail: ''};
  assert.deepEqual(progressInfo(unknown), {label: '处理中', percent: null});
  const noTotal = {...cards[0], phase: 'running', stage: 'download', completed: 5};
  assert.equal(progressInfo(noTotal)?.percent, null);

  // 不匹配任何卡且无 proposalId 的噪声事件：原样返回
  const untouched = applyTaskEvent(cards, {jobPath: '/runs/other', phase: 'running'});
  assert.equal(untouched.length, cards.length);
  assert.equal(untouched[0].jobPath, '/runs/job1');

  // 时长文案
  assert.equal(durationLabel(600), '10 分钟');
  assert.equal(durationLabel(75), '1 分 15 秒');
  assert.equal(durationLabel(8), '8 秒');
  assert.equal(durationLabel(undefined), '');
  console.log('agent-tasks: all assertions passed');
} finally {
  await rm(temp, {recursive: true, force: true});
}
