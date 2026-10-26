mod agent;
mod api_profiles;
mod art_custom;
mod billing;
mod billing_connection;
mod chat_export;
mod chat_file_attachments;
mod chat_history;
mod chat_search;
mod chat_settings;
mod code_file_parser;
mod diagnostics;
mod extension_tools;
mod pet_placement;
mod pet_region;
mod project_agent;
mod project_locations;
mod project_settings;
mod request_registry;
mod rinatomo;
mod release_profile;
mod runtime_paths;
mod runtime_skills;
mod sse;
mod startup;
mod stream_chat;
mod voice;
mod work_file_parser;
use arboard::{Clipboard, Error as ClipboardError};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine};
use futures_util::{
    future::{AbortHandle, Abortable},
    StreamExt,
};
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
    search_backend: String,
    context_chars: usize,
    search_mode: String,
    project_read_enabled: bool,
}

#[derive(Debug, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct ChatStreamRequest {
    request_id: String,
    messages: Vec<ChatMessage>,
    images: Option<Vec<ImagePayload>>,
    files: Option<Vec<chat_file_attachments::ParsedAttachment>>,
    #[serde(default)]
    search_mode: String,
    #[serde(default)]
    chat_mode: String,
    current_date: Option<String>,
    session_id: String,
    turn_id: String,
    #[serde(default)]
    voice_reply: bool,
    #[serde(skip)]
    history_summary: Option<String>,
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
    options: chat_settings::Options,
}

#[derive(Default)]
struct ChatCancelState {
    active_requests: Mutex<request_registry::RequestRegistry>,
}

