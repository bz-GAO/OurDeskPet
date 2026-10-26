//! Managed local JSON conversations. The UI never supplies an arbitrary write path.
use super::*;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
static STORE_LOCK: Mutex<()> = Mutex::new(());
type QuitSender = tokio::sync::oneshot::Sender<Result<(), String>>;
static QUIT_ACK: Mutex<Option<QuitSender>> = Mutex::new(None);
pub async fn flush_before_quit(app: &tauri::AppHandle) -> Result<(), String> {
    if app.get_webview_window("dialogue").is_none() {
        return Ok(());
    }
    let (sender, receiver) = tokio::sync::oneshot::channel();
    {
        let mut pending = QUIT_ACK.lock().map_err(|_| "退出状态不可用")?;
        if pending.is_some() {
            return Err("正在保存对话，请稍候".into());
        }
        *pending = Some(sender);
    }
    if app.emit_to("dialogue", "deskpet-before-quit", ()).is_err() {
        *QUIT_ACK.lock().map_err(|_| "退出状态不可用")? = None;
        return Err("无法确认对话已保存，请重试退出".into());
    }
    let result = tokio::time::timeout(Duration::from_secs(5), receiver).await;
    *QUIT_ACK.lock().map_err(|_| "退出状态不可用")? = None;
    result
        .map_err(|_| "对话保存超时，尚未退出")?
        .map_err(|_| "对话保存中断，尚未退出")?
}
#[tauri::command]
pub fn chat_storage_flush_done(window: tauri::Window, error: Option<String>) -> Result<(), String> {
    if window.label() != "dialogue" {
        return Err("无效的退出确认来源".into());
    }
    if let Some(sender) = QUIT_ACK.lock().map_err(|_| "退出状态不可用")?.take() {
        let _ = sender.send(if error.is_some() {
            Err("对话保存失败，尚未退出；请重试或选择不保存".into())
        } else {
            Ok(())
        });
    }
    Ok(())
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
struct StoreConfig {
    enabled: bool,
    directory: Option<PathBuf>,
    hidden: BTreeMap<PathBuf, BTreeSet<String>>,
}
impl Default for StoreConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            directory: None,
            hidden: BTreeMap::new(),
        }
    }
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StorageSettings {
    enabled: bool,
    directory: String,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StorageRecord {
    pub id: String,
    pub path: String,
    pub directory: String,
    pub title: String,
    pub mode: String,
    pub revision: String,
    pub visible: bool,
}
#[derive(Serialize)]
pub struct StorageList {
    records: Vec<StorageRecord>,
    skipped: usize,
}

fn config_path() -> Result<PathBuf, String> {
    Ok(billing::home("RinaDesk")?.join("chat-storage.json"))
}
fn read_config() -> Result<StoreConfig, String> {
    let path = config_path()?;
    billing::no_redirect(&path)?;
    use std::io::Read;
    let bytes = fs::File::open(&path).and_then(|file| {
        let mut bytes = Vec::new();
        file.take(128 * 1024 + 1).read_to_end(&mut bytes)?;
        Ok(bytes)
    });
    match bytes {
        Ok(bytes) if bytes.len() <= 128 * 1024 => {
            serde_json::from_slice(&bytes).map_err(|_| "对话存储配置损坏，未使用默认设置".into())
        }
        Ok(_) => Err("对话存储配置过大".into()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(StoreConfig::default()),
        Err(_) => Err("对话存储配置无法读取".into()),
    }
}
fn root(config: &StoreConfig) -> Result<PathBuf, String> {
    let path = match &config.directory {
        Some(directory) => directory.clone(),
        None => billing::home("RinaDesk")?.join("Conversations"),
    };
    if !path.is_absolute() {
        return Err("对话目录必须是完整路径".into());
    }
    billing::no_redirect(&path)?;
    Ok(path)
}
fn persist_config(config: &StoreConfig) -> Result<(), String> {
    let path = config_path()?;
    billing::no_redirect(&path)?;
    fs::create_dir_all(path.parent().ok_or("资料目录无效")?).map_err(|_| "无法创建资料目录")?;
    let bytes = serde_json::to_vec_pretty(config).map_err(|_| "无法保存对话设置")?;
    if bytes.len() > 128 * 1024 {
        return Err("对话存储配置过大".into());
    }
    write_document(&path, &bytes)
}
fn snapshot(config: &StoreConfig) -> Result<StorageSettings, String> {
    Ok(StorageSettings {
        enabled: config.enabled,
        directory: root(config)?.to_string_lossy().into_owned(),
    })
}
fn check_window(window: &tauri::Window, settings_only: bool) -> Result<(), String> {
    if window.label() == "settings" || (!settings_only && window.label() == "dialogue") {
        Ok(())
    } else {
        Err("请在对话或设置窗口操作".into())
    }
}
fn valid_id(id: &str) -> bool {
    id.len() == 36
        && id.bytes().enumerate().all(|(i, b)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}
fn document_path(directory: &Path, id: &str) -> Result<PathBuf, String> {
    if !valid_id(id) {
        return Err("对话标识无效".into());
    }
    billing::no_redirect(directory)?;
    let path = directory.join(format!("conversation-{id}.json"));
    billing::no_redirect(&path)?;
    Ok(path)
}
fn read_managed(directory: &Path, id: &str, visible: bool) -> Result<ImportedConversation, String> {
    use std::io::Read;
    let path = document_path(directory, id)?;
    let mut bytes = Vec::new();
    fs::File::open(path)
        .map_err(|_| "对话文件无法读取")?
        .take(MAX_DOCUMENT_BYTES as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "对话文件无法读取")?;
    if bytes.len() > MAX_DOCUMENT_BYTES {
        return Err("对话文件过大".into());
    }
    let path = document_path(directory, id)?;
    let mut document = decode_document(&path, &bytes)?;
    document.storage = Some(StorageRecord {
        id: id.into(),
        path: path.to_string_lossy().into_owned(),
        directory: directory.to_string_lossy().into_owned(),
        title: document.title.clone(),
        mode: document.mode.clone(),
        revision: format!("{:x}", Sha256::digest(&bytes)),
        visible,
    });
    Ok(document)
}
fn record(directory: &Path, id: &str, visible: bool) -> Result<StorageRecord, String> {
    read_managed(directory, id, visible)?
        .storage
        .ok_or("对话记录无效".into())
}
fn save_at(
    directory: &Path,
    id: &str,
    expected: Option<&str>,
    request: SaveRequest,
) -> Result<StorageRecord, String> {
    let path = document_path(directory, id)?;
    if path.exists() {
        // A malformed or externally edited file is never overwritten silently.
        let current = record(directory, id, true)?;
        if expected != Some(current.revision.as_str()) {
            return Err("对话文件已变化，请重新载入后继续".into());
        }
    } else if expected.is_some() {
        return Err("原对话文件已移动，未另建副本".into());
    }
    let title = display_title(&request.title);
    let bytes = encode_document(request, title)?;
    fs::create_dir_all(directory).map_err(|_| "无法创建对话目录")?;
    write_document(&path, &bytes)?;
    record(directory, id, true)
}
#[tauri::command]
pub fn chat_storage_settings(window: tauri::Window) -> Result<StorageSettings, String> {
    check_window(&window, false)?;
    snapshot(&read_config()?)
}
#[tauri::command]
pub fn chat_storage_prepare_directory(window: tauri::Window) -> Result<String, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let directory = root(&read_config()?)?;
    fs::create_dir_all(&directory).map_err(|_| "无法创建对话目录")?;
    billing::no_redirect(&directory)?;
    Ok(directory.to_string_lossy().into_owned())
}
#[tauri::command]
pub fn chat_storage_enable(
    window: tauri::Window,
    enabled: bool,
) -> Result<StorageSettings, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let mut config = read_config()?;
    config.enabled = enabled;
    persist_config(&config)?;
    let _ = window.app_handle().emit("deskpet-chat-storage-changed", ());
    snapshot(&config)
}
#[tauri::command]
pub async fn chat_storage_choose(window: tauri::Window) -> Result<StorageSettings, String> {
    check_window(&window, true)?;
    let selected = tauri::async_runtime::spawn_blocking(choose_directory)
        .await
        .map_err(|_| "目录选择未完成")??;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let mut config = read_config()?;
    if let Some(path) = selected {
        billing::no_redirect(&path)?;
        if !path.is_absolute() || !path.is_dir() {
            return Err("请选择有效目录".into());
        }
        config.directory = Some(path.canonicalize().map_err(|_| "目录不可用")?);
        persist_config(&config)?;
        let _ = window.app_handle().emit("deskpet-chat-storage-changed", ());
    }
    snapshot(&config)
}
#[cfg(windows)]
fn choose_directory() -> Result<Option<PathBuf>, String> {
    use std::os::windows::process::CommandExt;
    let script="[Console]::OutputEncoding=[Text.Encoding]::UTF8; $folder=(New-Object -ComObject Shell.Application).BrowseForFolder(0,'选择对话保存目录',0,0); if ($null -eq $folder) { exit 2 }; [Console]::WriteLine($folder.Self.Path)";
    let output = Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ])
        .creation_flags(0x08000000)
        .output()
        .map_err(|_| "无法打开目录选择")?;
    if output.status.code() == Some(2) {
        return Ok(None);
    }
    if !output.status.success() {
        return Err("目录选择失败".into());
    }
    let value = String::from_utf8(output.stdout).map_err(|_| "目录无效")?;
    Ok(Some(PathBuf::from(value.trim())))
}
#[cfg(not(windows))]
fn choose_directory() -> Result<Option<PathBuf>, String> {
    Err("当前仅支持 Windows 目录选择".into())
}
#[tauri::command]
pub fn chat_storage_list(window: tauri::Window) -> Result<StorageList, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let config = read_config()?;
    let directory = root(&config)?;
    let entries = match fs::read_dir(&directory) {
        Ok(v) => v,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(StorageList {
                records: vec![],
                skipped: 0,
            })
        }
        Err(_) => return Err("对话目录无法读取".into()),
    };
    let mut records = Vec::new();
    let mut skipped = 0;
    let mut budget = 100 * 1024 * 1024u64;
    for (index, entry) in entries.take(2001).enumerate() {
        if index == 2000 {
            skipped += 1;
            break;
        }
        let Ok(entry) = entry else {
            skipped += 1;
            continue;
        };
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            continue;
        };
        let Some(id) = name
            .strip_prefix("conversation-")
            .and_then(|s| s.strip_suffix(".json"))
            .filter(|s| valid_id(s))
        else {
            continue;
        };
        if config
            .hidden
            .get(&directory)
            .is_some_and(|set| set.contains(id))
        {
            continue;
        }
        let size = entry.metadata().map(|m| m.len()).unwrap_or(u64::MAX);
        if size > budget || records.len() >= 500 {
            skipped += 1;
            continue;
        }
        budget -= size;
        match record(&directory, id, true) {
            Ok(value) => records.push(value),
            Err(_) => skipped += 1,
        }
    }
    records.sort_by_cached_key(|record| {
        std::cmp::Reverse(fs::metadata(&record.path).and_then(|m| m.modified()).ok())
    });
    Ok(StorageList { records, skipped })
}
#[tauri::command]
pub fn chat_storage_save(
    window: tauri::Window,
    id: String,
    directory: String,
    expected: Option<String>,
    request: SaveRequest,
) -> Result<StorageRecord, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let config = read_config()?;
    if !config.enabled {
        return Err("自动保存已关闭".into());
    }
    let current = root(&config)?;
    if current != PathBuf::from(directory) {
        return Err("保存目录已变化，请重试".into());
    }
    let mut value = save_at(&current, &id, expected.as_deref(), request)?;
    value.visible = !config
        .hidden
        .get(&current)
        .is_some_and(|set| set.contains(&id));
    Ok(value)
}
#[tauri::command]
pub fn chat_storage_read(
    window: tauri::Window,
    id: String,
) -> Result<ImportedConversation, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let config = read_config()?;
    let directory = root(&config)?;
    read_managed(&directory, &id, true)
}
#[tauri::command]
pub fn chat_storage_forget(window: tauri::Window, id: String) -> Result<(), String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let mut config = read_config()?;
    let directory = root(&config)?;
    document_path(&directory, &id)?;
    config.hidden.entry(directory).or_default().insert(id);
    persist_config(&config)
}

