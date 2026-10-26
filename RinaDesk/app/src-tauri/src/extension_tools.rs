use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::io::{Read, Write};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use tauri::{AppHandle, Manager};

const TOOL_ID: &str = "rinayaki";

#[derive(Default, Serialize, Deserialize)]
struct Registry {
    rinayaki_path: Option<PathBuf>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolStatus {
    id: &'static str,
    connected: bool,
    available: bool,
    embedded_ready: bool,
    path: Option<String>,
    version: Option<String>,
    tools: Vec<ToolCapability>,
}

pub(crate) struct ToolDiagnostic {
    pub connected: bool,
    pub available: bool,
    pub path: Option<String>,
    pub version: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolCapability {
    id: String,
    name: String,
    #[serde(default)]
    available: bool,
    #[serde(default, alias = "embedded_ready")]
    embedded_ready: bool,
}

#[derive(Deserialize)]
struct BridgeProvider {
    id: String,
}

#[derive(Deserialize)]
struct BridgeDescription {
    protocol_version: u32,
    provider: BridgeProvider,
    tools: Vec<ToolCapability>,
}

fn registry_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|dir| dir.join("extensions.json"))
        .map_err(|_| "无法读取扩展配置位置。".to_string())
}

fn load(_app: &AppHandle) -> Result<Registry, String> {
    let root = crate::runtime_project_root().ok_or("发布组件目录不可用，请修复安装。")?;
    let sibling = root.parent().ok_or("发布组件目录无效。")?.join("RinaYaki");
    let (validated, _) = validate_source(&sibling)?;
    Ok(Registry { rinayaki_path: Some(validated) })
}

fn load_registry(path: &Path) -> Result<Registry, String> {
    let file = match fs::File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return Ok(Registry::default())
        }
        Err(_) => return Err("无法读取扩展配置，请重新定位。".into()),
    };
    let mut bytes = Vec::new();
    file.take(64 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "无法读取扩展配置。")?;
    if bytes.len() > 64 * 1024 {
        return Err("扩展配置过大，请重新定位。".into());
    }
    let registry: Registry =
        serde_json::from_slice(&bytes).map_err(|_| "扩展配置无法解析，请重新定位。")?;
    if registry
        .rinayaki_path
        .as_ref()
        .is_some_and(|path| !path.is_absolute())
    {
        return Err("扩展位置必须是完整路径，请重新定位。".into());
    }
    Ok(registry)
}

fn save(app: &AppHandle, registry: &Registry) -> Result<(), String> {
    save_registry(&registry_path(app)?, registry)
}

