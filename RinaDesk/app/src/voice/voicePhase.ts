export type VoicePhase = 'idle'|'starting'|'recording'|'finishing'|'done'|'error';
export type VoicePrimaryKind = 'start'|'stop'|'send'|'none';
export type VoicePrimary = {label: string; kind: VoicePrimaryKind; disabled: boolean};

/**
 * 语音弹窗右下角主按钮的三态推进：开始录音 → 停止录音 → 发送。
 * 空结果（没说话）与出错都回到"开始录音"；连接与整理阶段禁用等待。
 */
export function voicePrimary(phase: VoicePhase, hasText: boolean): VoicePrimary {
  switch (phase) {
    case 'idle':
      return {label: '开始录音', kind: 'start', disabled: false};
    case 'starting':
      return {label: '连接中…', kind: 'none', disabled: true};
    case 'recording':
      return {label: '停止录音', kind: 'stop', disabled: false};
    case 'finishing':
      return {label: '整理中…', kind: 'none', disabled: true};
    case 'done':
      return hasText
        ? {label: '发送', kind: 'send', disabled: false}
        : {label: '开始录音', kind: 'start', disabled: false};
    case 'error':
      return {label: '开始录音', kind: 'start', disabled: false};
  }
}

/** 弹窗中间的提示行；录音/空闲共用"单击开始或结束对话"。 */
export function voiceHint(phase: VoicePhase, hasText: boolean, error: string): string {
  if (phase === 'error') return error || '语音识别失败，请重试';
  if (phase === 'finishing') return '正在整理识别结果…';
  if (phase === 'done') return hasText ? '识别完成，确认后发送' : '没听到内容，再试一次';
  return '单击开始或结束对话';
}
