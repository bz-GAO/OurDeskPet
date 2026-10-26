//! DashScope 双工流式 ASR 的 run-task 协议。
//! 帧格式翻译自 dashscope Python SDK（RinaYaki venv 内 site-packages 的
//! audio/tts_v2/speech_synthesizer.py 与 protocol/websocket.py），模型与
//! Yaki live 保持同款。本文件只做纯构造/解析，网络在 session 任务里。

use serde::Deserialize;
use serde_json::{json, Value};

pub const MODEL: &str = "qwen-audio-3.0-asr-flash-streaming";
pub const CN_WEBSOCKET_URL: &str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference";
pub const INTL_WEBSOCKET_URL: &str = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference";

pub fn run_task_frame(task_id: &str) -> String {
    json!({
        "header": {
            "action": "run-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {
            "model": MODEL,
            "task_group": "audio",
            "task": "asr",
            "function": "recognition",
            "input": {},
            "parameters": {
                "format": "pcm",
                "sample_rate": 16000,
            },
        },
    })
    .to_string()
}

pub fn finish_task_frame(task_id: &str) -> String {
    json!({
        "header": {
            "action": "finish-task",
            "task_id": task_id,
            "streaming": "duplex",
        },
        "payload": {
            "input": {},
        },
    })
    .to_string()
}

/// 服务端下行事件。`Sentence` 的 `text` 是当前句的累计文本；
/// `is_final` 表示该句已断句结束（`end_time` 非 null）。
#[derive(Debug, PartialEq, Eq)]
pub enum ServerEvent {
    TaskStarted,
    Sentence { text: String, is_final: bool },
    TaskFinished,
    Failed { code: String, message: String },
    Ignored,
}

#[derive(Deserialize)]
struct DownFrame {
    header: DownHeader,
    payload: Option<Value>,
}

#[derive(Deserialize)]
struct DownHeader {
    event: Option<String>,
    #[serde(default)]
    error_code: String,
    #[serde(default)]
    error_message: String,
}

pub fn parse_server_event(text: &str) -> Result<ServerEvent, String> {
    let frame: DownFrame =
        serde_json::from_str(text).map_err(|_| "语音服务返回了无法解析的数据".to_string())?;
    match frame.header.event.as_deref() {
        Some("task-started") => Ok(ServerEvent::TaskStarted),
        Some("result-generated") => {
            let sentence = frame
                .payload
                .as_ref()
                .and_then(|payload| payload.get("output"))
                .and_then(|output| output.get("sentence"))
                .cloned()
                .unwrap_or(Value::Null);
            if sentence.get("heartbeat").and_then(Value::as_bool) == Some(true) {
                return Ok(ServerEvent::Ignored);
            }
            let Some(text) = sentence.get("text").and_then(Value::as_str) else {
                return Ok(ServerEvent::Ignored);
            };
            // SDK 判定：end_time 存在且非 null 即为断句结束。
            let is_final = sentence
                .get("end_time")
                .is_some_and(|value| !value.is_null());
            Ok(ServerEvent::Sentence {
                text: text.to_string(),
                is_final,
            })
        }
        Some("task-finished") => Ok(ServerEvent::TaskFinished),
        Some("task-failed") => Ok(ServerEvent::Failed {
            code: frame.header.error_code,
            message: if frame.header.error_message.is_empty() {
                "语音识别任务失败".into()
            } else {
                frame.header.error_message
            },
        }),
        _ => Ok(ServerEvent::Ignored),
    }
}

/// 由聊天 API 方案的 base_url 推断 ASR websocket 入口。
/// 仅认 DashScope 域名：key 是按方案复用的，别的服务商 key 无效，
/// 必须显式拒绝而不是回退到默认地址。
pub fn websocket_url_for_base_url(base_url: &str) -> Option<&'static str> {
    let Ok(url) = reqwest::Url::parse(base_url) else {
        return None;
    };
    match url.host_str() {
        Some("dashscope.aliyuncs.com") => Some(CN_WEBSOCKET_URL),
        Some("dashscope-intl.aliyuncs.com") => Some(INTL_WEBSOCKET_URL),
        _ => None,
    }
}

/// 维护"已断句文本 + 当前句部分文本"的显示状态。
#[derive(Default)]
pub struct Transcript {
    finalized: String,
    partial: String,
}

impl Transcript {
    pub fn push(&mut self, event: &ServerEvent) -> bool {
        match event {
            ServerEvent::Sentence { text, is_final } => {
                if *is_final {
                    self.finalized.push_str(text);
                    self.partial.clear();
                } else {
                    self.partial = text.clone();
                }
                true
            }
            _ => false,
        }
    }

