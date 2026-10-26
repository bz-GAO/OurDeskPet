//! Public distribution configuration. Never migrate private developer state.
use std::path::PathBuf;

pub(crate) fn data_dir(component: &str) -> Result<PathBuf, String> {
    if !matches!(component, "RinaDesk" | "RinaYaki" | "RinaTomo") {
        return Err("未知发布组件".into());
    }
    let base = std::env::var_os("LOCALAPPDATA")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or("本机资料目录不可用")?;
    if !base.is_absolute() { return Err("本机资料目录无效".into()); }
    Ok(base.join("OurDeskPet").join(component))
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
        assert_eq!(desk.parent().unwrap().file_name().unwrap(), "OurDeskPet");
        assert_eq!(data_dir("RinaTomo").unwrap().parent(), desk.parent());
        assert!(data_dir("../RinaDesk").is_err());
    }
}