/// 永久删除托管对话：删除 JSON 文件并清掉隐藏标记。调用方需先经用户确认。
#[tauri::command]
pub fn chat_storage_delete(window: tauri::Window, id: String) -> Result<(), String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let mut config = read_config()?;
    let directory = root(&config)?;
    let path = document_path(&directory, &id)?;
    if !path.is_file() {
        return Err("对话文件不存在。".into());
    }
    fs::remove_file(&path).map_err(|_| "对话文件删除失败。")?;
    if let Some(set) = config.hidden.get_mut(&directory) {
        set.remove(&id);
    }
    persist_config(&config)
}

/// 永久删除导入的对话文件：仅允许删除已存在、不超过 5 MiB 的 .json 文件。
#[tauri::command]
pub fn chat_storage_delete_file(window: tauri::Window, path: String) -> Result<(), String> {
    check_window(&window, false)?;
    let path = PathBuf::from(path.trim());
    if path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.eq_ignore_ascii_case("json"))
        != Some(true)
    {
        return Err("只能删除 .json 对话文件。".into());
    }
    let metadata = fs::metadata(&path).map_err(|_| "对话文件不存在。")?;
    if !metadata.is_file() {
        return Err("只能删除对话文件。".into());
    }
    if metadata.len() > 5 * 1024 * 1024 {
        return Err("文件超出对话文件的大小范围，已拒绝删除。".into());
    }
    fs::remove_file(&path).map_err(|_| "对话文件删除失败。".to_string())
}
#[tauri::command]
pub fn chat_storage_rename(
    window: tauri::Window,
    id: String,
    expected: String,
    title: String,
) -> Result<StorageRecord, String> {
    check_window(&window, false)?;
    let _guard = STORE_LOCK.lock().map_err(|_| "对话存储忙")?;
    let directory = root(&read_config()?)?;
    let document = load_document(&document_path(&directory, &id)?)?;
    save_at(
        &directory,
        &id,
        Some(&expected),
        SaveRequest {
            title,
            mode: document.mode,
            exported_at: document.exported_at,
            messages: document.messages,
        },
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "12345678-1234-1234-1234-123456789abc";
    #[test]
    fn managed_files_are_confined_and_conflicts_preserve_bytes() {
        const RESTART: &str = "RINADESK_TEST_CHAT_RESTART";
        if let Some(folder) = env::var_os(RESTART) {
            let value = record(Path::new(&folder), ID, true).unwrap();
            assert_eq!(value.title, "Test");
            return;
        }
        let folder = env::temp_dir().join(format!(
            "chat-storage-{}-{}",
            std::process::id(),
            chrono::Utc::now().timestamp_nanos_opt().unwrap()
        ));
        fs::create_dir(&folder).unwrap();
        for id in [
            "../escape",
            "C:\\file",
            "a.json",
            "12345678-1234-1234-1234-123456789ab/",
        ] {
            assert!(document_path(&folder, id).is_err());
        }
        let sample = || {
            serde_json::from_value(json!({"title":"Test","mode":"chat","exportedAt":"2026-10-19","messages":[{"role":"user","content":"hello","state":"complete"}]})).unwrap()
        };
        let first = save_at(&folder, ID, None, sample()).unwrap();
        let path = document_path(&folder, ID).unwrap();
        let original = fs::read(&path).unwrap();
        let mut child = Command::new(env::current_exe().unwrap());
        child.args(["--exact","chat_export::storage::tests::managed_files_are_confined_and_conflicts_preserve_bytes"]).env(RESTART,&folder).current_dir(env::temp_dir());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            child.creation_flags(0x08000000);
        }
        assert!(
            child.output().unwrap().status.success(),
            "fresh-process managed file read failed"
        );
        assert!(save_at(&folder, ID, None, sample()).is_err());
        assert!(save_at(&folder, ID, Some("stale"), sample()).is_err());
        assert_eq!(fs::read(&path).unwrap(), original);
        let second = save_at(&folder, ID, Some(&first.revision), sample()).unwrap();
        assert_eq!(first.path, second.path);
        assert_eq!(fs::read_dir(&folder).unwrap().count(), 1);
        fs::write(&path, b"broken").unwrap();
        assert!(save_at(&folder, ID, Some(&second.revision), sample()).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"broken");
        fs::remove_file(path).unwrap();
        fs::remove_dir(folder).unwrap();
    }
}
