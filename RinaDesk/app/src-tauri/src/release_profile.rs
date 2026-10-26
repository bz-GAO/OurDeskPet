//! Public distribution configuration. Never migrate private developer state.
use std::path::PathBuf;

fn distribution_root() -> Result<PathBuf, String> {
    let executable = std::env::current_exe().map_err(|_| "安装路径不可用")?;
    let directory = executable.parent().ok_or("安装路径无效")?;
    let is_release_root = |path: &std::path::Path| {
        path.join("release-manifest.json").is_file()
            && path.join("RinaDesk/release-profile.json").is_file()
    };
    if is_release_root(directory) {
        return directory
            .canonicalize()
            .map_err(|_| "安装路径不可读".to_string())
    }
    #[cfg(debug_assertions)]
    if let Some(root) = directory.ancestors().find(|path| is_release_root(path)) {
        return root
            .canonicalize()
            .map_err(|_| "发布工作区不可读".to_string())
    }
    Err("无法确认 OurDeskPet 安装根目录，请重新安装".into())
}

pub(crate) fn data_dir(component: &str) -> Result<PathBuf, String> {
    if !matches!(component, "RinaDesk" | "RinaYaki" | "RinaTomo") {
        return Err("未知发布组件".into());
    }
    Ok(distribution_root()?.join("data").join(component))
}

pub(crate) fn initialize() {
    // Only the new process is modified. Existing developer processes are untouched.
    let inherited: Vec<_> = std::env::vars_os().map(|(key, _)| key).collect();
    for key in inherited {
        let name = key.to_string_lossy();
        if name.starts_with("OURDESKPET_") || name.starts_with("DASHSCOPE_")
            || name.starts_with("OPENAI_") || name.starts_with("DEEPSEEK_")
            || name.starts_with("RINATOMO_") || name.starts_with("RINAYAKI_")
            || matches!(name.as_ref(), "PYTHONPATH" | "PYTHONHOME" | "TAVILY_API_KEY") {
            std::env::remove_var(key);
        }
    }
    if let Ok(home) = data_dir("RinaDesk") {
        if let Some(base) = home.parent() {
            std::env::set_var("OURDESKPET_DATA_ROOT", base);
        }
        std::env::set_var("OURDESKPET_ENV_FILE", home.join(".env"));
    }
    if let Ok(home) = data_dir("RinaYaki") { std::env::set_var("RINAYAKI_CONFIG_HOME", home); }
    if let Ok(home) = data_dir("RinaTomo") { std::env::set_var("RINATOMO_CONFIG_HOME", home); }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn data_is_namespaced_and_components_cannot_escape() {
        let desk = data_dir("RinaDesk").unwrap();
        assert_eq!(desk.parent().unwrap().file_name().unwrap(), "data");
        assert!(desk.parent().unwrap().parent().unwrap().join("release-manifest.json").is_file());
        assert_eq!(data_dir("RinaTomo").unwrap().parent(), desk.parent());
        assert!(data_dir("../RinaDesk").is_err());
    }
}