fn save_registry(path: &Path, registry: &Registry) -> Result<(), String> {
    let parent = path.parent().ok_or("扩展配置路径无效。")?;
    fs::create_dir_all(parent).map_err(|_| "无法创建扩展配置目录。")?;
    let body = serde_json::to_vec_pretty(registry).map_err(|_| "无法保存扩展配置。")?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "系统时间不可用。")?
        .as_nanos();
    let temporary = parent.join(format!(".extensions-{}-{stamp}.tmp", std::process::id()));
    let result = (|| {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(&body)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result.map_err(|_| "无法保存扩展配置，原记录保持不变。".into())
}

// Read only the saved registration and validate it; do not run capability discovery.
pub(crate) fn source_root(app: &AppHandle) -> Result<PathBuf, String> {
    let registry = load(app)?;
    let selected = registry
        .rinayaki_path
        .ok_or("RinaYaki is not connected in Extension tools.")?;
    validate_source(&selected).map(|(root, _)| root)
}

fn validate(root: &Path) -> Result<(PathBuf, String), String> {
    let (root, version) = validate_source(root)?;
    if !root.join(".venv/Scripts/pythonw.exe").is_file() {
        return Err("已找到 RinaYaki，但缺少本地 Python 环境；请先完成它的安装。".into());
    }
    Ok((root, version))
}

fn validate_source(root: &Path) -> Result<(PathBuf, String), String> {
    let mut entries = vec![
        "Start-RinaYaki.vbs",
        "scripts/yaki_ui.py",
        "src/rinayaki/__init__.py",
    ];
    // A legacy installation may omit the bridge, but an existing bridge must not
    // redirect execution outside the selected checkout (including broken links).
    if fs::symlink_metadata(root.join("scripts/desk_bridge.py")).is_ok() {
        entries.push("scripts/desk_bridge.py");
    }
    crate::project_locations::python_root(root, TOOL_ID, &entries)
}

// All execution paths use the same registered checkout, including native launch.
// Ignore inherited PYTHONPATH so another checkout cannot shadow this installation.
fn python_command(root: &Path, windowed: bool) -> Command {
    let mut command = Command::new(root.join(if windowed {
        ".venv/Scripts/pythonw.exe"
    } else {
        ".venv/Scripts/python.exe"
    }));
    command
        .env("PYTHONPATH", root.join("src"))
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .current_dir(root);
    if let Ok(home) = crate::billing::tool_home("RinaYaki", "RINAYAKI_CONFIG_HOME") {
        // Keep detached workers and Desk's reader on one absolute ledger root,
        // even when a packaged launcher virtualizes LOCALAPPDATA.
        command.env("RINAYAKI_CONFIG_HOME", home);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
}

/// 带墙钟超时的子进程执行：桥进程挂死时杀掉并返回可见错误，
/// 而不是让命令永远等待（2026-10-24 agent 闸 1 卡死事故的兜底）。
fn drain_limited(mut pipe: impl Read, limit: usize) -> std::io::Result<Vec<u8>> {
    let mut captured = Vec::with_capacity(limit.min(64 * 1024));
    let mut buffer = [0_u8; 8192];
    loop {
        let read = pipe.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        let remaining = limit.saturating_sub(captured.len());
        if remaining > 0 {
            captured.extend_from_slice(&buffer[..read.min(remaining)]);
        }
        // 超出保留上限后仍继续读取，避免子进程因管道写满而假死。
    }
    Ok(captured)
}

fn terminate_child_tree(child: &mut std::process::Child) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .creation_flags(0x08000000)
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn run_bridge_process(
    command: &mut Command,
    label: &str,
    seconds: u64,
) -> Result<std::process::Output, String> {
    let mut child = command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .stdin(std::process::Stdio::null())
        .spawn()
        .map_err(|_| format!("无法运行 {label}。"))?;
    let Some(stdout) = child.stdout.take() else {
        terminate_child_tree(&mut child);
        return Err(format!("无法读取 {label} 输出。"));
    };
    let Some(stderr) = child.stderr.take() else {
        terminate_child_tree(&mut child);
        return Err(format!("无法读取 {label} 错误输出。"));
    };
    // 必须在等待子进程的同时排空两个管道；否则输出超过系统管道缓存后，
    // 子进程会卡在 write，父进程则一直等退出，最后被误判成网络超时。
    let stdout_reader = std::thread::spawn(move || drain_limited(stdout, 3_000_001));
    let stderr_reader = std::thread::spawn(move || drain_limited(stderr, 256 * 1024));
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(seconds);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {
                if std::time::Instant::now() > deadline {
                    terminate_child_tree(&mut child);
                    let _ = stdout_reader.join();
                    let _ = stderr_reader.join();
                    return Err(format!("{label} 超过 {seconds} 秒未返回，已中止；请检查网络（境外视频可能需要代理）后重试。"));
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
            Err(error) => {
                terminate_child_tree(&mut child);
                let _ = stdout_reader.join();
                let _ = stderr_reader.join();
                return Err(format!("{label} 执行失败：{error}"));
            }
        }
    };
    let stdout = stdout_reader
        .join()
        .map_err(|_| format!("读取 {label} 输出的线程意外退出。"))?
        .map_err(|_| format!("无法读取 {label} 输出。"))?;
    let stderr = stderr_reader
        .join()
        .map_err(|_| format!("读取 {label} 错误输出的线程意外退出。"))?
        .map_err(|_| format!("无法读取 {label} 错误输出。"))?;
    Ok(std::process::Output {
        status,
        stdout,
        stderr,
    })
}

fn legacy_tools(root: &Path) -> Vec<ToolCapability> {
    vec![ToolCapability {
        id: "video".into(),
        name: "视频翻译".into(),
        available: true,
        embedded_ready: root.join("scripts/desk_bridge.py").is_file()
            && root.join(".venv/Scripts/python.exe").is_file(),
    }]
}

fn discover_tools(root: &Path) -> Vec<ToolCapability> {
    let script = root.join("scripts/desk_bridge.py");
    let python = root.join(".venv/Scripts/python.exe");
    if !script.is_file() || !python.is_file() {
        return legacy_tools(root);
    }
    let mut command = python_command(&root, false);
    command
        .args(["-X", "utf8"])
        .arg(script)
        .arg("describe")
        .current_dir(root);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let Ok(output) = command.output() else {
        return legacy_tools(root);
    };
    if !output.status.success() || output.stdout.len() > 64_000 {
        return legacy_tools(root);
    }
    let Ok(description) = serde_json::from_slice::<BridgeDescription>(&output.stdout) else {
        return legacy_tools(root);
    };
    if description.protocol_version != 1 || description.provider.id != TOOL_ID {
        return legacy_tools(root);
    }
    let mut ids = HashSet::new();
    let tools: Vec<_> = description
        .tools
        .into_iter()
        .filter(|tool| matches!(tool.id.as_str(), "video" | "live") && ids.insert(tool.id.clone()))
        .collect();
    if tools.iter().any(|tool| tool.id == "video") {
        tools
    } else {
        legacy_tools(root)
    }
}

fn status(registry: &Registry) -> ToolStatus {
    let result = registry
        .rinayaki_path
        .as_deref()
        .and_then(|path| validate(path).ok());
    let tools = result
        .as_ref()
        .map(|(root, _)| discover_tools(root))
        .unwrap_or_default();
    let embedded_ready = tools
        .iter()
        .find(|tool| tool.id == "video")
        .is_some_and(|tool| tool.embedded_ready);
    ToolStatus {
        id: TOOL_ID,
        connected: registry.rinayaki_path.is_some(),
        available: result.is_some(),
        embedded_ready,
        path: registry
            .rinayaki_path
            .as_ref()
            .map(|path| path.display().to_string()),
        version: result.map(|(_, version)| version),
        tools,
    }
}

#[tauri::command]
pub fn extension_status(app: AppHandle) -> Result<ToolStatus, String> {
    Ok(status(&load(&app)?))
}

pub(crate) fn diagnostic(app: &AppHandle) -> Result<ToolDiagnostic, String> {
    let value = status(&load(app)?);
    Ok(ToolDiagnostic {
        connected: value.connected,
        available: value.available,
        path: value.path,
        version: value.version,
    })
}

/// 注册表里的 RinaYaki 项目根；供需要读取 Yaki 自有凭据字段的模块使用
/// （与 billing::credentials 相同的"只读文档化凭据字段"边界）。
pub(crate) fn registered_yaki_root(app: &AppHandle) -> Option<PathBuf> {
    load(app).ok().and_then(|registry| registry.rinayaki_path)
}

#[cfg(target_os = "windows")]
fn choose_folder() -> Result<Option<PathBuf>, String> {
    use std::os::windows::process::CommandExt;
    let script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $folder=(New-Object -ComObject Shell.Application).BrowseForFolder(0,'选择 RinaYaki 项目文件夹',0,0); if ($null -eq $folder) { exit 2 }; [Console]::WriteLine($folder.Self.Path)";
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
        .map_err(|_| "无法打开文件夹选择窗口。")?;
    if output.status.code() == Some(2) {
        return Ok(None);
    }
    if !output.status.success() {
        return Err("文件夹选择失败。".into());
    }
    let path = String::from_utf8(output.stdout).map_err(|_| "无法读取所选路径。")?;
    let path = path.trim();
    if path.is_empty() {
        Ok(None)
    } else {
        Ok(Some(PathBuf::from(path)))
    }
}

#[cfg(not(target_os = "windows"))]
fn choose_folder() -> Result<Option<PathBuf>, String> {
    Err("当前仅支持 Windows 文件夹选择。".into())
}

#[tauri::command]
pub async fn extension_connect(app: AppHandle) -> Result<ToolStatus, String> {
    extension_status(app)
}

#[tauri::command]
pub fn extension_disconnect(_app: AppHandle) -> Result<ToolStatus, String> {
    Err("发布版内置组件不能在此移除。".into())
}

#[tauri::command]
pub fn extension_launch(app: AppHandle) -> Result<(), String> {
    let registry = load(&app)?;
    let path = registry
        .rinayaki_path
        .as_deref()
        .ok_or("尚未接入 RinaYaki。")?;
    let (root, _) = validate(path)?;
    let mut command = python_command(&root, true);
    command
        .arg(root.join("scripts/yaki_ui.py"))
        .current_dir(root);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
        .spawn()
        .map_err(|_| "未能打开 RinaYaki 窗口。".to_string())?;
    Ok(())
}

#[derive(Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VideoPreview {
    #[serde(alias = "protocol_version")]
    protocol_version: u32,
    kind: String,
    source: String,
    title: String,
    duration: f64,
    thumbnail: Option<String>,
}

#[tauri::command]
pub async fn extension_preview(app: AppHandle, value: String) -> Result<VideoPreview, String> {
    if value.trim().is_empty() || value.len() > 4096 {
        return Err("请输入视频链接、视频号或本地文件路径。".into());
    }
    let registry = load(&app)?;
    let path = registry
        .rinayaki_path
        .as_deref()
        .ok_or("尚未接入 RinaYaki。")?;
    let (root, _) = validate(path)?;
    let script = root.join("scripts/desk_bridge.py");
    let python = root.join(".venv/Scripts/python.exe");
    if !script.is_file() || !python.is_file() {
        return Err("RinaYaki 的桌宠预览接口不可用，请更新或重新定位。".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = python_command(&root, false);
        command
            .args(["-X", "utf8"])
            .arg(script)
            .arg("preview")
            .arg(value)
            .current_dir(root);
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let output = run_bridge_process(&mut command, "RinaYaki 预览接口", 90)?;
        if output.stdout.len() > 3_000_000 {
            return Err("视频预览结果过大。".into());
        }
        let value: serde_json::Value = serde_json::from_slice(&output.stdout)
            .map_err(|_| "RinaYaki 返回的预览结果无法解析。")?;
        if !output.status.success() {
            return Err(value
                .get("error")
                .and_then(|item| item.as_str())
                .unwrap_or("视频预览失败。")
                .to_string());
        }
        let preview: VideoPreview =
            serde_json::from_value(value).map_err(|_| "预览结果缺少必要信息。")?;
        if preview.protocol_version != 1 {
            return Err("RinaYaki 预览接口版本不匹配。".into());
        }
        Ok(preview)
    })
    .await
    .map_err(|_| "预览任务意外中断。".to_string())?
}

#[tauri::command]
pub async fn extension_yaki_action(
    app: AppHandle,
    action: String,
    request: serde_json::Value,
) -> Result<serde_json::Value, String> {
    if ![
        "jobs",
        "scan",
        "create",
        "status",
        "retry",
        "export",
        "sample",
        "open",
        "settings",
        "settings_save",
        "live_options",
        "live_start",
        "live_style_preview",
        "style_options",
        "style_preview",
        "live_guidance_open",
        "web_session_open",
        "video_preview",
    ]
    .contains(&action.as_str())
    {
        return Err("不支持的 RinaYaki 操作。".into());
    }
    let payload = serde_json::json!({"action": action, "request": request}).to_string();
    if payload.len() > 32_000 {
        return Err("请求内容过长。".into());
    }
    // 轮询类动作要快失败，避免任务卡 3 秒一轮积压；执行类给足下载/转写排队时间。
    let timeout_seconds: u64 = if action == "status" || action == "jobs" {
        20
    } else {
        90
    };
    let registry = load(&app)?;
    let path = registry
        .rinayaki_path
        .as_deref()
        .ok_or("尚未接入 RinaYaki。")?;
    let (root, _) = validate(path)?;
    let script = root.join("scripts/desk_bridge.py");
    let python = root.join(".venv/Scripts/python.exe");
    if !script.is_file() || !python.is_file() {
        return Err("RinaYaki 桌宠接口不可用。".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let mut command = python_command(&root, false);
        command
            .args(["-X", "utf8"])
            .arg(script)
            .arg("action")
            .arg(payload)
            .current_dir(root);
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let output = run_bridge_process(&mut command, "RinaYaki 接口", timeout_seconds)?;
        if output.stdout.len() > 3_000_000 {
            return Err("RinaYaki 返回的内容过大。".into());
        }
        let value: serde_json::Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "RinaYaki 返回的结果无法解析。")?;
        if !output.status.success() {
            return Err(value
                .get("error")
                .and_then(|item| item.as_str())
                .unwrap_or("RinaYaki 操作失败。")
                .to_string());
        }
        if value.get("protocol_version").and_then(|v| v.as_u64()) != Some(2) {
            return Err("RinaYaki 接口版本不匹配。".into());
        }
        Ok(value)
    })
    .await
    .map_err(|_| "RinaYaki 操作意外中断。".to_string())?
}

