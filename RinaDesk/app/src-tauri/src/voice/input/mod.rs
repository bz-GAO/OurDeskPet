//! 语音输入会话：麦克风采集 → DashScope 流式 ASR → 事件推给前端。
//! 同一时间只允许一个会话；停止（finish-task）后等待服务端收尾，
//! 取消则直接丢弃。60 秒自动收尾防失控。

mod asr;
mod capture;
mod resample;

use capture::MicrophoneHandle;
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use std::collections::VecDeque;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tokio::sync::mpsc;
use tokio::time::Instant;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::http::HeaderValue;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, WebSocketStream};

use resample::Resampler;

const MAX_RECORDING_SECONDS: u64 = 60;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
const FINISH_TIMEOUT: Duration = Duration::from_secs(8);
/// 一次发送的最小样本数（16kHz 下约 100ms，服务端推荐节奏）。
const SEND_CHUNK_SAMPLES: usize = 1600;
const TICK: Duration = Duration::from_millis(20);

type ClientStream = WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;
type WsSink = futures_util::stream::SplitSink<ClientStream, Message>;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct VoiceInputStatus {
    supported: bool,
    model: String,
    reason: String,
}

enum SessionCommand {
    /// 正常收尾：finish-task 后等最终结果。
    Finish,
    /// 放弃本次识别，不发任何结果事件。
    Abort,
}

enum SessionOutcome {
    Finalized(String),
    Aborted,
    Failed(String),
}

struct ActiveSession {
    id: u64,
    commands: mpsc::Sender<SessionCommand>,
    microphone: Arc<Mutex<Option<MicrophoneHandle>>>,
}

#[derive(Default)]
pub struct VoiceInputState {
    active: Mutex<Option<ActiveSession>>,
    next_id: Mutex<u64>,
}

impl VoiceInputState {
    fn take_id(&self) -> u64 {
        let mut next = self.next_id.lock().unwrap_or_else(|p| p.into_inner());
        *next += 1;
        *next
    }
}

fn dialogue_only(window: &WebviewWindow) -> Result<(), String> {
    if window.label() == "dialogue" {
        Ok(())
    } else {
        Err("仅对话窗口可以使用语音输入".into())
    }
}

fn resolve_asr_endpoint(app: &AppHandle) -> Result<(String, String), String> {
    // 优先用 RinaYaki 的 DashScope 凭据（用户指定：语音与 Yaki 同一把 key，
    // 不随聊天方案切换而失效）；聊天方案恰好是百炼时作为回退。
    if let Some((key, ws_url)) = yaki_dashscope_credentials(app) {
        let url = choose_websocket_url(ws_url.as_deref(), None);
        return Ok((key, url));
    }
    let resolved = crate::api_profiles::resolve(Some(app))?;
    let Some(key) = resolved.key.filter(|key| !key.trim().is_empty()) else {
        return Err(no_credentials_message().into());
    };
    let Some(ws_url) = asr::websocket_url_for_base_url(&resolved.url) else {
        return Err(no_credentials_message().into());
    };
    Ok((key, ws_url.to_string()))
}

fn no_credentials_message() -> &'static str {
    "语音输入需要 DashScope 密钥：RinaYaki 未注册或其 .env 未配置 DASHSCOPE_API_KEY，且当前 API 方案也不是阿里云百炼。"
}

/// 从注册的 RinaYaki 项目根 .env 里取 DASHSCOPE_* 凭据字段。
/// 只读这几个文档化字段（与 billing::credentials 的工具凭据边界一致），
/// 解析失败一律视为未配置；密钥不落日志、不进事件。
fn yaki_dashscope_credentials(app: &AppHandle) -> Option<(String, Option<String>)> {
    let root = crate::extension_tools::registered_yaki_root(app)?;
    let text = std::fs::read_to_string(root.join(".env")).ok()?;
    let values = parse_dashscope_env(&text);
    let key = values
        .get("DASHSCOPE_API_KEY")
        .map(|key| key.trim())
        .filter(|key| !key.is_empty())?;
    Some((
        key.to_string(),
        values.get("DASHSCOPE_WEBSOCKET_URL").cloned(),
    ))
}

