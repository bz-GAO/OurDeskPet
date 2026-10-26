export type AgentTaskPhase = 'confirm'|'ready'|'running'|'awaiting_style'|'complete'|'failed'|'declined';
export type AgentTaskCard = {
  proposalId: string;
  phase: AgentTaskPhase;
  url: string;
  title?: string;
  duration?: number;
  estimate?: string;
  suggestedName?: string;
  defaultParent?: string;
  thumbnail?: string;
  qualityLabel?: string;
  jobPath?: string;
  status?: string;
  detail?: string;
  stage?: string;
  completed?: number;
  total?: number;
};
export type AgentProposalEvent = {requestId: string; proposalId: string; url: string};

export function durationLabel(seconds?: number): string {
  if (!seconds || seconds <= 0) return '';
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return minutes > 0 ? (rest > 0 ? `${minutes} 分 ${rest} 秒` : `${minutes} 分钟`) : `${rest} 秒`;
}

/** 扩展页同一套阶段表；measured 阶段有可测百分比。 */
const STAGES: ReadonlyArray<readonly [string, string]> = [
  ['download', '读取视频'],
  ['audio', '提取音频'],
  ['asr', '识别语音'],
  ['translation', '翻译字幕'],
  ['refinement', '校对字幕'],
  ['export_and_mux', '生成成片'],
];
const MEASURED = new Set(['download', 'translation', 'refinement']);

export function phaseLabel(card: Pick<AgentTaskCard, 'phase'|'detail'|'status'>): string {
  switch (card.phase) {
    case 'confirm': return '等待确认';
    case 'ready': return '待开始';
    case 'running': return card.detail || '翻译进行中…';
    case 'awaiting_style': return '翻译完成';
    case 'complete': return '导出完成';
    case 'failed': return `失败（${card.status || '未知原因'}），可到 Yaki 扩展页重试`;
    case 'declined': return '已取消';
  }
}

/** 进度条信息：label 为当前阶段中文，percent 为 0-100（无可测值时 null=不定态动画）。 */
export function progressInfo(card: AgentTaskCard): {label: string; percent: number | null} | null {
  if (card.phase !== 'running') return null;
  const stage = card.stage || card.detail || '';
  const index = STAGES.findIndex(([key]) => key === stage);
  const label = index >= 0 ? STAGES[index][1] : (stage || '处理中');
  const measured = MEASURED.has(stage);
  if (measured && card.total && card.total > 0 && typeof card.completed === 'number') {
    const percent = Math.min(100, Math.max(0, Math.round((100 * card.completed) / card.total)));
    return {label: `${label} ${percent}%`, percent};
  }
  // 非 measured 阶段或暂无总量：一律不定态动画，避免出现静止的 0%。
  return {label: index >= 0 ? `${label} · 处理中` : label, percent: null};
}

/** 模型创建提案：追加一张待确认卡（同 id 幂等）。 */
export function applyProposalEvent(cards: readonly AgentTaskCard[], event: AgentProposalEvent): AgentTaskCard[] {
  if (cards.some(card => card.proposalId === event.proposalId)) return [...cards];
  return [...cards, {proposalId: event.proposalId, phase: 'confirm', url: event.url}];
}

/** 任务事件/轮询结果合并：优先 proposalId 匹配，运行后按 jobPath 匹配；
 * 字段就地覆盖但保留原 proposalId，防止轮询事件把它冲掉。 */
export function applyTaskEvent(
  cards: readonly AgentTaskCard[],
  payload: Partial<AgentTaskCard> & {proposalId?: string; jobPath?: string}
): AgentTaskCard[] {
  const index = cards.findIndex(card =>
    (payload.proposalId && card.proposalId === payload.proposalId) ||
    (payload.jobPath && card.jobPath === payload.jobPath)
  );
  if (index < 0) {
    if (!payload.proposalId || !payload.phase) return cards as AgentTaskCard[];
    return [...cards, {...payload, url: payload.url ?? ''} as AgentTaskCard];
  }
  // 无匹配变化的噪声事件保持原引用，避免上层无意义重渲染。
  const matched = cards[index];
  const unchanged = Object.entries(payload).every(([key, value]) =>
    key === 'proposalId' ? matched.proposalId === value : (matched as Record<string, unknown>)[key] === value
  );
  if (unchanged) return cards as AgentTaskCard[];
  return cards.map((card, position) =>
    position === index ? {...card, ...payload, proposalId: card.proposalId} : card
  );
}

/** 终态判定：轮询循环据此停表。 */
export function isTerminalPhase(card: AgentTaskCard): boolean {
  return card.phase === 'awaiting_style' || card.phase === 'complete' || card.phase === 'failed' || card.phase === 'declined';
}
