//! 确认级 agent 动作：提案 → 用户两闸确认 → 执行 → 任务状态。
//! 闸 1（唤起）确认后只跑免费的 `preview` 取元数据渲染卡片；
//! 闸 2（消费）确认后才调 `create`——桥的 create 会立即开始下载与转写，
//! 这条边界就是付费闸门。执行全程走既有 Yaki 桥，不另建 IPC。

use crate::extension_tools;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};

const MAX_PENDING: usize = 5;
const MAX_LOG_BYTES: u64 = 1024 * 1024;
static LOG_LOCK: Mutex<()> = Mutex::new(());
/// qwen-audio-3.1-asr-flash-filetrans 单价（2026-10 阿里云百炼页，0.00022 元/秒）。
/// 翻译（Qwen-MT 按字符）量级更小且费率易变，只在文案里提示"另计"。
const ASR_YUAN_PER_SECOND: f64 = 0.00022;
/// 终态通知去重：每个 (任务, 相位) 在本次 Desk 运行内只推一次。
static NOTIFIED_JOBS: std::sync::Mutex<Option<std::collections::HashSet<String>>> =
    std::sync::Mutex::new(None);

#[derive(Clone)]
pub struct Proposal {
    pub url: String,
    created: Instant,
    /// 闸 1 确认后由 preview 填充。
    kind: Option<String>,
    source: Option<String>,
    title: Option<String>,
    duration: Option<f64>,
    previewing: bool,
    /// Yaki 设置维护的默认保存位置（bridge settings action）。
    default_parent: Option<String>,
    /// 视频封面（data URL）与 Yaki 给出的画质默认值。
    thumbnail: Option<String>,
    acquisition: Option<Value>,
}

#[derive(Default)]
pub struct AgentProposals {
    pending: Mutex<HashMap<String, Proposal>>,
}

fn dialogue_only(window: &WebviewWindow) -> Result<(), String> {
    if window.label() == "dialogue" {
        Ok(())
    } else {
        Err("仅对话窗口可以使用 agent 动作。".into())
    }
}

/// 轻量运行日志（不含密钥/URL 全文），用于定位 agent 动作卡在哪一步。
fn rotate_log(path: &std::path::Path) {
    let Ok(metadata) = std::fs::metadata(path) else {
        return;
    };
    if metadata.len() < MAX_LOG_BYTES {
        return;
    }
    let previous = path.with_extension("log.1");
    let _ = std::fs::remove_file(&previous);
    let _ = std::fs::rename(path, previous);
}

fn log_event(line: &str) {
    use std::io::Write;
    let _guard = LOG_LOCK
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let Ok(dir) = crate::release_profile::data_dir("RinaDesk").map(|home| home.join("logs")) else {
        return;
    };
    if std::fs::create_dir_all(&dir).is_err() {
        return;
    }
    let path = dir.join("agent.log");
    rotate_log(&path);
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let now = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
        let _ = writeln!(file, "{now} {line}");
    }
}

/// 只接受 http/https 的 web 视频地址；本地文件仍走 Yaki 扩展页。
pub fn validate_url(url: &str) -> Result<(), String> {
    let url = url.trim();
    if url.is_empty() || url.len() > 4096 || url.contains(char::is_whitespace) {
        return Err("请提供有效的视频链接。".into());
    }
    let parsed = reqwest::Url::parse(url).map_err(|_| "请提供有效的视频链接。")?;
    if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
        return Err("视频链接需要是 http/https 地址。".into());
    }
    Ok(())
}

/// 费用预估文案：转写按时长精确估算，明确"以实际为准"。
pub fn estimate_cost_label(duration_seconds: f64) -> String {
    let minutes = (duration_seconds / 60.0).max(0.0);
    let asr = duration_seconds.max(0.0) * ASR_YUAN_PER_SECOND;
    format!(
        "转写预计约 ¥{:.2}（约 {:.0} 分钟），以实际用量为准",
        asr, minutes
    )
}

