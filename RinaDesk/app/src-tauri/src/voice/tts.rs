//! 发布版语音回答：Qwen Audio 3.1 Plus + 官方系统音色。
//! 使用 SpeechSynthesizer 协议；不读取或分发作者私人克隆音色。
//! 非实时合成响应直接带 base64 音频（wav 24kHz）；若只返回 URL（24h 有效）
//! 则当场下载转存，绝不把短时效 URL 交给前端。

use serde_json::{json, Value};
use futures_util::StreamExt;
use std::time::Duration;
use tauri::AppHandle;

pub const TTS_MODEL: &str = "qwen-audio-3.1-tts-plus";
pub const DEFAULT_VOICE: &str = "longanlingxin_v3.1";
const REQUEST_TIMEOUT: Duration = Duration::from_secs(45);
const MAX_AUDIO_BYTES: usize = 10 * 1024 * 1024;

fn trusted_audio_url(value: &str) -> Option<reqwest::Url> {
    let url = reqwest::Url::parse(value).ok()?;
    let host = url.host_str()?.to_ascii_lowercase();
    (url.scheme() == "https" && (host == "aliyuncs.com" || host.ends_with(".aliyuncs.com")))
        .then_some(url)
}

/// 由聊天 API 方案的主机推导非实时 TTS 端点。仅认 DashScope 域名。
pub fn http_endpoint_for_base_url(base_url: &str) -> Option<String> {
    let Ok(url) = reqwest::Url::parse(base_url) else {
        return None;
    };
    if url.scheme() != "https" || url.port_or_known_default() != Some(443)
        || !url.username().is_empty() || url.password().is_some() {
        return None;
    }
    match url.host_str() {
        Some("dashscope.aliyuncs.com") => {
            Some("https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer".into())
        }
        Some("dashscope-intl.aliyuncs.com") => {
            Some("https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer".into())
        }
        Some(host) if [".cn-beijing.maas.aliyuncs.com", ".ap-southeast-1.maas.aliyuncs.com"].iter().any(|suffix| {
            host.strip_suffix(*suffix).is_some_and(|workspace| !workspace.is_empty() && workspace.bytes().all(|byte| byte.is_ascii_alphanumeric() || byte == b'-'))
        }) => Some(format!("https://{host}/api/v1/services/audio/tts/SpeechSynthesizer")),
        _ => None,
    }
}

/// 解析结果：内联 base64（非流式）或需要下载的 URL（短时效，必须当场转存）。
pub enum TtsAudio {
    Inline(String),
    Remote(String),
}

fn wav_data_url(bytes: &[u8]) -> String {
    let mut audio=bytes.to_vec();
    // Some streaming WAV encoders leave sentinel chunk lengths in the completed
    // response. Finalize those lengths before browser playback and persistence.
    if audio.len()>=12 && &audio[..4]==b"RIFF" && &audio[8..12]==b"WAVE" {
        let riff_length=(audio.len()-8) as u32;
        audio[4..8].copy_from_slice(&riff_length.to_le_bytes());
        let mut offset=12usize;
        while offset+8<=audio.len() {
            let length=u32::from_le_bytes(audio[offset+4..offset+8].try_into().unwrap()) as usize;
            if &audio[offset..offset+4]==b"data" {
                if length>audio.len()-offset-8 {
                    let actual=(audio.len()-offset-8) as u32;
                    audio[offset+4..offset+8].copy_from_slice(&actual.to_le_bytes());
                }
                break;
            }
            let Some(next)=offset.checked_add(8).and_then(|value|value.checked_add(length)).and_then(|value|value.checked_add(length%2)) else {break;};
            offset=next;
        }
    }
    use base64::Engine as _;
    format!("data:audio/wav;base64,{}",base64::engine::general_purpose::STANDARD.encode(audio))
}

