use serde_json::{json, Value};
use std::env;
use std::io::{Read, Write};
use std::net::{Shutdown, TcpStream};
use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

const ADDRESS: &str = "127.0.0.1:37642";

fn offline_snapshot() -> Value {
    json!({
        "protocolVersion": 1,
        "provider": "rinatomo",
        "available": false,
        "owner": null,
        "napcat": "未连接",
        "qq": "等待启动",
        "state": "offline",
        "running": false,
        "paused": false,
        "login": {"required": false, "message": "", "qrcodeDataUrl": ""},
        "features": {"ping": true, "echo": false},
        "llm": {"enabled": false, "effectiveModel": "未配置", "minReplyInterval": 0,
            "timeoutSeconds": 30, "maxTokens": 512, "dailyTokenBudget": 200000,
            "maxInputChars": 2000, "maxConcurrentRequests": 2,
            "usage": {"used": 0, "dailyLimit": 200000, "remaining": 200000}},
        "permissions": {"adminUsers": [], "privateWhitelist": [], "enabledGroups": []},
        "autoStart": false
    })
}

/// 通知推送：agent 任务终态等"错过的事项"，由 Tomo 转发给 admin 白名单。
/// 失败只记录不阻塞调用方（通知尽力而为）。
pub(crate) fn notify(event: &str, title: &str, lines: &[&str]) {
    let payload = json!({
        "event": event,
        "title": title,
        "lines": lines,
    });
    if let Err(error) = request("notify", payload) {
        eprintln!("rinatomo notify failed: {error}");
    }
}

fn request(command: &str, payload: Value) -> Result<Value, String> {
    let mut stream = TcpStream::connect_timeout(
        &ADDRESS.parse().map_err(|_| "Tomo 控制地址无效。")?,
        Duration::from_millis(800),
    )
    .map_err(|_| "RinaTomo 控制器未运行。".to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(6)))
        .map_err(|error| error.to_string())?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .map_err(|error| error.to_string())?;
    let body = json!({"protocolVersion": 1, "command": command, "payload": payload}).to_string();
    if body.len() > 60_000 {
        return Err("Tomo 控制请求过长。".into());
    }
    stream
        .write_all(body.as_bytes())
        .map_err(|_| "无法发送 Tomo 控制请求。")?;
    stream
        .shutdown(Shutdown::Write)
        .map_err(|_| "无法完成 Tomo 控制请求。")?;
    let mut response = String::new();
    stream
        .take(524_288)
        .read_to_string(&mut response)
        .map_err(|_| "无法读取 Tomo 响应。")?;
    let envelope: Value =
        serde_json::from_str(response.trim()).map_err(|_| "Tomo 响应格式无效。")?;
    if envelope.get("ok").and_then(Value::as_bool) != Some(true) {
        return Err(envelope
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("Tomo 操作失败。")
            .to_string());
    }
    Ok(envelope.get("data").cloned().unwrap_or(Value::Null))
}

#[tauri::command]
pub fn rinatomo_status() -> Value {
    request("status", json!({})).unwrap_or_else(|_| offline_snapshot())
}

#[tauri::command]
pub fn rinatomo_action(action: String) -> Result<Value, String> {
    if !["show", "start", "pause", "refreshLogin", "shutdown"].contains(&action.as_str()) {
        return Err("不支持的 Tomo 操作。".into());
    }
    request(&action, json!({}))
}

#[tauri::command]
pub fn rinatomo_update(request_body: Value) -> Result<Value, String> {
    request("update", request_body)
}

fn is_desk_owned(snapshot: &Value) -> bool {
    snapshot.get("owner").and_then(Value::as_str) == Some("desk")
}

pub(crate) fn shutdown_if_desk_owned() {
    if request("status", json!({})).is_ok_and(|snapshot| is_desk_owned(&snapshot)) {
        let _ = request("shutdown", json!({}));
    }
}

pub(crate) fn project_root() -> Option<PathBuf> {
    let root = crate::runtime_project_root()?;
    let workspace = root.parent()?;
    let candidate = workspace.join("RinaTomo");
    crate::project_locations::python_root(
        &candidate,
        "rinatomo",
        &["Start-RinaTomo.vbs", "src/rinatomo/__init__.py"],
    )
    .ok()
    .map(|(root, _)| root)
}

#[tauri::command]
pub fn rinatomo_launch() -> Result<(), String> {
    let root = project_root().ok_or("未找到同一工作区内的 RinaTomo。")?;
    let python = root.join(".venv").join("Scripts").join("pythonw.exe");
    if !python.is_file() {
        return Err("RinaTomo 尚未安装本机运行环境。".into());
    }
    let mut import_paths = vec![root.join("src")];
    if let Some(existing) = env::var_os("PYTHONPATH") {
        import_paths.extend(env::split_paths(&existing));
    }
    let python_path =
        env::join_paths(import_paths).map_err(|_| "无法生成 RinaTomo 的本机模块路径。")?;
    let mut command = Command::new(python);
    command
        .args(["-m", "rinatomo", "ui", "--owner", "desk"])
        .env("PYTHONPATH", python_path)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .current_dir(&root);
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
        .spawn()
        .map(|_| ())
        .map_err(|_| "无法打开 RinaTomo。".to_string())
}

#[cfg(test)]
mod tests {
    use super::{is_desk_owned, offline_snapshot};
    use serde_json::{json, Value};

    #[test]
    fn offline_contract_matches_frontend() {
        let value = offline_snapshot();
        assert_eq!(value["provider"], "rinatomo");
        assert_eq!(value["owner"], Value::Null);
        assert_eq!(value["state"], "offline");
        assert_eq!(value["features"]["ping"], true);
        assert_eq!(value["llm"]["minReplyInterval"], 0);
        assert_eq!(value["llm"]["usage"]["used"], 0);
        assert_eq!(value["llm"]["usage"]["dailyLimit"], 200000);
        assert_eq!(value["llm"]["usage"]["remaining"], 200000);
        assert_eq!(value["login"]["required"], false);
    }

    #[test]
    fn only_desk_owned_controller_is_stopped_on_app_exit() {
        assert!(is_desk_owned(&json!({"owner": "desk"})));
        assert!(!is_desk_owned(&json!({"owner": "standalone"})));
        assert!(!is_desk_owned(&json!({})));
    }
}
