export type TaskEvent = {source: string; taskId: string; status: 'started' | 'completed' | 'cancelled' | 'failed'};
export type NoticeState = {phase: 'idle' | 'notifying' | 'unread'; unread: number};
export const NOTICE_DURATION = 2400;
export interface NoticePorts {
  isReading(source: string): Promise<boolean>;
  reveal(): Promise<void>;
  attention(active: boolean): Promise<void>;
  changed(state: NoticeState): void;
  schedule(callback: () => void, ms: number): () => void;
}

/** Notification state is orthogonal to pet art/behaviour and panel interaction. */
export class NotificationController {
  private unread = new Map<string, string>();
  private seen = new Set<string>();
  private phase: NoticeState['phase'] = 'idle';
  private cancelTimer?: () => void;
  private generation = 0;
  private disposed = false;
  constructor(private ports: NoticePorts) {}
  private publish() { this.ports.changed({phase:this.phase, unread:this.unread.size}); }
  async receive(event: TaskEvent) {
    if (this.disposed || !event || typeof event.source !== 'string' || typeof event.taskId !== 'string') return;
    const key = JSON.stringify([event.source,event.taskId]);
    if (event.status === 'started' || this.seen.has(key)) return;
    if (!['completed','cancelled','failed'].includes(event.status)) return;
    this.seen.add(key);
    // Bound lifetime bookkeeping; recent terminal events remain idempotent.
    if (this.seen.size > 512) this.seen.delete(this.seen.values().next().value!);
    if (event.status !== 'completed') return;
    const generation = this.generation;
    if (await this.ports.isReading(event.source)) return;
    if (this.disposed || generation !== this.generation) return;
    this.unread.set(key,event.source);
    if (this.phase === 'notifying') { this.publish(); return; }
    this.phase = 'notifying';
    this.publish();
    await this.ports.reveal();
    if (this.disposed || generation !== this.generation) return;
    this.cancelTimer = this.ports.schedule(()=>{ void this.finish(generation); },NOTICE_DURATION);
  }
  /** Hiding a popup never means the response has been read. */
  dismiss() {
    ++this.generation;
    this.cancelTimer?.(); this.cancelTimer=undefined;
    this.phase=this.unread.size ? 'unread' : 'idle';
    this.publish();
  }
  acknowledge(source: string) {
    for(const [key,itemSource] of this.unread) if(itemSource===source) this.unread.delete(key);
    if(!this.unread.size) {
      this.dismiss();
      void this.ports.attention(false);
    } else this.publish();
  }
  private async finish(generation: number) {
    // Recheck at the deadline: the user may have opened the dialogue during the pulse.
    for(const source of new Set(this.unread.values())) {
      if(await this.ports.isReading(source)) this.acknowledge(source);
    }
    if(this.disposed || generation!==this.generation || !this.unread.size) return;
    this.phase='unread'; this.publish();
    // The pet stays visible; only the notification panel returns to its collapsed state.
    if(!this.disposed && generation===this.generation) await this.ports.attention(true);
  }
  dispose() { this.disposed=true; ++this.generation; this.cancelTimer?.(); }
}