/// 从响应中提取音频。非流式返回 `output.audio.data`（base64 wav）；
/// 若只有 `output.audio.url`（24h 时效）则返回 Remote 由调用方下载。
pub fn parse_tts_audio(value: &Value) -> Result<TtsAudio, String> {
    if value.get("output").is_none() {
        let message = value
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("语音合成响应缺少音频");
        return Err(format!("语音合成失败：{message}"));
    }
    let audio = value
        .pointer("/output/audio")
        .ok_or_else(|| "语音合成响应缺少音频".to_string())?;
    if let Some(data) = audio
        .get("data")
        .and_then(Value::as_str)
        .filter(|d| !d.is_empty())
    {
        // Check both encoded and decoded sizes before persisting the data URL in chat history.
        if data.len() > MAX_AUDIO_BYTES.saturating_mul(4) / 3 + 8 {
            return Err("语音合成返回的音频过大".into());
        }
        use base64::Engine as _;
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(data)
            .map_err(|_| "语音合成返回的音频编码无效".to_string())?;
        if decoded.len() > MAX_AUDIO_BYTES {
            return Err("语音合成返回的音频过大".into());
        }
        return Ok(TtsAudio::Inline(wav_data_url(&decoded)));
    }
    if let Some(url) = audio
        .get("url")
        .and_then(Value::as_str)
        .filter(|u| !u.is_empty())
    {
        return trusted_audio_url(url)
            .map(|url| TtsAudio::Remote(url.to_string()))
            .ok_or_else(|| "语音合成返回的音频地址不安全".into());
    }
    Err("语音合成响应不含音频数据".into())
}

fn tts_voice(_app: &AppHandle) -> String {
    DEFAULT_VOICE.into()
}