#[tauri::command]
pub async fn extension_select_destination() -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(choose_destination)
        .await
        .map_err(|_| "文件夹选择未完成。".to_string())?
}

#[cfg(target_os = "windows")]
fn choose_destination() -> Result<Option<String>, String> {
    use std::os::windows::process::CommandExt;
    let script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $folder=(New-Object -ComObject Shell.Application).BrowseForFolder(0,'选择翻译项目保存位置',0,0); if ($null -eq $folder) { exit 2 }; [Console]::WriteLine($folder.Self.Path)";
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
        .map_err(|_| "无法打开文件夹选择窗口。")?;
    if output.status.code() == Some(2) {
        return Ok(None);
    }
    if !output.status.success() {
        return Err("文件夹选择失败。".into());
    }
    let value = String::from_utf8(output.stdout).map_err(|_| "无法读取所选路径。")?;
    let value = value.trim();
    if value.is_empty() {
        Ok(None)
    } else {
        Ok(Some(value.to_string()))
    }
}

#[cfg(not(target_os = "windows"))]
fn choose_destination() -> Result<Option<String>, String> {
    Err("当前仅支持 Windows 文件夹选择。".into())
}

#[cfg(target_os = "windows")]
fn choose_video() -> Result<Option<String>, String> {
    use std::os::windows::process::CommandExt;
    let script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms; $dialog=New-Object System.Windows.Forms.OpenFileDialog; $dialog.Title='选择视频'; $dialog.Filter='视频文件|*.mp4;*.mkv;*.mov;*.webm;*.avi;*.flv;*.m4v|所有文件|*.*'; if ($dialog.ShowDialog() -ne 'OK') { exit 2 }; [Console]::WriteLine($dialog.FileName)";
    let output = Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ])
        .creation_flags(0x08000000)
        .output()
        .map_err(|_| "无法打开视频选择窗口。")?;
    if output.status.code() == Some(2) {
        return Ok(None);
    }
    if !output.status.success() {
        return Err("选择视频失败。".into());
    }
    let path = String::from_utf8(output.stdout).map_err(|_| "无法读取所选文件路径。")?;
    let path = path.trim();
    if path.is_empty() {
        Ok(None)
    } else {
        Ok(Some(path.to_string()))
    }
}

