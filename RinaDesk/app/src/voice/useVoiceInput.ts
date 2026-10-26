import {invoke, isTauri} from '@tauri-apps/api/core';
import {listen} from '@tauri-apps/api/event';
import {useCallback, useEffect, useState} from 'react';
import type {VoicePhase} from './voicePhase';

export type VoiceInputStatus = {supported: boolean; model: string; reason: string};

/**
 * 语音输入会话的前端侧：状态由后端事件驱动（voice-input-state/partial/final/error），
 * 本地只在发起动作时乐观置位。同一时间最多一个会话，由后端兜底拒绝。
 */
export function useVoiceInput() {
  const [status, setStatus] = useState<VoiceInputStatus | null>(null);
  const [phase, setPhase] = useState<VoicePhase>('idle');
  const [text, setText] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let disposed = false;
    const offs: Array<() => void> = [];
    async function setup() {
      if (!isTauri()) {
        if (!disposed) setStatus({supported: false, model: '', reason: '浏览器预览不支持语音输入。'});
        return;
      }
      const events: Array<[string, (payload: unknown) => void]> = [
        ['voice-input-state', payload => setPhase((payload as {phase: VoicePhase}).phase)],
        ['voice-input-partial', payload => setText((payload as {text: string}).text)],
        ['voice-input-final', payload => {
          setText((payload as {text: string}).text);
          setPhase('done');
        }],
        ['voice-input-error', payload => {
          setError((payload as {message: string}).message || '语音识别失败');
          setPhase('error');
        }],
      ];
      for (const [name, handler] of events) {
        const off = await listen(name, event => {
          if (!disposed) handler(event.payload);
        });
        if (disposed) off();
        else offs.push(off);
      }
      try {
        const next = await invoke<VoiceInputStatus>('voice_input_status');
        if (!disposed) setStatus(next);
      } catch (e) {
        if (!disposed) setStatus({supported: false, model: '', reason: String(e)});
      }
    }
    void setup().catch(e => {
      if (!disposed) setStatus({supported: false, model: '', reason: String(e)});
    });
    return () => {
      disposed = true;
      offs.forEach(off => off());
      if (isTauri()) void invoke('voice_input_cancel').catch(() => {});
    };
  }, []);

  const reset = useCallback(() => {
    setPhase('idle');
    setText('');
    setError('');
  }, []);

  const start = useCallback(async () => {
    setError('');
    setText('');
    setPhase('starting');
    try {
      await invoke('voice_input_start');
    } catch (e) {
      setPhase('idle');
      setError(String(e));
    }
  }, []);

  const stop = useCallback(async () => {
    setPhase('finishing');
    try {
      await invoke('voice_input_stop');
    } catch (e) {
      setPhase('idle');
      setError(String(e));
    }
  }, []);

  const cancel = useCallback(async () => {
    try {
      await invoke('voice_input_cancel');
    } catch {
      // 取消失败不需要提示：会话可能已自然结束。
    }
  }, []);

  return {status, phase, text, error, reset, start, stop, cancel};
}

export type VoiceInputApi = ReturnType<typeof useVoiceInput>;
