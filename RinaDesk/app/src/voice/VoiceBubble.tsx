import {useRef, useState} from 'react';

/**
 * 语音结合回答的气泡：微信/QQ 语音消息式——不自动播放，点击播放，
 * 对应口述文字默认渲染在旁边（语音内容本就同屏可见，不搞按住 reveal）。
 */
export function VoiceBubble({voice}: {voice: {dataUrl: string; text: string}}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  function toggle() {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    }
  }
  return (
    <div className={`voice-bubble${playing ? ' is-playing' : ''}`}>
      <button type="button" className="voice-bubble-play" onClick={toggle} aria-label={playing ? '停止播放' : '播放语音'}>
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="voice-bubble-wave" aria-hidden="true">
        {[10, 16, 22, 16, 10].map((height, index) => <span key={index} style={{height}}/>)}
      </div>
      <p className="voice-bubble-text">{voice.text}</p>
      <audio ref={audioRef} src={voice.dataUrl} onEnded={() => setPlaying(false)} onPause={() => setPlaying(false)}/>
    </div>
  );
}
