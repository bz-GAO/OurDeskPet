export type Features = {ping: boolean; echo: boolean};
export type Permissions = {adminUsers: number[]; privateWhitelist: number[]; enabledGroups: number[]};
export type LoginState = {required: boolean; message: string; qrcodeDataUrl: string};
export type LlmUsage = {used: number; dailyLimit: number; remaining: number};
export type LlmSettings = {
  enabled: boolean; effectiveModel: string; minReplyInterval: number; timeoutSeconds: number;
  maxTokens: number; dailyTokenBudget: number; maxInputChars: number; maxConcurrentRequests: number;
  usage?: LlmUsage;
};
export type NotificationEvents = {translation: boolean; chatReply: boolean; loginFailure: boolean};
export type Notifications = {
  enabled: boolean; nightSleepEnabled: boolean; nightStart: string; nightEnd: string; events: NotificationEvents;
};
export type RinaTomoSnapshot = {
  protocolVersion: number; provider: string; available: boolean;
  owner: 'standalone' | 'desk' | null;
  napcat: string; qq: string; state: 'online' | 'offline'; running: boolean; paused: boolean;
  shuttingDown?: boolean; shutdownError?: string;
  login: LoginState; features: Features; llm: LlmSettings;
  permissions: Permissions; autoStart: boolean; notifications?: Notifications;
};
export type LlmDraft = {
  enabled: boolean; minReplyInterval: string; timeoutSeconds: string; maxTokens: string;
  dailyTokenBudget: string; maxInputChars: string; maxConcurrentRequests: string;
};
export type Draft = {
  features: Features; llm: LlmDraft; permissions: Record<keyof Permissions, string>; autoStart: boolean;
  notifications: Notifications;
};
export type Group = keyof Draft;
export const notificationsPreview: Notifications = {
  enabled: true, nightSleepEnabled: true, nightStart: '22:00', nightEnd: '08:00',
  events: {translation: true, chatReply: false, loginFailure: true},
};
export const preview: RinaTomoSnapshot = {
  protocolVersion: 1, provider: 'rinatomo', available: false,
  owner: null,
  napcat: '未连接', qq: '等待启动', state: 'offline', running: false, paused: false,
  shuttingDown: false, shutdownError: '',
  login: {required: false, message: '', qrcodeDataUrl: ''},
  features: {ping: true, echo: false},
  llm: {enabled: false, effectiveModel: '未配置', minReplyInterval: 0, timeoutSeconds: 30,
    maxTokens: 512, dailyTokenBudget: 200000, maxInputChars: 2000, maxConcurrentRequests: 2,
    usage: {used: 0, dailyLimit: 200000, remaining: 200000}},
  permissions: {adminUsers: [], privateWhitelist: [], enabledGroups: []}, autoStart: false,
  notifications: notificationsPreview,
};
export function serviceControls(snapshot: RinaTomoSnapshot) {
  const closing = snapshot.shuttingDown === true;
  const error = snapshot.shutdownError || '';
  return {
    closing, error,
    canStart: snapshot.available && !closing && !error,
    showShutdown: snapshot.available && (snapshot.running || closing || Boolean(error)),
    canShutdown: snapshot.available && !closing,
  };
}
export function fromSnapshot(value: RinaTomoSnapshot): Draft {
  const llm=value.llm??preview.llm;
  return {features: {ping: value.features.ping, echo: value.features.echo}, llm: {
    enabled: llm.enabled, minReplyInterval: String(llm.minReplyInterval), timeoutSeconds: String(llm.timeoutSeconds),
    maxTokens: String(llm.maxTokens), dailyTokenBudget: String(llm.dailyTokenBudget),
    maxInputChars: String(llm.maxInputChars), maxConcurrentRequests: String(llm.maxConcurrentRequests),
  }, permissions: {
    adminUsers: value.permissions.adminUsers.join(', '),
    privateWhitelist: value.permissions.privateWhitelist.join(', '),
    enabledGroups: value.permissions.enabledGroups.join(', '),
  }, autoStart: value.autoStart, notifications: value.notifications??notificationsPreview};
}
export function parseIds(value: string, label: string): number[] {
  const parts = value.trim() ? value.trim().split(/[\s,，;；]+/) : [];
  if (parts.some(part => !/^\d+$/.test(part))) throw new Error(`${label}只能填写正整数，用逗号或空格分隔。`);
  const ids = parts.map(Number);
  if (ids.some(id => !Number.isSafeInteger(id) || id <= 0)) throw new Error(`${label}包含无效的 QQ/群号。`);
  return [...new Set(ids)];
}
export function parseNonNegativeNumber(value: string, label: string): number {
  const result=Number(value);
  if(value.trim()===''||!Number.isFinite(result)||result<0)throw new Error(`${label}必须是大于或等于 0 的数字。`);
  return result;
}
export function parsePositiveInteger(value: string, label: string): number {
  const result=Number(value);
  if(!/^\d+$/.test(value.trim())||!Number.isSafeInteger(result)||result<1)throw new Error(`${label}必须是大于 0 的整数。`);
  return result;
}
export function parseNightTime(value: string, label: string): string {
  if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(value.trim()))throw new Error(`${label}必须是 HH:MM 的 24 小时制时间。`);
  return value.trim();
}
export function mergeDraft(current: Draft, incoming: RinaTomoSnapshot, dirty: Record<Group, boolean>): Draft {
  if (!incoming.available) return current;
  const next = fromSnapshot(incoming);
  return {
    features: dirty.features ? current.features : next.features,
    llm: dirty.llm ? current.llm : next.llm,
    permissions: dirty.permissions ? current.permissions : next.permissions,
    autoStart: dirty.autoStart ? current.autoStart : next.autoStart,
    notifications: dirty.notifications ? current.notifications : next.notifications,
  };
}