#[cfg(not(target_os = "windows"))]
fn choose_video() -> Result<Option<String>, String> {
    Err("当前仅支持 Windows 视频选择。".into())
}

#[tauri::command]
pub async fn extension_select_video() -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(choose_video)
        .await
        .map_err(|_| "视频选择未完成。".to_string())?
}

#[cfg(test)]
mod tests {
    use super::{validate, BridgeDescription, VideoPreview};
    use std::{fs, path::PathBuf};

    #[cfg(windows)]
    #[test]
    fn bridge_process_timeout_kills_hung_child() {
        // ping 4 次约 3 秒；1 秒超时必须杀掉并返回可见错误。
        let mut command = std::process::Command::new("cmd");
        command.args(["/c", "ping -n 4 127.0.0.1 > nul"]);
        let started = std::time::Instant::now();
        let error = super::run_bridge_process(&mut command, "测试进程", 1)
            .err()
            .unwrap_or_else(|| panic!("应当超时报错"));
        assert!(error.contains("超过 1 秒"), "{error}");
        assert!(started.elapsed() < std::time::Duration::from_secs(3));
    }

    #[cfg(windows)]
    #[test]
    fn bridge_process_collects_output_when_child_exits() {
        let mut command = std::process::Command::new("cmd");
        command.args(["/c", "echo bridge-ok"]);
        let output = super::run_bridge_process(&mut command, "测试进程", 10).unwrap();
        assert!(output.status.success());
        assert!(String::from_utf8_lossy(&output.stdout).contains("bridge-ok"));
    }

