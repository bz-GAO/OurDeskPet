use chrono::{DateTime, Local};
use serde::Serialize;
use serde_json::Value;
use std::{env, fs};
use tauri::AppHandle;

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolDiagnostic {
    path: Option<String>,
    state: String,
    version: Option<String>,
    protocol: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Diagnostics {
    app_version: &'static str,
    build_time: String,
    source_revision: String,
    executable_path: String,
    config_path: String,
    yaki: ToolDiagnostic,
    tomo: ToolDiagnostic,
}

fn executable() -> (String, String) {
    let Ok(path) = env::current_exe() else {
        return ("不可用".into(), "不可用".into());
    };
    let built = fs::metadata(&path)
        .ok()
        .and_then(|value| value.modified().ok())
        .map(|value| {
            DateTime::<Local>::from(value)
                .format("%Y-%m-%d %H:%M:%S")
                .to_string()
        })
        .unwrap_or_else(|| "不可用".into());
    (path.display().to_string(), built)
}

pub(crate) fn collect(app: &AppHandle) -> Diagnostics {
    let (executable_path, file_time) = executable();
    let yaki = match super::extension_tools::diagnostic(app) {
        Ok(value) => ToolDiagnostic {
            path: value.path,
            state: if value.available {
                "可用".into()
            } else if value.connected {
                "已登记，运行环境不可用".into()
            } else {
                "未登记".into()
            },
            version: value.version,
            protocol: "发现 v1 / 操作 v2".into(),
        },
        Err(_) => ToolDiagnostic {
            path: None,
            state: "登记信息不可读".into(),
            version: None,
            protocol: "发现 v1 / 操作 v2".into(),
        },
    };
    let tomo_status: Value = super::rinatomo::rinatomo_status();
    let tomo_root = super::rinatomo::project_root();
    let tomo = ToolDiagnostic {
        path: tomo_root.as_ref().map(|path| path.display().to_string()),
        state: if tomo_status.get("available").and_then(Value::as_bool) == Some(true) {
            "控制器在线".into()
        } else if tomo_root.is_some() {
            "已定位，控制器离线".into()
        } else {
            "未找到".into()
        },
        version: None,
        protocol: format!(
            "v{}",
            tomo_status
                .get("protocolVersion")
                .and_then(Value::as_u64)
                .unwrap_or(1)
        ),
    };
    Diagnostics {
        app_version: env!("CARGO_PKG_VERSION"),
        build_time: option_env!("RINADESK_BUILD_TIME")
            .map(str::to_string)
            .unwrap_or(file_time),
        source_revision: option_env!("RINADESK_SOURCE_REVISION")
            .unwrap_or("未记录")
            .to_string(),
        executable_path,
        config_path: super::api_profiles::location(Some(app))
            .map(|path| path.display().to_string())
            .unwrap_or_else(|_| "不可用".into()),
        yaki,
        tomo,
    }
}

#[tauri::command]
pub async fn diagnostics_get(app: AppHandle) -> Result<Diagnostics, String> {
    tauri::async_runtime::spawn_blocking(move || collect(&app))
        .await
        .map_err(|_| "诊断信息读取中断。".to_string())
}

#[cfg(test)]
mod tests {
    #[test]
    fn build_metadata_is_bounded() {
        assert!(!env!("CARGO_PKG_VERSION").is_empty());
        assert!(
            option_env!("RINADESK_SOURCE_REVISION")
                .unwrap_or("未记录")
                .len()
                < 128
        );
    }
}
