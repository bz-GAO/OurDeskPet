use arboard::{Clipboard, Error as ClipboardError};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine};
use futures_util::StreamExt;
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet},
    env,
    error::Error,
    fs,
    io::Cursor,
    path::{Path, PathBuf},
    process::Command,
    sync::Mutex,
    time::Duration,
};
use tauri::{Emitter, Manager, State};
use xcap::{
    image::{DynamicImage, ImageFormat},
    Monitor,
};

const DEFAULT_BASE_URL: &str = "https://api.openai.com/v1";
const PROMPT_FALLBACK: &str = "你现在是天王寺璃奈（Tennoji Rina）。你是一个精通电子工程、硬件开发和计算机技术的女孩子。请在回复中使用璃奈板表达情绪，并用严谨但自然的语气帮助用户。";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmConfigStatus {
    has_api_key: bool,
    base_url: String,
    model: Option<String>,
    model_options: Vec<String>,
    prompt_source: String,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatStreamRequest {
    request_id: String,
    messages: Vec<ChatMessage>,
    images: Option<Vec<ImagePayload>>,
}

#[derive(Debug, Deserialize, Clone)]
struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ImagePayload {
    mime_type: String,
    data_url: String,
    width: Option<u32>,
    height: Option<u32>,
    byte_size: Option<usize>,
    name: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct CaptureScreenRegionRequest {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatDeltaEvent {
    request_id: String,
    delta: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatCompleteEvent {
    request_id: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatErrorEvent {
    request_id: String,
    message: String,
}

#[derive(Debug)]
struct LlmConfig {
    api_key: Option<String>,
    base_url: String,
    model: Option<String>,
    model_options: Vec<String>,
    system_prompt: String,
    prompt_source: String,
}

#[derive(Default)]
struct ChatCancelState {
    canceled_requests: Mutex<HashSet<String>>,
}

#[tauri::command]
fn llm_config_status(app: tauri::AppHandle) -> LlmConfigStatus {
    let config = load_llm_config(Some(&app));

    LlmConfigStatus {
        has_api_key: config
            .api_key
            .as_ref()
            .is_some_and(|value| !value.trim().is_empty()),
        base_url: config.base_url,
        model: config.model,
        model_options: config.model_options,
        prompt_source: config.prompt_source,
    }
}

#[tauri::command]
async fn chat_stream(
    window: tauri::Window,
    state: State<'_, ChatCancelState>,
    request: ChatStreamRequest,
) -> Result<(), String> {
    let config = load_llm_config(None);

    let result = stream_openai_compatible_chat(&window, &state, &request, &config).await;
    if let Err(error) = &result {
        let _ = emit_chat_error(&window, &request.request_id, error);
    }

    result
}

#[tauri::command]
fn cancel_chat_stream(state: State<'_, ChatCancelState>, request_id: String) -> Result<(), String> {
    state
        .canceled_requests
        .lock()
        .map_err(|_| "Could not lock chat cancellation state.".to_string())?
        .insert(request_id);

    Ok(())
}

#[tauri::command]
fn capture_screen_region(request: CaptureScreenRegionRequest) -> Result<ImagePayload, String> {
    if request.width < 8 || request.height < 8 {
        return Err("Selected region is too small.".to_string());
    }

    let monitor = Monitor::from_point(request.x, request.y)
        .map_err(|error| format!("Could not find monitor for selection: {error}"))?;
    let monitor_x = monitor
        .x()
        .map_err(|error| format!("Could not read monitor x position: {error}"))?;
    let monitor_y = monitor
        .y()
        .map_err(|error| format!("Could not read monitor y position: {error}"))?;
    let monitor_width = monitor
        .width()
        .map_err(|error| format!("Could not read monitor width: {error}"))?;
    let monitor_height = monitor
        .height()
        .map_err(|error| format!("Could not read monitor height: {error}"))?;

    let relative_x = (request.x - monitor_x).max(0) as u32;
    let relative_y = (request.y - monitor_y).max(0) as u32;
    let max_width = monitor_width.saturating_sub(relative_x);
    let max_height = monitor_height.saturating_sub(relative_y);
    let width = request.width.min(max_width);
    let height = request.height.min(max_height);

    if width < 8 || height < 8 {
        return Err("Selected region is outside the active monitor.".to_string());
    }

    let image = monitor
        .capture_region(relative_x, relative_y, width, height)
        .map_err(|error| format!("Failed to capture selected region: {error}"))?;
    let image_width = image.width();
    let image_height = image.height();
    let mut png_bytes = Vec::new();

    DynamicImage::ImageRgba8(image)
        .write_to(&mut Cursor::new(&mut png_bytes), ImageFormat::Png)
        .map_err(|error| format!("Failed to encode capture as PNG: {error}"))?;

    let data_url = format!(
        "data:image/png;base64,{}",
        BASE64_STANDARD.encode(&png_bytes)
    );

    Ok(ImagePayload {
        mime_type: "image/png".to_string(),
        data_url,
        width: Some(image_width),
        height: Some(image_height),
        byte_size: Some(png_bytes.len()),
        name: Some("screen-capture.png".to_string()),
    })
}

#[tauri::command]
fn close_capture_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("capture") {
        window
            .close()
            .map_err(|error| format!("Failed to close capture window: {error}"))?;
    }

    Ok(())
}

#[tauri::command]
fn start_system_screen_clip(app: tauri::AppHandle) -> Result<(), String> {
    let _ = close_capture_window(app);
    start_windows_screen_clip()
}

#[tauri::command]
fn read_clipboard_image() -> Result<Option<ImagePayload>, String> {
    let mut clipboard =
        Clipboard::new().map_err(|error| format!("Failed to open clipboard: {error}"))?;

    match clipboard.get_image() {
        Ok(image) => clipboard_image_to_payload(image),
        Err(ClipboardError::ContentNotAvailable) => Ok(None),
        Err(error) => Err(format!("Failed to read clipboard image: {error}")),
    }
}

fn clipboard_image_to_payload(
    image: arboard::ImageData<'static>,
) -> Result<Option<ImagePayload>, String> {
    let width = image.width as u32;
    let height = image.height as u32;
    let rgba = xcap::image::RgbaImage::from_raw(width, height, image.bytes.into_owned())
        .ok_or_else(|| "Clipboard image data is not valid RGBA.".to_string())?;
    let mut png_bytes = Vec::new();

    DynamicImage::ImageRgba8(rgba)
        .write_to(&mut Cursor::new(&mut png_bytes), ImageFormat::Png)
        .map_err(|error| format!("Failed to encode clipboard image as PNG: {error}"))?;

    let data_url = format!(
        "data:image/png;base64,{}",
        BASE64_STANDARD.encode(&png_bytes)
    );

    Ok(Some(ImagePayload {
        mime_type: "image/png".to_string(),
        data_url,
        width: Some(width),
        height: Some(height),
        byte_size: Some(png_bytes.len()),
        name: Some("screen-clip.png".to_string()),
    }))
}

#[cfg(target_os = "windows")]
fn start_windows_screen_clip() -> Result<(), String> {
    Command::new("explorer.exe")
        .arg("ms-screenclip:")
        .spawn()
        .map(|_| ())
        .or_else(|_| {
            Command::new("SnippingTool.exe")
                .arg("/clip")
                .spawn()
                .map(|_| ())
        })
        .map_err(|error| format!("Failed to start Windows screen clipping: {error}"))
}

#[cfg(not(target_os = "windows"))]
fn start_windows_screen_clip() -> Result<(), String> {
    Err("System screen clipping is currently implemented for Windows only.".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(ChatCancelState::default())
        .invoke_handler(tauri::generate_handler![
            llm_config_status,
            chat_stream,
            cancel_chat_stream,
            capture_screen_region,
            close_capture_window,
            start_system_screen_clip,
            read_clipboard_image
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

async fn stream_openai_compatible_chat(
    window: &tauri::Window,
    state: &ChatCancelState,
    request: &ChatStreamRequest,
    config: &LlmConfig,
) -> Result<(), String> {
    let api_key = config
        .api_key
        .as_ref()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "API key is not configured. Add OURDESKPET_API_KEY to .env.".to_string())?;

    let model = config
        .model
        .as_ref()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "Model is not configured. Add OURDESKPET_MODEL to .env.".to_string())?;

    if request.messages.is_empty() {
        return Err("Message history is empty.".to_string());
    }

    if take_cancel_request(state, &request.request_id)? {
        emit_chat_complete(window, &request.request_id)?;
        return Ok(());
    }

    let payload = json!({
        "model": model,
        "stream": true,
        "messages": build_api_messages(request, &config.system_prompt)?,
    });

    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(20))
        .build()
        .map_err(|error| format!("Failed to create HTTP client: {error}"))?;

    let response = client
        .post(chat_completions_endpoint(&config.base_url))
        .header(AUTHORIZATION, format!("Bearer {api_key}"))
        .header(CONTENT_TYPE, "application/json")
        .json(&payload)
        .send()
        .await
        .map_err(|error| format_reqwest_error("API request failed", &error))?;

    let status = response.status();
    let content_type = response
        .headers()
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();

    if !status.is_success() {
        let body = response.text().await.unwrap_or_default();
        let detail = extract_error_message(&body).unwrap_or(body);
        return Err(format!("API returned {status}: {}", detail.trim()));
    }

    if take_cancel_request(state, &request.request_id)? {
        emit_chat_complete(window, &request.request_id)?;
        return Ok(());
    }

    if !content_type.contains("text/event-stream") {
        let value = response
            .json::<Value>()
            .await
            .map_err(|error| format_reqwest_error("Failed to parse API response", &error))?;
        let content = value
            .pointer("/choices/0/message/content")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();

        if !content.is_empty() {
            emit_chat_delta(window, &request.request_id, &content)?;
        }
        emit_chat_complete(window, &request.request_id)?;
        return Ok(());
    }

    let mut stream = response.bytes_stream();
    let mut buffer = String::new();

    while let Some(chunk) = stream.next().await {
        if take_cancel_request(state, &request.request_id)? {
            emit_chat_complete(window, &request.request_id)?;
            return Ok(());
        }

        let chunk =
            chunk.map_err(|error| format_reqwest_error("Failed while reading stream", &error))?;
        buffer.push_str(&String::from_utf8_lossy(&chunk).replace("\r\n", "\n"));

        while let Some(split_at) = buffer.find("\n\n") {
            let block = buffer[..split_at].to_string();
            buffer = buffer[split_at + 2..].to_string();

            if handle_sse_block(window, &request.request_id, &block)? {
                emit_chat_complete(window, &request.request_id)?;
                return Ok(());
            }
        }
    }

    if !buffer.trim().is_empty() {
        let _ = handle_sse_block(window, &request.request_id, &buffer)?;
    }

    emit_chat_complete(window, &request.request_id)?;
    Ok(())
}

fn take_cancel_request(state: &ChatCancelState, request_id: &str) -> Result<bool, String> {
    Ok(state
        .canceled_requests
        .lock()
        .map_err(|_| "Could not lock chat cancellation state.".to_string())?
        .remove(request_id))
}

fn build_api_messages(
    request: &ChatStreamRequest,
    system_prompt: &str,
) -> Result<Vec<Value>, String> {
    let mut messages = vec![json!({
        "role": "system",
        "content": system_prompt,
    })];

    for (index, message) in request.messages.iter().enumerate() {
        let role = message.role.trim();
        if role != "user" && role != "assistant" {
            continue;
        }

        let is_last_message = index + 1 == request.messages.len();
        let images = request.images.as_ref().filter(|items| !items.is_empty());

        if role == "user" && is_last_message && images.is_some() {
            let mut content = vec![json!({
                "type": "text",
                "text": message.content,
            })];

            for image in images.unwrap() {
                if !image.mime_type.starts_with("image/")
                    || !image.data_url.starts_with("data:image/")
                {
                    return Err("Image payload must be an image data URL.".to_string());
                }

                content.push(json!({
                    "type": "image_url",
                    "image_url": {
                        "url": image.data_url,
                    },
                }));
            }

            messages.push(json!({
                "role": role,
                "content": content,
            }));
        } else {
            messages.push(json!({
                "role": role,
                "content": message.content,
            }));
        }
    }

    Ok(messages)
}

fn handle_sse_block(window: &tauri::Window, request_id: &str, block: &str) -> Result<bool, String> {
    for line in block.lines() {
        let line = line.trim();
        let Some(data) = line.strip_prefix("data:") else {
            continue;
        };
        let data = data.trim();

        if data == "[DONE]" {
            return Ok(true);
        }

        let value = serde_json::from_str::<Value>(data)
            .map_err(|error| format!("Failed to parse stream chunk: {error}"))?;

        if let Some(delta) = value
            .pointer("/choices/0/delta/content")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
        {
            emit_chat_delta(window, request_id, delta)?;
        }
    }

    Ok(false)
}

fn emit_chat_delta(window: &tauri::Window, request_id: &str, delta: &str) -> Result<(), String> {
    window
        .emit(
            "llm-chat-delta",
            ChatDeltaEvent {
                request_id: request_id.to_string(),
                delta: delta.to_string(),
            },
        )
        .map_err(|error| format!("Failed to emit chat delta: {error}"))
}

fn emit_chat_complete(window: &tauri::Window, request_id: &str) -> Result<(), String> {
    window
        .emit(
            "llm-chat-complete",
            ChatCompleteEvent {
                request_id: request_id.to_string(),
            },
        )
        .map_err(|error| format!("Failed to emit chat completion: {error}"))
}

fn emit_chat_error(window: &tauri::Window, request_id: &str, message: &str) -> Result<(), String> {
    window
        .emit(
            "llm-chat-error",
            ChatErrorEvent {
                request_id: request_id.to_string(),
                message: message.to_string(),
            },
        )
        .map_err(|error| format!("Failed to emit chat error: {error}"))
}

fn chat_completions_endpoint(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');

    if trimmed.ends_with("/chat/completions") {
        trimmed.to_string()
    } else {
        format!("{trimmed}/chat/completions")
    }
}

fn format_reqwest_error(context: &str, error: &reqwest::Error) -> String {
    let mut parts = vec![format!("{context}: {error}")];
    let mut source = error.source();

    while let Some(error_source) = source {
        parts.push(format!("caused by: {error_source}"));
        source = error_source.source();
    }

    parts.join(" | ")
}

fn load_llm_config(app: Option<&tauri::AppHandle>) -> LlmConfig {
    let env_values = load_env_values(app);
    let read_value = |key: &str| {
        env::var(key)
            .ok()
            .filter(|value| !value.trim().is_empty())
            .or_else(|| env_values.get(key).cloned())
            .map(|value| value.trim().to_string())
    };

    let prompt_from_env = read_value("OURDESKPET_SYSTEM_PROMPT");
    let prompt_file = read_value("OURDESKPET_PROMPT_FILE");
    let (system_prompt, prompt_source) = match prompt_from_env {
        Some(prompt) => (prompt, "environment".to_string()),
        None => read_prompt_file(app, prompt_file.as_deref())
            .unwrap_or_else(|| (PROMPT_FALLBACK.to_string(), "fallback".to_string())),
    };

    LlmConfig {
        api_key: read_value("OURDESKPET_API_KEY"),
        base_url: read_value("OURDESKPET_BASE_URL").unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
        model: read_value("OURDESKPET_MODEL"),
        model_options: read_value("OURDESKPET_MODEL_OPTIONS")
            .map(|value| parse_model_options(&value))
            .unwrap_or_default(),
        system_prompt,
        prompt_source,
    }
}

fn parse_model_options(value: &str) -> Vec<String> {
    value
        .split([',', '\n', ';'])
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn load_env_values(app: Option<&tauri::AppHandle>) -> HashMap<String, String> {
    let mut values = HashMap::new();

    for path in candidate_env_paths(app) {
        if let Ok(content) = fs::read_to_string(path) {
            for (key, value) in parse_env_file(&content) {
                values.entry(key).or_insert(value);
            }
        }
    }

    values
}

fn parse_env_file(content: &str) -> HashMap<String, String> {
    let mut values = HashMap::new();

    for raw_line in content.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }

        let Some((key, value)) = line.split_once('=') else {
            continue;
        };

        let value = value
            .trim()
            .trim_matches('"')
            .trim_matches('\'')
            .to_string();
        values.insert(key.trim().to_string(), value);
    }

    values
}

fn candidate_env_paths(app: Option<&tauri::AppHandle>) -> Vec<PathBuf> {
    let mut paths = Vec::new();

    if let Ok(path) = env::var("OURDESKPET_ENV_FILE") {
        paths.push(PathBuf::from(path));
    }

    if let Ok(current_dir) = env::current_dir() {
        paths.push(current_dir.join(".env"));
        if let Some(parent) = current_dir.parent() {
            paths.push(parent.join(".env"));
        }
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    paths.push(manifest_dir.join(".env"));
    if let Some(app_dir) = manifest_dir.parent() {
        paths.push(app_dir.join(".env"));
        if let Some(project_dir) = app_dir.parent() {
            paths.push(project_dir.join(".env"));
        }
    }

    if let Some(app) = app {
        if let Ok(config_dir) = app.path().app_config_dir() {
            paths.push(config_dir.join(".env"));
            paths.push(config_dir.join("config.env"));
        }
    }

    dedupe_paths(paths)
}

fn read_prompt_file(
    app: Option<&tauri::AppHandle>,
    prompt_file: Option<&str>,
) -> Option<(String, String)> {
    for path in candidate_prompt_paths(app, prompt_file) {
        if let Ok(content) = fs::read_to_string(&path) {
            let trimmed = content.trim();
            if !trimmed.is_empty() {
                return Some((trimmed.to_string(), path.display().to_string()));
            }
        }
    }

    None
}

fn candidate_prompt_paths(
    app: Option<&tauri::AppHandle>,
    prompt_file: Option<&str>,
) -> Vec<PathBuf> {
    let mut paths = Vec::new();

    if let Some(path) = prompt_file.filter(|value| !value.trim().is_empty()) {
        paths.push(PathBuf::from(path));
    }

    if let Ok(path) = env::var("OURDESKPET_PROMPT_FILE") {
        paths.push(PathBuf::from(path));
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(app_dir) = manifest_dir.parent() {
        if let Some(project_dir) = app_dir.parent() {
            paths.push(project_dir.join("prompts").join("rina_system_prompt.md"));
        }
    }

    if let Some(app) = app {
        if let Ok(config_dir) = app.path().app_config_dir() {
            paths.push(config_dir.join("rina_system_prompt.md"));
        }
    }

    dedupe_paths(paths)
}

fn dedupe_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut deduped = Vec::new();

    for path in paths {
        if !deduped
            .iter()
            .any(|existing: &PathBuf| same_path(existing, &path))
        {
            deduped.push(path);
        }
    }

    deduped
}

fn same_path(left: &Path, right: &Path) -> bool {
    left.to_string_lossy()
        .eq_ignore_ascii_case(&right.to_string_lossy())
}

fn extract_error_message(body: &str) -> Option<String> {
    serde_json::from_str::<Value>(body).ok().and_then(|value| {
        value
            .pointer("/error/message")
            .and_then(Value::as_str)
            .or_else(|| value.pointer("/message").and_then(Value::as_str))
            .map(ToString::to_string)
    })
}