#[tauri::command]
fn llm_config_status(app: tauri::AppHandle) -> Result<LlmConfigStatus, String> {
    let config = load_llm_config(Some(&app))?;
    let search_available = chat_search::available(&config);
    let search_backend = chat_search::label(&config).to_string();

    Ok(LlmConfigStatus {
        has_api_key: config
            .api_key
            .as_ref()
            .is_some_and(|value| !value.trim().is_empty()),
        base_url: config.base_url,
        model: config.model,
        model_options: config.model_options,
        prompt_source: config.prompt_source,
        search_available,
        search_backend,
        context_chars: config.context_chars,
        search_mode: config.options.search_mode.clone(),
        project_read_enabled: config.options.project_read_enabled,
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
        let mut active = state
            .active_requests
            .lock()
            .map_err(|_| "Could not lock active requests.")?;
        active.register(request.request_id.clone(), abort)?;
    }
    let result = Abortable::new(chat_history::run(&window, &request, &config), registration).await;
    let _ = window.app_handle().emit_to(
        "main",
        "deskpet-speech-state",
        json!({"requestId":request.request_id,"active":false}),
    );
    state
        .active_requests
        .lock()
        .map_err(|_| "Could not lock active requests.")?
        .remove(&request.request_id);
    match result {
        Err(_) => {
            emit_chat_complete(&window, &request.request_id, "cancelled")?;
            Ok("cancelled".into())
        }
        Ok(Err(error)) => {
            let _ = emit_chat_error(&window, &request.request_id, &error);
            Err(error)
        }
        Ok(Ok(status)) => {
            emit_chat_complete(&window, &request.request_id, status)?;
            if status != "completed" {
                return Ok(status.into());
            }
            // The native producer is independent of the dialogue webview lifecycle.
            let _ = window.app_handle().emit_to(
                "main",
                "deskpet-task-event",
                json!({
                    "source": "chat", "taskId": request.request_id, "status": "completed"
                }),
            );
            Ok(status.into())
        }
    }
}

#[tauri::command]
fn cancel_chat_stream(state: State<'_, ChatCancelState>, request_id: String) -> Result<(), String> {
    state
        .active_requests
        .lock()
        .map_err(|_| "Could not lock active requests.")?
        .cancel(&request_id)
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
    let pet = app
        .get_webview_window("main")
        .ok_or("Pet window is unavailable.")?;
    #[cfg(target_os = "windows")]
    {
        // SW_SHOWNOACTIVATE restores the pet without stealing keyboard focus.
        // Obtain the live HWND on the UI thread, not across an asynchronous gap.
        let ui_pet = pet.clone();
        pet.run_on_main_thread(move || {
            if let Ok(hwnd) = ui_pet.hwnd() {
                #[link(name = "user32")]
                extern "system" {
                    fn ShowWindow(hwnd: *mut std::ffi::c_void, command: i32) -> i32;
                }
                // SAFETY: HWND belongs to this live Tauri window; ShowWindow takes no borrowed buffers.
                unsafe {
                    ShowWindow(hwnd.0 as *mut std::ffi::c_void, 4);
                }
            }
        })
        .map_err(|error| error.to_string())?;
    }
    #[cfg(not(target_os = "windows"))]
    {
        pet.unminimize().map_err(|error| error.to_string())?;
        pet.show().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
async fn pet_left_button_down(window: tauri::WebviewWindow) -> Result<bool, String> {
    if window.label() != "main" {
        return Err("Only the pet can check its drag gesture".into());
    }
    #[cfg(target_os = "windows")]
    {
        #[link(name = "user32")]
        extern "system" {
            fn GetAsyncKeyState(key: i32) -> i16;
            fn GetSystemMetrics(index: i32) -> i32;
        }
        // SAFETY: no pointers or buffers, queries only the current left mouse button.
        return Ok(unsafe { GetAsyncKeyState(if GetSystemMetrics(23) != 0 { 2 } else { 1 }) } < 0);
    }
    #[cfg(not(target_os = "windows"))]
    Ok(false)
}

/// Use the OS foreground window, not WebView keyboard-focus bookkeeping.
#[tauri::command]
fn dialogue_is_reading(app: tauri::AppHandle) -> bool {
    let Some(dialogue) = app.get_webview_window("dialogue") else {
        return false;
    };
    #[cfg(target_os = "windows")]
    {
        let Ok(handle) = dialogue.hwnd() else {
            return false;
        };
        #[link(name = "user32")]
        extern "system" {
            fn GetForegroundWindow() -> *mut std::ffi::c_void;
            fn GetAncestor(hwnd: *mut std::ffi::c_void, flags: u32) -> *mut std::ffi::c_void;
            fn IsWindowVisible(hwnd: *mut std::ffi::c_void) -> i32;
            fn IsIconic(hwnd: *mut std::ffi::c_void) -> i32;
        }
        let hwnd = handle.0 as *mut std::ffi::c_void;
        // SAFETY: live application HWND; read-only Win32 queries without borrowed buffers.
        unsafe {
            let foreground = GetForegroundWindow();
            return IsWindowVisible(hwnd) != 0
                && IsIconic(hwnd) == 0
                && !foreground.is_null()
                && (foreground == hwnd || GetAncestor(foreground, 2) == hwnd);
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        dialogue.is_visible().unwrap_or(false)
            && !dialogue.is_minimized().unwrap_or(true)
            && dialogue.is_focused().unwrap_or(false)
    }
}

#[tauri::command]
async fn prepare_quit_app(window: tauri::Window, app: tauri::AppHandle) -> Result<(), String> {
    if window.label() != "main" {
        return Err("只能从桌宠主窗口退出".into());
    }
    chat_export::storage::flush_before_quit(&app).await
}

#[tauri::command]
fn complete_quit_app(window: tauri::Window, app: tauri::AppHandle) -> Result<(), String> {
    if window.label() != "main" {
        return Err("只能从桌宠主窗口退出".into());
    }
    app.exit(0);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    release_profile::initialize();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second shortcut launch should return to the existing pet.
            if let Some(pet) = app.get_webview_window("main") {
                let _ = pet.unminimize();
                let _ = pet.show();
                let _ = pet.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .manage(ChatCancelState::default())
        .manage(chat_history::HistoryState::default())
        .manage(chat_export::ConversationFiles::default())
        .setup(|app| {
            // Only the pet opts out of the Windows taskbar slide animation.
            // Chat/settings and global accessibility/system preferences are untouched.
            #[cfg(target_os = "windows")]
            if let Some(pet) = app.get_webview_window("main") {
                if let Ok(hwnd) = pet.hwnd() {
                    #[link(name = "dwmapi")]
                    extern "system" {
                        fn DwmSetWindowAttribute(
                            hwnd: *mut std::ffi::c_void,
                            attribute: u32,
                            value: *const std::ffi::c_void,
                            size: u32,
                        ) -> i32;
                    }
                    let disabled: i32 = 1;
                    // SAFETY: live HWND, BOOL buffer and its exact byte size.
                    let result = unsafe {
                        DwmSetWindowAttribute(
                            hwnd.0 as *mut std::ffi::c_void,
                            3,
                            &disabled as *const _ as *const std::ffi::c_void,
                            4,
                        )
                    };
                    if result < 0 {
                        eprintln!("Pet DWM transition override unavailable: {result:#x}");
                    }
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.emit("deskpet-exit-requested", ());
                }
            }
            if window.label() == "dialogue" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
            if window.label() == "dialogue" && matches!(event, tauri::WindowEvent::Destroyed) {
                if let Ok(active) = window
                    .app_handle()
                    .state::<ChatCancelState>()
                    .active_requests
                    .lock()
                {
                    for abort in active.values() {
                        abort.abort();
                    }
                }
            }
            if window.label() == "dialogue"
                && matches!(event, tauri::WindowEvent::Focused(true))
                && dialogue_is_reading(window.app_handle().clone())
            {
                let _ = window.app_handle().emit_to(
                    "main",
                    "deskpet-task-read",
                    json!({"source":"chat"}),
                );
            }
        })
        .manage(voice::input::VoiceInputState::default())
        .manage(agent::proposals::AgentProposals::default())
        .invoke_handler(tauri::generate_handler![
            pet_region::set_pet_region,
            pet_placement::park_pet_beside_window,
            pet_left_button_down,
            prepare_quit_app,
            complete_quit_app,
            reveal_pet_notification,
            dialogue_is_reading,
            llm_config_status,
            api_profiles::api_profiles_list,
            api_profiles::api_profiles_save,
            api_profiles::api_profiles_activate,
            chat_settings::chat_settings_get,
            billing::billing_status,
            billing::billing_balance,
            billing_connection::billing_connection_save,
            art_custom::art_custom_list,
            art_custom::art_custom_save,
            art_custom::art_custom_rename,
            art_custom::art_custom_delete,
            chat_settings::chat_settings_save,
            project_settings::project_settings_pending,
            project_settings::project_settings_decide,
            startup::startup_get,
            startup::startup_set,
            diagnostics::diagnostics_get,
            extension_tools::extension_status,
            extension_tools::extension_connect,
            extension_tools::extension_disconnect,
            extension_tools::extension_launch,
            extension_tools::extension_preview,
            extension_tools::extension_select_video,
            extension_tools::extension_yaki_action,
            extension_tools::extension_select_destination,
            rinatomo::rinatomo_status,
            rinatomo::rinatomo_action,
            rinatomo::rinatomo_update,
            rinatomo::rinatomo_launch,
            chat_stream,
            cancel_chat_stream,
            chat_history::clear_chat_history,
            chat_history::restore_chat_history,
            chat_export::chat_export_title,
            chat_export::chat_export_save,
            chat_export::chat_import_choose,
            chat_export::chat_import_read,
            chat_export::storage::chat_storage_settings,
            chat_export::storage::chat_storage_prepare_directory,
            chat_export::storage::chat_storage_enable,
            chat_export::storage::chat_storage_choose,
            chat_export::storage::chat_storage_list,
            chat_export::storage::chat_storage_save,
            chat_export::storage::chat_storage_read,
            chat_export::storage::chat_storage_forget,
            chat_export::storage::chat_storage_rename,
            chat_export::storage::chat_storage_flush_done,
            work_file_parser::parse_work_file,
            code_file_parser::parse_code_file,
            capture_screen_region,
            close_capture_window,
            start_system_screen_clip,
            read_clipboard_image,
            voice::input::voice_input_status,
            voice::input::voice_input_start,
            voice::input::voice_input_stop,
            voice::input::voice_input_cancel,
            voice::output::voice_output_play,
            voice::output::voice_output_settings_get,
            voice::output::voice_output_settings_save,
            voice::tts::voice_reply_synthesize,
            agent::proposals::agent_proposal_confirm,
            agent::proposals::agent_proposal_decline,
            agent::proposals::agent_task_start,
            agent::proposals::agent_task_status,
            agent::proposals::agent_task_export,
            agent::proposals::agent_open_yaki,
            chat_export::storage::chat_storage_delete,
            chat_export::storage::chat_storage_delete_file
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    billing::start(app.handle().clone());
    app.run(|_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            rinatomo::shutdown_if_desk_owned();
        }
    });
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
    if !delta.is_empty() {
        let _ = window.app_handle().emit_to(
            "main",
            "deskpet-speech-state",
            json!({"requestId":request_id,"active":true}),
        );
    }
    Ok(())
}

fn emit_chat_complete(
    window: &tauri::Window,
    request_id: &str,
    status: &str,
) -> Result<(), String> {
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

fn load_llm_config(app: Option<&tauri::AppHandle>) -> Result<LlmConfig, String> {
    let api = api_profiles::resolve(app)?;
    let env_values = load_env_values(app)?;
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

    let options = chat_settings::Options::from_reader(&read_value);
    options.validate()?;
    Ok(LlmConfig {
        api_key: api.key,
        base_url: api.url,
        model: api.model,
        model_options: read_value("OURDESKPET_MODEL_OPTIONS")
            .map(|value| parse_model_options(&value))
            .unwrap_or_default(),
        system_prompt,
        prompt_source,
        tavily_key: read_value("TAVILY_API_KEY").filter(|s| !s.is_empty()),
        tavily_url: options.search_url.clone(),
        search_enabled: options.search_enabled,
        context_chars: options.context_chars,
        read_timeout_secs: options.read_timeout,
        options,
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

fn load_env_values(app: Option<&tauri::AppHandle>) -> Result<HashMap<String, String>, String> {
    let path = api_profiles::location(app)?;
    api_profiles::parse(&api_profiles::read(&path)?)
}

/// Companion or executable ancestry identifies this installation after moving the group.
pub(crate) fn runtime_project_root() -> Option<PathBuf> {
    let exe = env::current_exe().ok();
    // A distributed release must never reopen the checkout used to compile it.
    #[cfg(debug_assertions)]
    let development = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent);
    #[cfg(not(debug_assertions))]
    let development = None;
    // Shared compiler output may be inside a developer checkout. Debug/test
    // builds must prefer this release checkout, never that cache's ancestry.
    #[cfg(debug_assertions)]
    if let Some(root) = development.filter(|root| root.join("release-profile.json").is_file()) {
        return runtime_paths::project_root(None, Some(root));
    }
    runtime_paths::project_root(exe.as_deref().and_then(Path::parent), development)
        .filter(|root| root.join("release-profile.json").is_file())
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
    let root = runtime_project_root();
    let env_file = api_profiles::location(app).ok();
    let config_dir = app.and_then(|app| app.path().app_config_dir().ok());
    runtime_paths::prompt_files(
        prompt_file,
        root.as_deref(),
        env_file.as_deref(),
        config_dir.as_deref(),
    )
}