#[tauri::command]
pub async fn voice_reply_synthesize(app: AppHandle, text: String) -> Result<Value, String> {
    let text = text.trim().to_string();
    if text.is_empty() {
        return Err("口述段为空，跳过语音合成。".into());
    }
    if text.chars().count() > 600 {
        return Err("口述段超出 600 字符，跳过语音合成。".into());
    }
    let resolved = crate::api_profiles::resolve(Some(&app))?;
    let key = resolved
        .key
        .filter(|key| !key.trim().is_empty())
        .ok_or_else(|| "请先在设置中配置 API。".to_string())?;
    let endpoint = http_endpoint_for_base_url(&resolved.url)
        .ok_or_else(|| "语音回答需要阿里云百炼方案（同语音输入）。".to_string())?;
    let voice = tts_voice(&app);
    let payload = json!({
        "model": TTS_MODEL,
        "input": {"text": text, "voice": voice, "format": "wav", "sample_rate": 24000, "rate": 1.0},
    });
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .timeout(REQUEST_TIMEOUT)
        .build()
        .map_err(|_| "语音合成网络初始化失败".to_string())?;
    let response = client
        .post(&endpoint)
        .header("Authorization", format!("Bearer {key}"))
        .header("Content-Type", "application/json")
        .json(&payload)
        .send()
        .await
        .map_err(|error| format!("语音合成请求失败：{error}"))?;
    let status = response.status();
    let value: Value = response
        .json()
        .await
        .map_err(|_| "语音合成响应无法解析".to_string())?;
    if !status.is_success() {
        let message = value
            .get("message")
            .and_then(Value::as_str)
            .unwrap_or("请检查配置、额度或网络连接。");
        return Err(format!(
            "语音合成失败（HTTP {}）：{message}",
            status.as_u16()
        ));
    }
    let audio = match parse_tts_audio(&value)? {
        TtsAudio::Inline(data_url) => data_url,
        TtsAudio::Remote(url) => {
            let response = client
                .get(&url)
                .timeout(REQUEST_TIMEOUT)
                .send()
                .await
                .map_err(|_| "语音音频下载失败".to_string())?
                .error_for_status()
                .map_err(|_| "语音音频下载失败".to_string())?;
            if response
                .content_length()
                .is_some_and(|size| size > MAX_AUDIO_BYTES as u64)
            {
                return Err("语音音频超过 10 MB，已拒绝保存".into());
            }
            let mut stream=response.bytes_stream();
            let mut bytes=Vec::new();
            while let Some(chunk)=stream.next().await {
                let chunk=chunk.map_err(|_| "语音音频下载失败".to_string())?;
                if bytes.len().saturating_add(chunk.len())>MAX_AUDIO_BYTES {
                    return Err("语音音频超过 10 MB，已拒绝保存".into());
                }
                bytes.extend_from_slice(&chunk);
            }
            wav_data_url(&bytes)
        }
    };
    Ok(json!({"dataUrl": audio, "voice": voice, "model": TTS_MODEL}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn completed_streaming_wav_has_final_chunk_lengths() {
        use base64::Engine as _;
        let source=b"RIFF\xff\xff\xff\xffWAVEdata\xff\xff\xff\xff\x01\x02\x03\x04";
        let url=wav_data_url(source);
        let bytes=base64::engine::general_purpose::STANDARD.decode(url.strip_prefix("data:audio/wav;base64,").unwrap()).unwrap();
        assert_eq!(&bytes[4..8],&16u32.to_le_bytes());
        assert_eq!(&bytes[16..20],&4u32.to_le_bytes());
        assert_eq!(&bytes[20..],&[1,2,3,4]);
    }

    #[test]
    fn endpoint_only_accepts_dashscope_hosts() {
        assert!(
            http_endpoint_for_base_url("https://dashscope.aliyuncs.com/compatible-mode/v1")
                .is_some_and(
                    |url| url.contains("/api/v1/services/audio/tts/SpeechSynthesizer")
                )
        );
        assert!(http_endpoint_for_base_url(
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
        .is_some());
        assert!(http_endpoint_for_base_url("https://api.openai.com/v1").is_none());
        assert!(http_endpoint_for_base_url("http://dashscope.aliyuncs.com").is_none());
        assert!(http_endpoint_for_base_url("https://secret@dashscope.aliyuncs.com").is_none());
        assert!(http_endpoint_for_base_url("https://example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1").is_some());
        assert!(http_endpoint_for_base_url("https://example.cn-beijing.maas.aliyuncs.com.evil.test").is_none());
        assert!(http_endpoint_for_base_url("not a url").is_none());
    }

    #[test]
    fn parse_tts_audio_extracts_base64_or_remote() {
        let response = json!({
            "output": {"audio": {"data": "QUJD", "url": "", "id": "a1"}, "finish_reason": "stop"},
            "usage": {"characters": 42}
        });
        assert!(matches!(
            parse_tts_audio(&response),
            Ok(TtsAudio::Inline(data)) if data == "data:audio/wav;base64,QUJD"
        ));
        let remote = json!({"output": {"audio": {"data": "", "url": "https://dashscope-result.oss-cn-shanghai.aliyuncs.com/a.wav"}}});
        assert!(matches!(
            parse_tts_audio(&remote),
            Ok(TtsAudio::Remote(url)) if url == "https://dashscope-result.oss-cn-shanghai.aliyuncs.com/a.wav"
        ));
        let insecure = json!({"output": {"audio": {"url": "http://oss.example/a.wav"}}});
        assert!(parse_tts_audio(&insecure).is_err());
        let foreign = json!({"output": {"audio": {"url": "https://example.com/a.wav"}}});
        assert!(parse_tts_audio(&foreign).is_err());
        let invalid_base64 = json!({"output": {"audio": {"data": "not-base64"}}});
        assert!(parse_tts_audio(&invalid_base64).is_err());
        let failed = json!({"code":"InvalidApiKey","message":"bad key"});
        assert!(parse_tts_audio(&failed).is_err());
        let empty = json!({"output": {"audio": {"data": "", "url": ""}}});
        assert!(parse_tts_audio(&empty).is_err());
    }
}
