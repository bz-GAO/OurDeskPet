import {build} from 'esbuild';
import {mkdtemp, rm} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const temp = await mkdtemp(path.resolve('node_modules/.voice-reply-test-'));
try {
  const file = path.join(temp, 'reply.mjs');
  await build({entryPoints: ['src/voice/voiceReply.ts'], outfile: file, bundle: true, platform: 'node', format: 'esm'});
  const {parseSpokenReply} = await import(pathToFileURL(file));

  // 标准格式：全角引号
  let parsed = parseSpokenReply('说出："后面的内容我展示给你。"\n\n## 详细说明\n正文……');
  assert.equal(parsed.hasVoice, true);
  assert.equal(parsed.spoken, '后面的内容我展示给你。');
  assert.equal(parsed.rest, '## 详细说明\n正文……');

  // 半角引号 + 冒号变体
  parsed = parseSpokenReply('说出:"好的，马上看。"\n正文');
  assert.equal(parsed.hasVoice, true);
  assert.equal(parsed.spoken, '好的，马上看。');
  assert.equal(parsed.rest, '正文');

  // 无展示文本（口述即全部）
  parsed = parseSpokenReply('说出："没问题。"\n');
  assert.equal(parsed.hasVoice, true);
  assert.equal(parsed.rest, '');

  // 未按格式：整体降级纯文本，不丢内容
  parsed = parseSpokenReply('你好，这里是普通回复。');
  assert.equal(parsed.hasVoice, false);
  assert.equal(parsed.rest, '你好，这里是普通回复。');
  parsed = parseSpokenReply('说出：没有引号的口述');
  assert.equal(parsed.hasVoice, false);
  parsed = parseSpokenReply('语音说："没有说出前缀"');
  assert.equal(parsed.hasVoice, false);

  // 空口述段：降级
  parsed = parseSpokenReply('说出：""\n正文');
  assert.equal(parsed.hasVoice, false);
  assert.equal(parsed.rest, '说出：""\n正文');

  // 引号内的引号（非贪婪到第一个闭引号）
  parsed = parseSpokenReply('说出："说\'引号\'测试"正文');
  assert.equal(parsed.spoken, "说'引号'测试");
  assert.equal(parsed.rest, '正文');
  console.log('voice-reply: all assertions passed');
} finally {
  await rm(temp, {recursive: true, force: true});
}