/// 只挑 DASHSCOPE_ 前缀的赋值行；容忍注释、export 前缀、单双引号与行尾注释。
fn parse_dashscope_env(text: &str) -> std::collections::BTreeMap<String, String> {
    let mut values = std::collections::BTreeMap::new();
    for line in text.lines() {
        let line = line.trim().trim_start_matches('\u{feff}');
        let line = line.strip_prefix("export ").unwrap_or(line).trim_start();
        if line.starts_with('#') {
            continue;
        }
        let Some((key, raw)) = line.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if !key.starts_with("DASHSCOPE_") {
            continue;
        }
        let raw = raw.trim();
        fn strip_quotes(value: &str) -> Option<&str> {
            value
                .strip_prefix('"')
                .and_then(|rest| rest.strip_suffix('"'))
                .or_else(|| {
                    value
                        .strip_prefix('\'')
                        .and_then(|rest| rest.strip_suffix('\''))
                })
        }
        // 先按原值剥引号；失败则切掉行尾注释后再剥一次（`KEY='v' # note`），
        // 仍无引号就用切注释后的原值本身。
        let value = strip_quotes(raw).map(str::to_string).unwrap_or_else(|| {
            let unquoted = raw.split('#').next().unwrap_or(raw).trim();
            strip_quotes(unquoted)
                .map(str::to_string)
                .unwrap_or_else(|| unquoted.to_string())
        });
        if !value.is_empty() {
            values.insert(key.to_string(), value);
        }
    }
    values
}

/// ASR websocket 入口：显式 wss 地址 > 由 base_url 主机映射 > 百炼国内默认。
fn choose_websocket_url(explicit: Option<&str>, base_url: Option<&str>) -> String {
    if let Some(ws) = explicit
        .map(str::trim)
        .filter(|s| s.starts_with("wss://") && !s.contains(char::is_whitespace))
    {
        return ws.to_string();
    }
    if let Some(url) = base_url.and_then(asr::websocket_url_for_base_url) {
        return url.to_string();
    }
    asr::CN_WEBSOCKET_URL.to_string()
}

#[tauri::command]
pub fn voice_input_status(
    window: WebviewWindow,
    app: AppHandle,
) -> Result<VoiceInputStatus, String> {
    dialogue_only(&window)?;
    match resolve_asr_endpoint(&app) {
        Ok(_) => Ok(VoiceInputStatus {
            supported: true,
            model: asr::MODEL.to_string(),
            reason: String::new(),
        }),
        Err(reason) => Ok(VoiceInputStatus {
            supported: false,
            model: asr::MODEL.to_string(),
            reason,
        }),
    }
}

#[tauri::command]
pub fn voice_input_start(
    window: WebviewWindow,
    app: AppHandle,
    state: State<'_, VoiceInputState>,
) -> Result<(), String> {
    dialogue_only(&window)?;
    let (key, ws_url) = resolve_asr_endpoint(&app)?;
    let mut active = state.active.lock().unwrap_or_else(|p| p.into_inner());
    if active.is_some() {
        return Err("语音识别正在进行中".into());
    }
    let session_id = state.take_id();
    let microphone = Arc::new(Mutex::new(Some(capture::start_microphone(
        MAX_RECORDING_SECONDS,
    )?)));
    let (command_tx, command_rx) = mpsc::channel(4);
    *active = Some(ActiveSession {
        id: session_id,
        commands: command_tx,
        microphone: microphone.clone(),
    });
    drop(active);
    let _ = app.emit(
        "voice-input-state",
        serde_json::json!({ "phase": "starting" }),
    );
    tauri::async_runtime::spawn(run_session(
        app.clone(),
        session_id,
        key,
        ws_url,
        microphone,
        command_rx,
    ));
    Ok(())
}

#[tauri::command]
pub fn voice_input_stop(
    window: WebviewWindow,
    state: State<'_, VoiceInputState>,
) -> Result<(), String> {
    dialogue_only(&window)?;
    let mut active = state.active.lock().unwrap_or_else(|p| p.into_inner());
    match active.as_mut() {
        Some(session) => {
            let result = session
                .commands
                .try_send(SessionCommand::Finish)
                .map_err(|_| "语音会话已结束".to_string());
            // 立即停麦；队列里已有的样本仍会被收尾流程取走。
            *session.microphone.lock().unwrap_or_else(|p| p.into_inner()) = None;
            result
        }
        None => Err("语音识别尚未开始".into()),
    }
}

