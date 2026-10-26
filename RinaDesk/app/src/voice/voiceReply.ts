export type SpokenReply = {spoken: string; rest: string; hasVoice: boolean};

/**
 * 解析"语音结合回答"：模型按约定以 说出："口述内容" 开头，随后是展示文本。
 * 引号兼容全角 “” 与半角 ""（成对或混用）；未按格式（含空口述段）时
 * hasVoice=false，整条消息按普通文本渲染——永不因解析失败丢内容。
 */
export function parseSpokenReply(content: string): SpokenReply {
  const match = /^\s*说出[：:]\s*[“"]([\s\S]*?)[”"]\s*([\s\S]*)$/.exec(content);
  if (!match) return {spoken: '', rest: content, hasVoice: false};
  const spoken = match[1].trim();
  if (!spoken) return {spoken: '', rest: content, hasVoice: false};
  return {spoken, rest: match[2].trimStart(), hasVoice: true};
}
