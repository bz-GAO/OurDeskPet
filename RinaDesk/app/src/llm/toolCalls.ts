export type ToolCallState = 'running'|'done'|'error';
export type MessageToolCall = {name: string; state: ToolCallState; detail?: string};
export type ToolCallEvent = {requestId: string; name: string; state: ToolCallState; detail?: string};

const LABELS: Record<string, string> = {
  desk_diagnostics: 'Desk 诊断',
  tomo_status: 'Tomo 状态',
  yaki_status: 'Yaki 状态',
};

export function toolLabel(name: string): string {
  return LABELS[name] ?? name;
}

/**
 * 把一次 llm-chat-tool 事件归并进当前消息的工具调用列表：
 * running 追加条目；done/error 就地更新最后一个同名 running 条目，
 * 若找不到（如窗口重开后补收）则直接追加终态。
 */
export function applyToolEvent(calls: readonly MessageToolCall[], event: Pick<ToolCallEvent, 'name'|'state'|'detail'>): MessageToolCall[] {
  if (event.state === 'running') {
    return [...calls, {name: event.name, state: 'running'}];
  }
  const index = [...calls].reverse().findIndex(call => call.name === event.name && call.state === 'running');
  if (index < 0) {
    return [...calls, {name: event.name, state: event.state, detail: event.detail}];
  }
  const target = calls.length - 1 - index;
  return calls.map((call, position) =>
    position === target ? {...call, state: event.state, detail: event.detail} : call
  );
}