#[tauri::command]
pub fn voice_input_cancel(
    window: WebviewWindow,
    state: State<'_, VoiceInputState>,
) -> Result<(), String> {
    dialogue_only(&window)?;
    let mut active = state.active.lock().unwrap_or_else(|p| p.into_inner());
    if let Some(session) = active.as_mut() {
        let _ = session.commands.try_send(SessionCommand::Abort);
        *session.microphone.lock().unwrap_or_else(|p| p.into_inner()) = None;
    }
    Ok(())
}

fn clear_session(app: &AppHandle, session_id: u64) {
    let state = app.state::<VoiceInputState>();
    let mut active = state.active.lock().unwrap_or_else(|p| p.into_inner());
    if active.as_ref().map(|session| session.id) == Some(session_id) {
        *active = None;
    }
}

async fn run_session(
    app: AppHandle,
    session_id: u64,
    key: String,
    ws_url: String,
    microphone: Arc<Mutex<Option<MicrophoneHandle>>>,
    mut commands: mpsc::Receiver<SessionCommand>,
) {
    let outcome = session_body(&app, &key, ws_url.as_str(), &microphone, &mut commands).await;
    // 统一释放麦克风（drop cpal 流即停止采集）。
    *microphone.lock().unwrap_or_else(|p| p.into_inner()) = None;
    match outcome {
        SessionOutcome::Finalized(text) => {
            let _ = app.emit("voice-input-final", serde_json::json!({ "text": text }));
        }
        SessionOutcome::Aborted => {}
        SessionOutcome::Failed(message) => {
            let _ = app.emit(
                "voice-input-error",
                serde_json::json!({ "message": message }),
            );
        }
    }
    // 先发布本次结果，再开放下一次 start，避免极小窗口内旧会话事件覆盖新会话。
    clear_session(&app, session_id);
}

