use serde::Serialize;
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    pub(crate) enabled: bool,
    pub(crate) supported: bool,
}
#[cfg(target_os = "windows")]
fn registry(args: &[&str]) -> Result<std::process::Output, String> {
    use std::os::windows::process::CommandExt;
    std::process::Command::new("reg.exe")
        .args(args)
        .creation_flags(0x08000000)
        .output()
        .map_err(|_| "无法访问 Windows 启动设置".into())
}
const RUN: &str = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";
#[tauri::command]
pub fn startup_get() -> Result<Status, String> {
    #[cfg(target_os = "windows")]
    {
        let result = registry(&["query", RUN, "/v", "OurDeskPet"])?;
        Ok(Status {
            enabled: result.status.success(),
            supported: true,
        })
    }
    #[cfg(not(target_os = "windows"))]
    {
        Ok(Status {
            enabled: false,
            supported: false,
        })
    }
}
#[tauri::command]
pub fn startup_set(enabled: bool) -> Result<Status, String> {
    #[cfg(target_os = "windows")]
    {
        let result = if enabled {
            let exe = std::env::current_exe().map_err(|_| "无法获取程序位置")?;
            let command = format!("\"{}\" --autostart", exe.display());
            registry(&[
                "add", RUN, "/v", "OurDeskPet", "/t", "REG_SZ", "/d", &command, "/f",
            ])?
        } else {
            if !startup_get()?.enabled {
                return startup_get();
            }
            registry(&["delete", RUN, "/v", "OurDeskPet", "/f"])?
        };
        if !result.status.success() {
            return Err("未能更改开机启动，请重试。".into());
        }
        startup_get()
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = enabled;
        Err("当前仅支持 Windows 开机启动。".into())
    }
}