    #[test]
    fn bridge_output_capture_is_bounded_but_drains_the_reader() {
        let output = super::drain_limited(std::io::Cursor::new(vec![b'x'; 128]), 17).unwrap();
        assert_eq!(output, vec![b'x'; 17]);
    }

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let root = std::env::temp_dir()
                .join(format!("desk-registration-{}-{stamp}", std::process::id()));
            for dir in ["scripts", "src/rinayaki", ".venv/Scripts"] {
                fs::create_dir_all(root.join(dir)).unwrap();
            }
            for file in [
                "Start-RinaYaki.vbs",
                "scripts/yaki_ui.py",
                "src/rinayaki/__init__.py",
                ".venv/Scripts/pythonw.exe",
            ] {
                fs::write(root.join(file), "").unwrap();
            }
            fs::write(
                root.join("pyproject.toml"),
                "[project]\nname='rinayaki'\nversion='1.0'\n",
            )
            .unwrap();
            Self(root)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn persisted_registration_reloads_and_relocation_replaces_it() {
        let old = Fixture::new();
        let new = Fixture::new();
        let config = Fixture::new();
        let path = config.0.join("extensions.json");
        super::save_registry(
            &path,
            &super::Registry {
                rinayaki_path: Some(old.0.clone()),
            },
        )
        .unwrap();
        let loaded = super::load_registry(&path).unwrap();
        assert_eq!(
            super::validate_source(loaded.rinayaki_path.as_ref().unwrap())
                .unwrap()
                .0,
            old.0.canonicalize().unwrap()
        );
        super::save_registry(
            &path,
            &super::Registry {
                rinayaki_path: Some(new.0.clone()),
            },
        )
        .unwrap();
        let loaded = super::load_registry(&path).unwrap();
        assert_eq!(
            super::validate_source(loaded.rinayaki_path.as_ref().unwrap())
                .unwrap()
                .0,
            new.0.canonicalize().unwrap()
        );
        fs::remove_file(new.0.join("Start-RinaYaki.vbs")).unwrap();
        assert!(super::validate_source(loaded.rinayaki_path.as_ref().unwrap()).is_err());
        // A still-valid old checkout must not become an implicit fallback.
        assert!(super::validate_source(&old.0).is_ok());
        super::save_registry(&path, &super::Registry::default()).unwrap();
        assert!(super::load_registry(&path).unwrap().rinayaki_path.is_none());
    }

