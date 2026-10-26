import {invoke, isTauri} from '@tauri-apps/api/core';

export type SfxEvent = 'notify' | 'teleport' | 'task_complete' | 'task_failed';

/** 事件音效：由后端按设置/reviewed 闸门决定是否真的出声；前端失败静默。 */
export function playSfx(event: SfxEvent) {
  if (!isTauri()) return;
  void invoke('voice_output_play', {event}).catch(() => {});
}