    pub fn display(&self) -> String {
        let mut text = self.finalized.clone();
        text.push_str(&self.partial);
        text
    }

    pub fn has_final_text(&self) -> bool {
        !self.finalized.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frames_match_duplex_protocol_shape() {
        let run = serde_json::from_str::<Value>(&run_task_frame("tid-1")).unwrap();
        assert_eq!(run["header"]["action"], "run-task");
        assert_eq!(run["header"]["streaming"], "duplex");
        assert_eq!(run["payload"]["task"], "asr");
        assert_eq!(run["payload"]["function"], "recognition");
        assert_eq!(run["payload"]["parameters"]["format"], "pcm");
        assert_eq!(run["payload"]["parameters"]["sample_rate"], 16000);
        let finish = serde_json::from_str::<Value>(&finish_task_frame("tid-1")).unwrap();
        assert_eq!(finish["header"]["action"], "finish-task");
        assert_eq!(finish["header"]["task_id"], "tid-1");
    }

    #[test]
    fn parses_started_intermediate_final_and_failure() {
        assert_eq!(
            parse_server_event(r#"{"header":{"event":"task-started","task_id":"t"}}"#).unwrap(),
            ServerEvent::TaskStarted
        );
        let intermediate = parse_server_event(
            r#"{"header":{"event":"result-generated"},"payload":{"output":{"sentence":{"text":"你好","begin_time":0,"end_time":null}}}}"#,
        )
        .unwrap();
        assert_eq!(
            intermediate,
            ServerEvent::Sentence {
                text: "你好".into(),
                is_final: false
            }
        );
        let final_line = parse_server_event(
            r#"{"header":{"event":"result-generated"},"payload":{"output":{"sentence":{"text":"今天天气怎么样？","begin_time":0,"end_time":2340}}}}"#,
        )
        .unwrap();
        assert_eq!(
            final_line,
            ServerEvent::Sentence {
                text: "今天天气怎么样？".into(),
                is_final: true
            }
        );
        let failed = parse_server_event(
            r#"{"header":{"event":"task-failed","error_code":"InvalidApiKey","error_message":"Invalid API-key"}}"#,
        )
        .unwrap();
        assert!(matches!(failed, ServerEvent::Failed { code, .. } if code == "InvalidApiKey"));
        assert_eq!(
            parse_server_event(
                r#"{"header":{"event":"task-finished"},"payload":{"output":{"finished":true}}}"#
            )
            .unwrap(),
            ServerEvent::TaskFinished
        );
    }

    #[test]
    fn skips_heartbeat_and_textless_sentences() {
        let heartbeat = r#"{"header":{"event":"result-generated"},"payload":{"output":{"sentence":{"heartbeat":true}}}}"#;
        assert_eq!(parse_server_event(heartbeat).unwrap(), ServerEvent::Ignored);
        let empty = r#"{"header":{"event":"result-generated"},"payload":{"output":{"sentence":{"end_time":null}}}}"#;
        assert_eq!(parse_server_event(empty).unwrap(), ServerEvent::Ignored);
    }

    #[test]
    fn transcript_builds_display_from_finals_and_partial() {
        let mut transcript = Transcript::default();
        assert!(!transcript.push(&ServerEvent::TaskStarted));
        let sentence = |text: &str, is_final: bool| ServerEvent::Sentence {
            text: text.to_string(),
            is_final,
        };
        transcript.push(&sentence("打开", false));
        assert_eq!(transcript.display(), "打开");
        transcript.push(&sentence("打开 RinaYaki", false));
        assert_eq!(transcript.display(), "打开 RinaYaki");
        transcript.push(&sentence("打开 RinaYaki。", true));
        assert_eq!(transcript.display(), "打开 RinaYaki。");
        transcript.push(&sentence("翻译", false));
        assert_eq!(transcript.display(), "打开 RinaYaki。翻译");
        assert!(transcript.has_final_text());
    }

    #[test]
    fn websocket_url_only_accepts_dashscope_hosts() {
        assert_eq!(
            websocket_url_for_base_url("https://dashscope.aliyuncs.com/compatible-mode/v1"),
            Some(CN_WEBSOCKET_URL)
        );
        assert_eq!(
            websocket_url_for_base_url("https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
            Some(INTL_WEBSOCKET_URL)
        );
        assert_eq!(
            websocket_url_for_base_url("https://api.openai.com/v1"),
            None
        );
        assert_eq!(
            websocket_url_for_base_url("https://dashscope.example.com/v1"),
            None
        );
        assert_eq!(websocket_url_for_base_url("not a url"), None);
    }
}
