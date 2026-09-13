mod pet_placement;
mod api_profiles;
mod pet_region;
mod sse;
mod chat_search;
mod stream_chat;
use arboard::{Clipboard, Error as ClipboardError};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine};
use futures_util::{StreamExt, future::{AbortHandle, Abortable}};
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
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
const PROMPT_FALLBACK: &str = include_str!("../../../prompts/rina_system_prompt.md");

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmConfigStatus {
    has_api_key: bool,
    base_url: String,
    model: Option<String>,
    model_options: Vec<String>,
    prompt_source: String,
    search_available: bool,
    context_chars: usize,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatStreamRequest {
    request_id: String,
    messages: Vec<ChatMessage>,
    images: Option<Vec<ImagePayload>>,
    #[serde(default)]
    search_mode: String,
    current_date: Option<String>,
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
    status: String,
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
    tavily_key: Option<String>,
    tavily_url: String,
    search_enabled: bool,
    context_chars: usize,
    read_timeout_secs: u64,
}

#[derive(Default)]
struct ChatCancelState {
    active_requests: Mutex<HashMap<String, AbortHandle>>,
}

#[tauri::command]
fn llm_config_status(app: tauri::AppHandle) -> Result<LlmConfigStatus,String> {
    let config = load_llm_config(Some(&app))?;

    Ok(LlmConfigStatus {
        has_api_key: config
            .api_key
            .as_ref()
            .is_some_and(|value| !value.trim().is_empty()),
        base_url: config.base_url,
        model: config.model,
        model_options: config.model_options,
        prompt_source: config.prompt_source,
        search_available: config.search_enabled && config.tavily_key.is_some(),
        context_chars: config.context_chars,
    })
}

#[tauri::command]
async fn chat_stream(
    window: tauri::Window,
    state: State<'_, ChatCancelState>,
    request: ChatStreamRequest,
) -> Result<String, String> {
    let config = load_llm_config(Some(window.app_handle()))?;

    let (abort, registration) = AbortHandle::new_pair();
    {
        let mut active = state.active_requests.lock().map_err(|_| "Could not lock active requests.")?;
        if active.contains_key(&request.request_id) { return Err("Duplicate request ID.".into()); }
        active.insert(request.request_id.clone(), abort);
    }
    let result = Abortable::new(stream_chat::run(&window, &request, &config), registration).await;
    let _ = window.app_handle().emit_to("main", "deskpet-speech-state", json!({"requestId":request.request_id,"active":false}));
    state.active_requests.lock().map_err(|_| "Could not lock active requests.")?.remove(&request.request_id);
    match result {
        Err(_) => { emit_chat_complete(&window, &request.request_id, "cancelled")?; Ok("cancelled".into()) },
        Ok(Err(error)) => { let _ = emit_chat_error(&window, &request.request_id, &error); Err(error) }
        Ok(Ok(status)) => {
            emit_chat_complete(&window, &request.request_id, status)?;
            if status != "completed" { return Ok(status.into()); }
            // The native producer is independent of the dialogue webview lifecycle.
            let _ = window.app_handle().emit_to("main", "deskpet-task-event", json!({
                "source": "chat", "taskId": request.request_id, "status": "completed"
            }));
            Ok(status.into())
        }
    }
}

#[tauri::command]
fn cancel_chat_stream(state: State<'_, ChatCancelState>, request_id: String) -> Result<(), String> {
    if let Some(abort) = state.active_requests.lock().map_err(|_| "Could not lock active requests.")?.get(&request_id) {
        abort.abort();
    }
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


#[tauri::command]
fn reveal_pet_notification(app: tauri::AppHandle) -> Result<(), String> {
    let pet = app.get_webview_window("main").ok_or("Pet window is unavailable.")?;
    #[cfg(target_os = "windows")]
    {
        // SW_SHOWNOACTIVATE restores the pet without stealing keyboard focus.
        // Obtain the live HWND on the UI thread, not across an asynchronous gap.
        let ui_pet = pet.clone();
        pet.run_on_main_thread(move || {
            if let Ok(hwnd) = ui_pet.hwnd() {
                #[link(name = "user32")]
                extern "system" { fn ShowWindow(hwnd: *mut std::ffi::c_void, command: i32) -> i32; }
                // SAFETY: HWND belongs to this live Tauri window; ShowWindow takes no borrowed buffers.
                unsafe { ShowWindow(hwnd.0 as *mut std::ffi::c_void, 4); }
            }
        }).map_err(|error| error.to_string())?;
    }
    #[cfg(not(target_os = "windows"))]
    { pet.unminimize().map_err(|error| error.to_string())?; pet.show().map_err(|error| error.to_string())?; }
    Ok(())
}


#[tauri::command]
async fn pet_left_button_down(window: tauri::WebviewWindow) -> Result<bool,String> {
    if window.label() != "main" { return Err("Only the pet can check its drag gesture".into()); }
    #[cfg(target_os="windows")]
    {
        #[link(name="user32")]
        extern "system" { fn GetAsyncKeyState(key:i32)->i16; fn GetSystemMetrics(index:i32)->i32; }
        // SAFETY: no pointers or buffers, queries only the current left mouse button.
        return Ok(unsafe { GetAsyncKeyState(if GetSystemMetrics(23) != 0 {2} else {1}) } < 0);
    }
    #[cfg(not(target_os="windows"))]
    Ok(false)
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) { app.exit(0); }

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(ChatCancelState::default())
        .on_window_event(|window, event| {
            if window.label()=="dialogue" {
                if let tauri::WindowEvent::CloseRequested { api, .. }=event {
                    api.prevent_close();
                    let _=window.hide();
                }
            }
            if window.label()=="dialogue" && matches!(event,tauri::WindowEvent::Destroyed) {
                if let Ok(active)=window.app_handle().state::<ChatCancelState>().active_requests.lock() {
                    for abort in active.values(){abort.abort();}
                }
            }
            if window.label() == "dialogue" && matches!(event, tauri::WindowEvent::Focused(true)) {
                let _ = window.app_handle().emit_to("main", "deskpet-task-read", json!({"source":"chat"}));
            }
        })
        .invoke_handler(tauri::generate_handler![
            pet_region::set_pet_region,
            pet_placement::park_pet_beside_window,
            pet_left_button_down,
            quit_app,
            reveal_pet_notification,
            llm_config_status,
            api_profiles::api_profiles_list,
            api_profiles::api_profiles_save,
            api_profiles::api_profiles_activate,
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

fn emit_chat_delta(window: &tauri::Window, request_id: &str, delta: &str) -> Result<(), String> {
    window
        .emit(
            "llm-chat-delta",
            ChatDeltaEvent {
                request_id: request_id.to_string(),
                delta: delta.to_string(),
            },
        )
        .map_err(|error| format!("Failed to emit chat delta: {error}"))?;
    if !delta.is_empty() { let _ = window.app_handle().emit_to("main", "deskpet-speech-state", json!({"requestId":request_id,"active":true})); }
    Ok(())
}

fn emit_chat_complete(window: &tauri::Window, request_id: &str, status: &str) -> Result<(), String> {
    window
        .emit(
            "llm-chat-complete",
            ChatCompleteEvent {
                request_id: request_id.to_string(),
                status: status.to_string(),
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

fn load_llm_config(app: Option<&tauri::AppHandle>) -> Result<LlmConfig,String> {
    let api = api_profiles::resolve(app)?;
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

    Ok(LlmConfig {
        api_key: api.key,
        base_url: api.url,
        model: api.model,
        model_options: read_value("OURDESKPET_MODEL_OPTIONS")
            .map(|value| parse_model_options(&value))
            .unwrap_or_default(),
        system_prompt,
        prompt_source,
        tavily_key: read_value("TAVILY_API_KEY").filter(|s|!s.is_empty()),
        tavily_url: read_value("OURDESKPET_TAVILY_BASE_URL").filter(|s|!s.is_empty()).unwrap_or_else(||"https://api.tavily.com".into()),
        search_enabled: read_value("OURDESKPET_SEARCH_ENABLED").as_deref()!=Some("false"),
        context_chars: read_value("OURDESKPET_CONTEXT_CHARS").and_then(|s|s.parse::<usize>().ok()).unwrap_or(24000).clamp(4000,100000),
        read_timeout_secs: read_value("OURDESKPET_READ_TIMEOUT_SECS").and_then(|s|s.parse::<u64>().ok()).unwrap_or(180).clamp(15,600),
    })
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