async fn session_body(
    app: &AppHandle,
    key: &str,
    ws_url: &str,
    microphone: &Arc<Mutex<Option<MicrophoneHandle>>>,
    commands: &mut mpsc::Receiver<SessionCommand>,
) -> SessionOutcome {
    let (queue, native_rate, limit_reached, capture_failed) = {
        let guard = microphone.lock().unwrap_or_else(|p| p.into_inner());
        let Some(mic) = guard.as_ref() else {
            return SessionOutcome::Failed("麦克风会话已失效".into());
        };
        (
            mic.queue.clone(),
            mic.native_rate,
            mic.limit_reached.clone(),
            mic.capture_failed.clone(),
        )
    };

    let task_id = format!(
        "desk-{:x}-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0),
        std::process::id()
    );
    let mut request = match ws_url.into_client_request() {
        Ok(request) => request,
        Err(_) => return SessionOutcome::Failed("语音服务地址无效".into()),
    };
    let headers = request.headers_mut();
    let authorization = match HeaderValue::from_str(&format!("Bearer {key}")) {
        Ok(value) => value,
        Err(_) => return SessionOutcome::Failed("API 密钥包含非法字符".into()),
    };
    headers.insert("Authorization", authorization);
    headers.insert(
        "user-agent",
        HeaderValue::from_static("RinaDesk/0.1 voice-input"),
    );

    let connection = tokio::time::timeout(CONNECT_TIMEOUT, connect_async(request));
    tokio::pin!(connection);
    let connected = match tokio::select! {
        result = &mut connection => Some(result),
        command = commands.recv() => match command {
            Some(SessionCommand::Abort) | Some(SessionCommand::Finish) | None => None,
        },
    } {
        Some(Ok(Ok(connection))) => connection,
        Some(Ok(Err(error))) => {
            return SessionOutcome::Failed(format!("连接语音服务失败：{error}"));
        }
        Some(Err(_)) => return SessionOutcome::Failed("连接语音服务超时，请检查网络".into()),
        None => return SessionOutcome::Aborted,
    };
    let (mut sink, mut stream) = connected.0.split();

    if sink
        .send(Message::text(asr::run_task_frame(&task_id)))
        .await
        .is_err()
    {
        return SessionOutcome::Failed("发送语音任务失败".into());
    }

    let mut transcript = asr::Transcript::default();
    let mut resampler = Resampler::new(native_rate);
    let mut pending: VecDeque<i16> = VecDeque::new();
    let mut finishing = false;
    let mut finish_deadline: Option<Instant> = None;
    let hard_deadline = Instant::now() + Duration::from_secs(MAX_RECORDING_SECONDS + 15);
    let mut ticker = tokio::time::interval(TICK);

    loop {
        tokio::select! {
            maybe_message = stream.next() => {
                let message = match maybe_message {
                    Some(Ok(message)) => message,
                    Some(Err(error)) => {
                        return best_effort(transcript, finishing, format!("语音连接出错：{error}"));
                    }
                    None => {
                        return best_effort(transcript, finishing, "语音连接被服务端关闭".into());
                    }
                };
                match message {
                    Message::Text(text) => {
                        let event = match asr::parse_server_event(&text) {
                            Ok(event) => event,
                            Err(error) => return SessionOutcome::Failed(error),
                        };
                        match &event {
                            asr::ServerEvent::TaskStarted => {
                                let _ = app.emit(
                                    "voice-input-state",
                                    serde_json::json!({ "phase": "recording" }),
                                );
                            }
                            asr::ServerEvent::Sentence { .. } => {
                                transcript.push(&event);
                                let _ = app.emit(
                                    "voice-input-partial",
                                    serde_json::json!({ "text": transcript.display() }),
                                );
                            }
                            asr::ServerEvent::TaskFinished => {
                                return SessionOutcome::Finalized(transcript.display());
                            }
                            asr::ServerEvent::Failed { code, message } => {
                                let detail = if code.is_empty() {
                                    message.clone()
                                } else {
                                    format!("语音识别失败：{message}（{code}）")
                                };
                                return SessionOutcome::Failed(detail);
                            }
                            asr::ServerEvent::Ignored => {}
                        }
                    }
                    Message::Ping(payload) => {
                        let _ = sink.send(Message::Pong(payload)).await;
                    }
                    Message::Close(_) => {
                        return best_effort(transcript, finishing, "语音连接被服务端关闭".into());
                    }
                    _ => {}
                }
            }
            _ = ticker.tick(), if !finishing => {
                if Instant::now() > hard_deadline {
                    return SessionOutcome::Failed("语音会话超时".into());
                }
                if capture_failed.load(Ordering::Relaxed) {
                    *microphone.lock().unwrap_or_else(|p| p.into_inner()) = None;
                    return best_effort(transcript, false, "麦克风采集已中断，请检查设备连接和系统权限".into());
                }
                pending.extend(resampler.process(&queue.drain()));
                if limit_reached.load(Ordering::Relaxed) {
                    // 达到上限立即释放系统麦克风；队列和 pending 已足够完成收尾。
                    *microphone.lock().unwrap_or_else(|p| p.into_inner()) = None;
                    if begin_finishing(app, &mut sink, &mut pending, &task_id).await.is_err() {
                        return best_effort(transcript, true, "发送结束指令失败".into());
                    }
                    finishing = true;
                    finish_deadline = Some(Instant::now() + FINISH_TIMEOUT);
                    continue;
                }
                if send_ready_chunks(&mut sink, &mut pending).await.is_err() {
                    return best_effort(transcript, finishing, "发送音频失败".into());
                }
            }
            command = commands.recv() => {
                match command {
                    Some(SessionCommand::Finish) if !finishing => {
                        // 队列里剩的音频也属本次识别，先发完再收尾。
                        pending.extend(resampler.process(&queue.drain()));
                        if begin_finishing(app, &mut sink, &mut pending, &task_id).await.is_err() {
                            return best_effort(transcript, true, "发送结束指令失败".into());
                        }
                        finishing = true;
                        finish_deadline = Some(Instant::now() + FINISH_TIMEOUT);
                    }
                    Some(SessionCommand::Finish) => {}
                    Some(SessionCommand::Abort) | None => {
                        // 主动放弃：不发结果事件，直接结束任务。
                        return SessionOutcome::Aborted;
                    }
                }
            }
            _ = wait_for_deadline(finish_deadline), if finishing => {
                let text = transcript.display();
                if text.is_empty() {
                    return SessionOutcome::Failed("等待识别结果超时".into());
                }
                return SessionOutcome::Finalized(text);
            }
        }
    }
}