    #[test]
    fn rejects_bad_registration_and_failed_save_preserves_destination() {
        let fixture = Fixture::new();
        let path = fixture.0.join("extensions.json");
        for data in [
            br#"{"rinayaki_path":"relative/path"}"#.to_vec(),
            b"{".to_vec(),
            vec![b'x'; 65537],
        ] {
            fs::write(&path, data).unwrap();
            assert!(super::load_registry(&path).is_err());
        }
        fs::remove_file(&path).unwrap();
        fs::create_dir(&path).unwrap();
        fs::write(path.join("keep"), "original").unwrap();
        assert!(super::save_registry(&path, &super::Registry::default()).is_err());
        assert_eq!(fs::read_to_string(path.join("keep")).unwrap(), "original");
        assert!(!fs::read_dir(&fixture.0).unwrap().any(|entry| entry
            .unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with(".extensions-")));
    }

    #[test]
    fn native_and_bridge_commands_pin_the_selected_source() {
        let fixture = Fixture::new();
        for windowed in [true, false] {
            let command = super::python_command(&fixture.0, windowed);
            assert_eq!(command.get_current_dir(), Some(fixture.0.as_path()));
            let paths = command
                .get_envs()
                .find(|(key, _)| *key == "PYTHONPATH")
                .unwrap()
                .1
                .unwrap();
            assert_eq!(
                std::env::split_paths(paths).collect::<Vec<_>>(),
                vec![fixture.0.join("src")]
            );
            assert!(command
                .get_envs()
                .any(|(key, value)| key == "PYTHONDONTWRITEBYTECODE"
                    && value == Some(std::ffi::OsStr::new("1"))));
        }
    }

