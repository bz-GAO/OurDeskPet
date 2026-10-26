import {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {voiceHint, voicePrimary} from './voicePhase';
import type {VoiceInputApi} from './useVoiceInput';
import './voice.css';

/**
 * 语音输入弹窗：复用 ConfirmDialog 的结构与视觉（原生 dialog + portal）。
 * 中间提示行 + 实时识别文本；左下取消，右下主按钮三态推进。
 */
export function VoiceDialog({voice, onSend, onClose}: {voice: VoiceInputApi; onSend: (text: string, combined: boolean) => void; onClose: () => void}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [combined, setCombined] = useState(false);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const node = ref.current;
    node?.showModal();
    return () => {
      node?.close();
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  const hasText = voice.text.trim().length > 0;
  const primary = voicePrimary(voice.phase, hasText);
  const hint = voiceHint(voice.phase, hasText, voice.error);

  function handlePrimary() {
    if (primary.kind === 'start') void voice.start();
    else if (primary.kind === 'stop') void voice.stop();
    else if (primary.kind === 'send') onSend(voice.text.trim(), combined);
  }

  return createPortal(
    <dialog
      ref={ref}
      className="rina-confirm-dialog voice-dialog"
      role="dialog"
      aria-label="语音输入"
      onCancel={event => {
        event.preventDefault();
        onClose();
      }}
    >
      <h2>语音输入</h2>
      <div className="rina-confirm-body voice-body">
        <p className="voice-hint" data-phase={voice.phase}>{hint}</p>
        <div className="voice-transcript" aria-live="polite" data-phase={voice.phase}>
          {voice.text || (voice.phase === 'recording' || voice.phase === 'finishing' ? '…' : '')}
        </div>
        {voice.error ? <p className="voice-error" role="alert">{voice.error}</p> : null}
        <label className="voice-combined">
          <input type="checkbox" checked={combined} onChange={event => setCombined(event.target.checked)}/>
          语音结合回答（回复开头先口述一段，详情照常展示）
        </label>
      </div>
      <div className="rina-confirm-actions voice-actions">
        <button type="button" onClick={onClose}>取消</button>
        <button
          type="button"
          className="voice-primary"
          data-phase={voice.phase}
          disabled={primary.disabled}
          onClick={handlePrimary}
        >
          {primary.label}
        </button>
      </div>
    </dialog>,
    document.body
  );
}