/// 断连/出错时若有已识别文本则按当前结果交付，否则报错。
fn best_effort(transcript: asr::Transcript, finishing: bool, error: String) -> SessionOutcome {
    let text = transcript.display();
    if finishing && !text.is_empty() {
        SessionOutcome::Finalized(text)
    } else if !transcript.has_final_text() {
        SessionOutcome::Failed(error)
    } else {
        SessionOutcome::Finalized(text)
    }
}

async fn wait_for_deadline(deadline: Option<Instant>) {
    match deadline {
        Some(deadline) => tokio::time::sleep_until(deadline).await,
        None => std::future::pending::<()>().await,
    }
}

async fn begin_finishing(
    app: &AppHandle,
    sink: &mut WsSink,
    pending: &mut VecDeque<i16>,
    task_id: &str,
) -> Result<(), ()> {
    let _ = app.emit(
        "voice-input-state",
        serde_json::json!({ "phase": "finishing" }),
    );
    while !pending.is_empty() {
        let count = pending.len().min(SEND_CHUNK_SAMPLES);
        let chunk: Vec<i16> = pending.drain(..count).collect();
        send_chunk(sink, &chunk).await.map_err(|_| ())?;
    }
    sink.send(Message::text(asr::finish_task_frame(task_id)))
        .await
        .map_err(|_| ())
}

async fn send_ready_chunks(sink: &mut WsSink, pending: &mut VecDeque<i16>) -> Result<(), String> {
    while pending.len() >= SEND_CHUNK_SAMPLES {
        let chunk: Vec<i16> = pending.drain(..SEND_CHUNK_SAMPLES).collect();
        send_chunk(sink, &chunk).await?;
    }
    Ok(())
}

async fn send_chunk(sink: &mut WsSink, samples: &[i16]) -> Result<(), String> {
    let bytes: Vec<u8> = samples.iter().flat_map(|&s| s.to_le_bytes()).collect();
    sink.send(Message::binary(bytes))
        .await
        .map_err(|_| "发送音频失败".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dashscope_env_parser_picks_only_prefixed_keys() {
        let text = "# comment\nDASHSCOPE_API_KEY=sk-abc \nexport DASHSCOPE_WEBSOCKET_URL=\"wss://example.test/api-ws\"\nOTHER_KEY=keep-out\nDASHSCOPE_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1' # inline\nDASHSCOPE_EMPTY=\nbroken line without equals\n";
        let values = parse_dashscope_env(text);
        assert_eq!(
            values.get("DASHSCOPE_API_KEY").map(String::as_str),
            Some("sk-abc")
        );
        assert_eq!(
            values.get("DASHSCOPE_WEBSOCKET_URL").map(String::as_str),
            Some("wss://example.test/api-ws")
        );
        assert_eq!(
            values.get("DASHSCOPE_BASE_URL").map(String::as_str),
            Some("https://dashscope.aliyuncs.com/compatible-mode/v1")
        );
        assert!(!values.contains_key("OTHER_KEY"));
        assert!(!values.contains_key("DASHSCOPE_EMPTY"));
        assert_eq!(values.len(), 3);
    }

    #[test]
    fn websocket_url_prefers_explicit_then_base_then_default() {
        assert_eq!(
            choose_websocket_url(Some("wss://custom.test/ws"), None),
            "wss://custom.test/ws"
        );
        assert_eq!(
            choose_websocket_url(
                None,
                Some("https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
            ),
            asr::INTL_WEBSOCKET_URL.to_string()
        );
        assert_eq!(choose_websocket_url(None, None), asr::CN_WEBSOCKET_URL);
        // 显式地址非法（非 wss / 含空白）时不采纳，落到默认。
        assert_eq!(
            choose_websocket_url(Some("http://insecure.test"), None),
            asr::CN_WEBSOCKET_URL
        );
        assert_eq!(
            choose_websocket_url(Some("wss://bad url"), None),
            asr::CN_WEBSOCKET_URL
        );
        // base_url 不是 dashscope 主机时也不采纳。
        assert_eq!(
            choose_websocket_url(None, Some("https://api.openai.com/v1")),
            asr::CN_WEBSOCKET_URL
        );
    }
}