    #[test]
    fn folder_must_be_installed_rinayaki() {
        let root =
            std::env::temp_dir().join(format!("rinadesk-extension-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("scripts")).unwrap();
        fs::create_dir_all(root.join("src/rinayaki")).unwrap();
        fs::create_dir_all(root.join(".venv/Scripts")).unwrap();
        fs::write(
            root.join("pyproject.toml"),
            "[project]\nname = \"unrelated\"\nversion = \"0.1.0\"\n",
        )
        .unwrap();
        fs::write(root.join("Start-RinaYaki.vbs"), "").unwrap();
        fs::write(root.join("scripts/yaki_ui.py"), "").unwrap();
        fs::write(root.join("src/rinayaki/__init__.py"), "").unwrap();
        fs::write(root.join(".venv/Scripts/pythonw.exe"), "").unwrap();
        assert!(validate(&root).is_err());
        fs::write(
            root.join("pyproject.toml"),
            "[project]\nname = \"rinayaki\"\nversion = \"0.1.0\"\n",
        )
        .unwrap();
        let (found, version) = validate(&root).unwrap();
        assert_eq!(found, PathBuf::from(root.canonicalize().unwrap()));
        assert_eq!(version, "0.1.0");
        fs::remove_file(root.join(".venv/Scripts/pythonw.exe")).unwrap();
        assert!(validate(&root).is_err());
        assert!(super::validate_source(&root).is_ok());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn preview_contract_accepts_python_field_names() {
        let payload = serde_json::json!({
            "protocol_version": 1,
            "kind": "local",
            "source": std::env::temp_dir().join("video.mp4"),
            "title": "video.mp4",
            "duration": 1.0,
            "thumbnail": null
        });
        let preview: VideoPreview = serde_json::from_value(payload).unwrap();
        assert_eq!(preview.protocol_version, 1);
        assert_eq!(serde_json::to_value(preview).unwrap()["protocolVersion"], 1);
    }

    #[test]
    fn provider_contract_accepts_two_tools_from_one_path() {
        let payload = serde_json::json!({
            "protocol_version": 1,
            "provider": {"id": "rinayaki", "name": "RinaYaki"},
            "tools": [
                {"id": "video", "name": "视频翻译", "available": true, "embedded_ready": true},
                {"id": "live", "name": "实时翻译", "available": true, "embedded_ready": true}
            ]
        });
        let description: BridgeDescription = serde_json::from_value(payload).unwrap();
        assert_eq!(description.provider.id, "rinayaki");
        assert_eq!(description.tools.len(), 2);
        assert!(description.tools[0].embedded_ready);
        assert!(description.tools[1].embedded_ready);
    }
}