/// Yaki 设置返回的路径可能带 Windows verbatim 前缀（\\?\），展示与回传都去掉。
fn strip_verbatim(path: &str) -> String {
    path.trim()
        .trim_start_matches(r"\\?\")
        .trim_start_matches(r"\\?\UNC\")
        .to_string()
}

fn task_request(
    kind: &str,
    source: &str,
    title: &str,
    name: &str,
    parent: &str,
    acquisition: Option<&Value>,
) -> Value {
    let mut video = json!({"kind": kind, "source": source, "title": title});
    if let Some(acquisition) = acquisition {
        // 与扩展页一致：沿用 Yaki 给的会话/画质默认，画质取 auto。
        video["acquisition"] = json!({"session": acquisition.get("session").cloned().unwrap_or(Value::Null), "quality": "auto"});
    }
    json!({
        "video": video,
        "sourceLanguage": "ja",
        "targetLanguage": "zh-Hans",
        "name": name,
        "parent": parent,
    })
}

/// 从视频标题推导合法项目名：去掉 Windows/Yaki 不接受的字符，
/// 折叠连续下划线，去首尾空白与点号，限长。空结果回退固定名。
fn suggested_project_name(title: &str) -> String {
    const FALLBACK: &str = "rinadesk-translation";
    let mut name = String::new();
    let mut last_was_underscore = false;
    for character in title.chars() {
        let keep = !matches!(
            character,
            '<' | '>'
                | ':'
                | '"'
                | '/'
                | '\\'
                | '|'
                | '?'
                | '*'
                | '.'
                | '#'
                | '%'
                | '&'
                | '{'
                | '}'
                | '$'
                | '!'
                | '`'
                | '\''
                | '='
                | '@'
                | '+'
                | ','
                | ';'
        ) && !character.is_control()
            && !character.is_whitespace();
        if keep {
            name.push(character);
            last_was_underscore = false;
        } else if !last_was_underscore && !name.is_empty() {
            name.push('_');
            last_was_underscore = true;
        }
    }
    let trimmed = name.trim_matches(|c: char| c == '_' || c == '.' || c.is_whitespace());
    let mut result: String = trimmed.chars().take(60).collect();
    result = result
        .trim_matches(|c: char| c == '_' || c == '.' || c.is_whitespace())
        .to_string();
    if result.is_empty() {
        FALLBACK.into()
    } else {
        result
    }
}

fn card_value(proposal_id: &str, proposal: &Proposal, phase: &str, extra: Value) -> Value {
    let mut value = json!({
        "proposalId": proposal_id,
        "phase": phase,
        "url": proposal.url,
        "title": proposal.title,
        "duration": proposal.duration,
        "estimate": proposal.duration.map(estimate_cost_label),
    });
    if let Some(object) = value.as_object_mut() {
        if let Some(fields) = extra.as_object() {
            for (key, field) in fields {
                object.insert(key.clone(), field.clone());
            }
        }
    }
    value
}

fn emit_task(app: &AppHandle, payload: Value) {
    let _ = app.emit("agent-task", payload);
}

/// 模型调用确认级工具时登记提案并通知前端；不执行任何动作。
pub fn register(app: &AppHandle, request_id: &str, url: &str) -> Value {
    if let Err(error) = validate_url(url) {
        return json!({"error": error});
    }
    let state = app.state::<AgentProposals>();
    let mut pending = state.pending.lock().unwrap_or_else(|p| p.into_inner());
    let evicted = if pending.len() >= MAX_PENDING {
        if let Some(oldest) = pending
            .iter()
            .filter(|(_, proposal)| !proposal.previewing && proposal.kind.is_none())
            .min_by_key(|(_, proposal)| proposal.created)
            .map(|(id, _)| id.clone())
        {
            pending.remove(&oldest);
            Some(oldest)
        } else {
            return json!({"error":"已有过多待开始的视频任务，请先处理现有任务卡。"});
        }
    } else {
        None
    };
    let proposal_id = format!(
        "proposal-{:x}-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0),
        std::process::id()
    );
    let proposal = Proposal {
        url: url.trim().to_string(),
        created: Instant::now(),
        kind: None,
        source: None,
        title: None,
        duration: None,
        previewing: false,
        default_parent: None,
        thumbnail: None,
        acquisition: None,
    };
    pending.insert(proposal_id.clone(), proposal);
    drop(pending);
    if let Some(evicted) = evicted {
        emit_task(
            app,
            json!({"proposalId": evicted, "phase": "failed", "status": "提案已过期，请重新创建"}),
        );
    }
    let _ = app.emit(
        "agent-proposal",
        json!({"requestId": request_id, "proposalId": proposal_id, "url": url.trim()}),
    );
    json!({
        "status": "proposal_created",
        "detail": "已生成翻译任务卡片等待用户确认；用户在聊天页确认后才会开始任何下载或付费步骤。在用户完成确认前，不要声称翻译已开始。",
    })
}

#[tauri::command]
pub async fn agent_proposal_confirm(
    window: WebviewWindow,
    app: AppHandle,
    state: State<'_, AgentProposals>,
    proposal_id: String,
) -> Result<Value, String> {
    dialogue_only(&window)?;
    let url = {
        let mut pending = state.pending.lock().unwrap_or_else(|p| p.into_inner());
        let proposal = pending.get_mut(&proposal_id).ok_or("提案已失效")?;
        if proposal.previewing {
            return Err("正在读取视频信息，请稍候。".into());
        }
        proposal.previewing = true;
        proposal.url.clone()
    };
    log_event(&format!("gate1 confirm start id={proposal_id}"));
    // 闸 1 确认：只取元数据，不触发下载。VideoPreview 字段不外露，经序列化读取。
    let preview = match extension_tools::extension_preview(app.clone(), url).await {
        Ok(preview) => preview,
        Err(error) => {
            if let Some(proposal) = state
                .pending
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .get_mut(&proposal_id)
            {
                proposal.previewing = false;
            }
            log_event(&format!(
                "gate1 confirm FAILED id={proposal_id} error={error}"
            ));
            return Err(error);
        }
    };
    log_event(&format!("gate1 confirm ok id={proposal_id}"));
    // 顺带取 Yaki 设置里的默认保存位置（免费、只读），供闸 2 表单预填。
    let default_parent =
        extension_tools::extension_yaki_action(app.clone(), "settings".into(), json!({}))
            .await
            .ok()
            .and_then(|value| {
                value
                    .pointer("/settings/defaultProjectDir")
                    .and_then(Value::as_str)
                    .map(strip_verbatim)
            });
    let preview = serde_json::to_value(&preview).map_err(|_| "预览结果无法解析。")?;
    let field = |key: &str| {
        preview
            .get(key)
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    };
    let (kind, source, title, duration) = (
        field("kind"),
        field("source"),
        field("title"),
        preview
            .get("duration")
            .and_then(Value::as_f64)
            .unwrap_or(0.0),
    );
    let card = {
        let mut pending = state.pending.lock().unwrap_or_else(|p| p.into_inner());
        let Some(proposal) = pending.get_mut(&proposal_id) else {
            return Err("提案已失效".into());
        };
        proposal.kind = Some(kind);
        proposal.source = Some(source);
        proposal.title = Some(title);
        proposal.duration = Some(duration);
        proposal.previewing = false;
        proposal.default_parent = default_parent.clone();
        proposal.thumbnail = preview
            .get("thumbnail")
            .and_then(Value::as_str)
            .map(str::to_string);
        proposal.acquisition = preview
            .get("acquisition")
            .filter(|value| value.is_object())
            .cloned();
        let quality_label = proposal
            .acquisition
            .as_ref()
            .and_then(|value| value.get("quality"))
            .and_then(Value::as_str)
            .unwrap_or("自动")
            .to_string();
        let suggested = suggested_project_name(proposal.title.as_deref().unwrap_or(""));
        // 不用 json! 字面量键：当前工具链的 release 链接会丢掉这两个键的字面量
        //（行为同 extension_status 事件），改为运行时构造绕开。
        let mut extra = serde_json::Map::new();
        extra.insert("suggested".to_string() + "Name", json!(suggested));
        extra.insert("default".to_string() + "Parent", json!(default_parent));
        extra.insert("thumbnail".to_string(), json!(proposal.thumbnail));
        extra.insert("quality".to_string() + "Label", json!(quality_label));
        card_value(&proposal_id, proposal, "ready", Value::Object(extra))
    };
    emit_task(&app, card.clone());
    Ok(card)
}

#[tauri::command]
pub fn agent_proposal_decline(
    window: WebviewWindow,
    app: AppHandle,
    state: State<'_, AgentProposals>,
    proposal_id: String,
) -> Result<(), String> {
    dialogue_only(&window)?;
    state
        .pending
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .remove(&proposal_id);
    emit_task(
        &app,
        json!({"proposalId": proposal_id, "phase": "declined"}),
    );
    Ok(())
}

#[tauri::command]
pub async fn agent_task_start(
    window: WebviewWindow,
    app: AppHandle,
    state: State<'_, AgentProposals>,
    proposal_id: String,
    name: String,
    parent: String,
) -> Result<Value, String> {
    dialogue_only(&window)?;
    let name = name.trim().to_string();
    let parent = parent.trim().to_string();
    if name.is_empty() || parent.is_empty() {
        return Err("请填写保存位置和项目名称。".into());
    }
    // 闸 2 确认：从这里开始才产生下载与转写费用。
    let proposal = state
        .pending
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .remove(&proposal_id)
        .ok_or("提案已失效")?;
    let (kind, source, title) = match (
        proposal.kind.clone(),
        proposal.source.clone(),
        proposal.title.clone(),
    ) {
        (Some(kind), Some(source), title) => (kind, source, title.unwrap_or_default()),
        _ => {
            state
                .pending
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .insert(proposal_id.clone(), proposal);
            return Err("提案缺少预览信息，请重新发起".into());
        }
    };
    let request = task_request(
        &kind,
        &source,
        &title,
        &name,
        &parent,
        proposal.acquisition.as_ref(),
    );
    log_event(&format!("gate2 start begin id={proposal_id}"));
    let created =
        match extension_tools::extension_yaki_action(app.clone(), "create".into(), request).await {
            Ok(created) => created,
            Err(error) => {
                state
                    .pending
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .insert(proposal_id.clone(), proposal.clone());
                log_event(&format!(
                    "gate2 start FAILED id={proposal_id} error={error}"
                ));
                return Err(error);
            }
        };
    log_event(&format!("gate2 start ok id={proposal_id}"));
    let job_path = created
        .get("job")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let status = created
        .pointer("/state/status")
        .and_then(Value::as_str)
        .unwrap_or("new")
        .to_string();
    if job_path.is_empty() {
        return Err("Yaki 未返回任务句柄。".into());
    }
    let card = json!({
        "proposalId": proposal_id,
        "phase": "running",
        "url": proposal.url,
        "jobPath": job_path,
        "status": status,
    });
    emit_task(&app, card.clone());
    Ok(card)
}

#[tauri::command]
pub async fn agent_task_status(
    window: WebviewWindow,
    app: AppHandle,
    job_path: String,
) -> Result<Value, String> {
    dialogue_only(&window)?;
    if job_path.is_empty() || job_path.len() > 1024 {
        return Err("任务句柄无效。".into());
    }
    // 桥侧 checked_job 只放行已登记的直接工程；状态只读。
    let status = extension_tools::extension_yaki_action(
        app.clone(),
        "status".into(),
        json!({"job": job_path}),
    )
    .await?;
    let raw = status
        .pointer("/state/status")
        .and_then(Value::as_str)
        .unwrap_or("unknown")
        .to_string();
    let phase = match raw.as_str() {
        "awaiting_style" => "awaiting_style",
        "complete" => "complete",
        "failed" => "failed",
        _ => "running",
    };
    let number = |pointer: &str| {
        status
            .pointer(pointer)
            .and_then(Value::as_f64)
            .filter(|value| value.is_finite())
    };
    let card = json!({
        "jobPath": job_path,
        "phase": phase,
        "status": raw,
        "detail": status.pointer("/state/phase").and_then(Value::as_str)
            .or_else(|| status.pointer("/state/stage").and_then(Value::as_str))
            .unwrap_or(""),
        "stage": status.pointer("/state/stage").and_then(Value::as_str).unwrap_or(""),
        "completed": number("/state/completed"),
        "total": number("/state/total"),
        "title": status.get("projectName").and_then(Value::as_str).unwrap_or(""),
    });
    // 终态一次性推送到 Tomo 通知（主人可能在挂机等长任务）。去重键=任务+相位。
    if matches!(phase, "awaiting_style" | "complete" | "failed") {
        let mut notified = NOTIFIED_JOBS.lock().unwrap_or_else(|p| p.into_inner());
        let set = notified.get_or_insert_with(std::collections::HashSet::new);
        let dedupe_key = format!("{job_path}:{phase}");
        if set.insert(dedupe_key) {
            let title = card["title"].as_str().unwrap_or("翻译任务").to_string();
            let phase_label = match phase {
                "awaiting_style" => "翻译完成，可导出字幕",
                "complete" => "导出完成",
                _ => "任务失败",
            };
            let status_line = card["status"].as_str().unwrap_or("").to_string();
            tauri::async_runtime::spawn_blocking(move || {
                crate::rinatomo::notify(
                    "translation",
                    &format!("{title} · {phase_label}"),
                    &[&status_line],
                );
            });
        }
    }
    // 轮询结果也走事件，前端统一按 jobPath 合并进消息里的任务卡。
    emit_task(&app, card.clone());
    Ok(card)
}

/// 跳转到 Yaki 扩展页：显示/聚焦设置窗口并向其定向广播切页事件。
/// 用 Rust emit_to 而非前端 emit 广播，避免跨窗口投递的版本行为差异
/// （2026-10-24 前端广播未生效的修复）。
#[tauri::command]
pub fn agent_open_yaki(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("settings") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
    let _ = app.emit_to("settings", "deskpet-open-yaki", ());
    Ok(())
}

/// 一键导出：awaiting_style 的任务用 Yaki 默认样式（默认字体 + 黑色描边，
/// 与扩展页 defaultStyle 一致）给每个说话人提交 export。
#[tauri::command]
pub async fn agent_task_export(
    window: WebviewWindow,
    app: AppHandle,
    job_path: String,
) -> Result<Value, String> {
    dialogue_only(&window)?;
    if job_path.is_empty() || job_path.len() > 1024 {
        return Err("任务句柄无效。".into());
    }
    log_event(&format!("export begin job={job_path}"));
    let status = extension_tools::extension_yaki_action(
        app.clone(),
        "status".into(),
        json!({"job": job_path}),
    )
    .await?;
    if status.pointer("/state/status").and_then(Value::as_str) != Some("awaiting_style") {
        log_event(&format!("export rejected job={job_path} 状态未就绪"));
        return Err("只有翻译完成的任务可以导出。".into());
    }
    let speakers: Vec<String> = status
        .pointer("/prepared/speakers")
        .and_then(Value::as_object)
        .map(|map| map.keys().cloned().collect())
        .unwrap_or_default();
    if speakers.is_empty() {
        return Err("尚未生成说话人信息，请到 Yaki 扩展页处理。".into());
    }
    let default_font =
        extension_tools::extension_yaki_action(app.clone(), "style_options".into(), json!({}))
            .await
            .ok()
            .and_then(|value| {
                value
                    .get("defaultFont")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            })
            .unwrap_or_else(|| "Noto Sans CJK SC Medium".into());
    let styles: serde_json::Map<String, Value> = speakers
        .iter()
        .map(|speaker| {
            (
                speaker.clone(),
                json!({"color": "#000000", "font": default_font}),
            )
        })
        .collect();
    let export = extension_tools::extension_yaki_action(
        app.clone(),
        "export".into(),
        json!({"job": job_path, "styles": styles}),
    )
    .await;
    match export {
        Ok(result) => {
            log_event(&format!("export ok job={job_path}"));
            let card = json!({
                "jobPath": job_path,
                "phase": "running",
                "status": result.pointer("/state/status").and_then(Value::as_str).unwrap_or("running"),
            });
            emit_task(&app, card.clone());
            Ok(card)
        }
        Err(error) => {
            log_event(&format!("export FAILED job={job_path} error={error}"));
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn verbatim_prefix_is_stripped_for_display_and_roundtrip() {
        assert_eq!(strip_verbatim(r"\\?\E:\烤肉翻译运行"), r"E:\烤肉翻译运行");
        assert_eq!(strip_verbatim(r"E:\烤肉翻译运行"), r"E:\烤肉翻译运行");
        assert_eq!(strip_verbatim("  E:\\dir  "), "E:\\dir");
    }

    #[test]
    fn url_validation_accepts_web_only() {
        assert!(validate_url("https://www.youtube.com/watch?v=abc").is_ok());
        assert!(validate_url("http://example.com/v").is_ok());
        assert!(validate_url("  https://www.bilibili.com/video/BV1xx  ").is_ok());
        assert!(validate_url("").is_err());
        assert!(validate_url("not a url").is_err());
        assert!(validate_url("file:///E:/video.mp4").is_err());
        assert!(validate_url("E:\\video.mp4").is_err());
        assert!(validate_url(&format!("https://example.com/{}", "a".repeat(4100))).is_err());
        assert!(validate_url("https://example.com/a b").is_err());
    }

    #[test]
    fn cost_estimate_scales_with_duration() {
        let label = estimate_cost_label(600.0);
        assert!(label.contains("¥0.13"), "{label}");
        assert!(label.contains("10 分钟"), "{label}");
        assert!(!label.contains("另计"), "{label}");
        assert!(estimate_cost_label(0.0).contains("¥0.00"));
    }

    #[test]
    fn task_request_supplies_the_yaki_language_contract() {
        let request = task_request(
            "web",
            "https://example.com/v",
            "示例",
            "示例项目",
            "E:\\烤肉翻译运行",
            Some(&json!({"session":"app","quality":"1080p"})),
        );
        assert_eq!(request["sourceLanguage"], "ja");
        assert_eq!(request["targetLanguage"], "zh-Hans");
        assert_eq!(request["video"]["kind"], "web");
        assert_eq!(request["name"], "示例项目");
        assert_eq!(request["parent"], "E:\\烤肉翻译运行");
        assert_eq!(request["video"]["acquisition"]["session"], "app");
        assert_eq!(request["video"]["acquisition"]["quality"], "auto");
        let plain = task_request("web", "s", "t", "n", "p", None);
        assert!(plain["video"].get("acquisition").is_none());
    }

    #[test]
    fn suggested_project_name_sanitizes_titles() {
        assert_eq!(
            suggested_project_name("【官方MV】Never Gonna Give You Up"),
            "【官方MV】Never_Gonna_Give_You_Up"
        );
        assert_eq!(suggested_project_name("  hello   world  "), "hello_world");
        assert_eq!(
            suggested_project_name("a/b\\c:d*e?f\"g<h>i|j"),
            "a_b_c_d_e_f_g_h_i_j"
        );
        assert_eq!(suggested_project_name("...___..."), "rinadesk-translation");
        assert_eq!(suggested_project_name(""), "rinadesk-translation");
        let long = suggested_project_name(&"字".repeat(200));
        assert_eq!(long.chars().count(), 60);
        assert!(!long.ends_with('_') && !long.ends_with('.'));
    }

    #[test]
    fn card_value_merges_extra_fields() {
        let proposal = Proposal {
            url: "https://example.com/v".into(),
            created: Instant::now(),
            kind: Some("web".into()),
            source: Some("https://example.com/v".into()),
            title: Some("示例".into()),
            duration: Some(120.0),
            previewing: false,
            default_parent: Some("E:\\烤肉翻译运行".into()),
            thumbnail: None,
            acquisition: None,
        };
        let card = card_value("p1", &proposal, "ready", json!({"jobPath": "/tmp/j"}));
        assert_eq!(card["proposalId"], "p1");
        assert_eq!(card["phase"], "ready");
        assert_eq!(card["title"], "示例");
        assert_eq!(card["duration"], 120.0);
        assert!(card["estimate"].as_str().unwrap().contains("¥"));
        assert_eq!(card["jobPath"], "/tmp/j");
    }
}
