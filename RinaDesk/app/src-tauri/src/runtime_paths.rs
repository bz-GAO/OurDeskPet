//! Resolve one installation and one configuration file, independent of the shell's cwd.
use std::{
    fs,
    path::{Component, Path, PathBuf},
};

fn validated_root(path: &Path) -> Option<PathBuf> {
    if !path.join("app/src-tauri/tauri.conf.json").is_file() {
        return None;
    }
    path.canonicalize().ok()
}

// Installed binaries live in <private data>/bin. Resolve their data next to
// the verified launcher anchor, not from the parent shell's LOCALAPPDATA.
pub(crate) fn installed_data_root(executable_dir: &Path) -> Option<PathBuf> {
    if executable_dir.file_name()? != "bin" || !executable_dir.join("rinadesk-root.txt").is_file() {
        return None;
    }
    project_root(Some(executable_dir), None)?;
    Some(executable_dir.parent()?.to_path_buf())
}

pub(crate) fn project_root(
    executable_dir: Option<&Path>,
    development_root: Option<&Path>,
) -> Option<PathBuf> {
    if let Some(directory) = executable_dir {
        match fs::read_to_string(directory.join("rinadesk-root.txt")) {
            Ok(value) => {
                let value = value.trim();
                let anchor = Path::new(value);
                // An existing but broken anchor must not redirect this copy to another checkout.
                if value.is_empty() || value.chars().any(char::is_control) {
                    return None;
                }
                // Repair-Launcher uses an absolute anchor when install and source are on different drives.
                if anchor.is_absolute() {
                    return validated_root(anchor);
                }
                if value.contains(':')
                    || anchor
                        .components()
                        .any(|part| matches!(part, Component::Prefix(_) | Component::RootDir))
                {
                    return None;
                }
                return validated_root(&directory.join(anchor));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return None,
        }
        // Direct `tauri build` keeps the executable under this checkout's target directory.
        // This also follows a moved checkout without using its old compilation path.
        if let Some(root) = directory.ancestors().find_map(validated_root) {
            return Some(root);
        }
    }
    development_root.and_then(validated_root)
}

pub(crate) fn env_file(
    explicit: Option<&str>,
    root: Option<&Path>,
    config_dir: Option<&Path>,
) -> Result<PathBuf, String> {
    if let Some(value) = explicit.map(str::trim).filter(|value| !value.is_empty()) {
        let path = PathBuf::from(value);
        if path.is_absolute() {
            return Ok(path);
        }
        if path
            .components()
            .any(|part| matches!(part, Component::Prefix(_) | Component::RootDir))
        {
            return Err("配置路径应为完整路径或相对路径".into());
        }
        // Resolve explicit relative overrides alongside the current installation/configuration.
        let base = root.or(config_dir).ok_or("配置目录不可用")?;
        return Ok(base.join(path));
    }
    // Keep this destination even when .env has not been created yet.
    if let Some(root) = root {
        return Ok(root.join(".env"));
    }
    let directory = config_dir.ok_or("配置目录不可用")?;
    let primary = directory.join(".env");
    let legacy = directory.join("config.env");
    Ok(if !primary.exists() && legacy.is_file() {
        legacy
    } else {
        primary
    })
}

// A broken installed anchor is not a standalone installation. Do not silently
// switch it to app_config_dir and create a second set of settings on restart.
pub(crate) fn check_config_anchor(
    executable_dir: Option<&Path>,
    root: Option<&Path>,
) -> Result<(), String> {
    if root.is_some() {
        return Ok(());
    }
    if let Some(directory) = executable_dir {
        match fs::symlink_metadata(directory.join("rinadesk-root.txt")) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            _ => {
                return Err("启动定位文件无效或项目目录不可用，请修复启动项；未切换配置目录".into())
            }
        }
    }
    Ok(())
}

pub(crate) fn prompt_files(
    configured: Option<&str>,
    root: Option<&Path>,
    env_file: Option<&Path>,
    config_dir: Option<&Path>,
) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Some(value) = configured.map(str::trim).filter(|value| !value.is_empty()) {
        let path = PathBuf::from(value);
        if path.is_absolute() {
            paths.push(path);
        } else if let Some(directory) = env_file.and_then(Path::parent).or(root).or(config_dir) {
            paths.push(directory.join(path));
        }
    }
    if let Some(root) = root {
        paths.push(root.join("prompts/rina_system_prompt.md"));
    } else if let Some(directory) = config_dir {
        paths.push(directory.join("rina_system_prompt.md"));
    }
    paths
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn installed_storage_is_anchored_not_shell_dependent() {
        let fixture = Fixture::new();
        let bin = fixture.0.join("private/bin");
        fs::create_dir_all(&bin).unwrap();
        assert_eq!(installed_data_root(&bin), None);
        fs::write(
            bin.join("rinadesk-root.txt"),
            fixture.0.to_string_lossy().as_bytes(),
        )
        .unwrap();
        assert_eq!(installed_data_root(&bin), Some(fixture.0.join("private")));
        fs::write(bin.join("rinadesk-root.txt"), "missing").unwrap();
        assert_eq!(installed_data_root(&bin), None);
    }
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let stamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let root =
                std::env::temp_dir().join(format!("rinadesk-paths-{}-{stamp}", std::process::id()));
            fs::create_dir_all(root.join("app/src-tauri")).unwrap();
            fs::write(root.join("app/src-tauri/tauri.conf.json"), "{}").unwrap();
            Self(root)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn broken_anchor_cannot_redirect_configuration_to_standalone_storage() {
        let fixture = Fixture::new();
        let bin = fixture.0.join("bin");
        fs::create_dir(&bin).unwrap();
        assert!(check_config_anchor(Some(&bin), None).is_ok());
        for value in ["", "missing", "broken\0path"] {
            fs::write(bin.join("rinadesk-root.txt"), value).unwrap();
            let root = project_root(Some(&bin), None);
            assert!(root.is_none());
            assert!(check_config_anchor(Some(&bin), root.as_deref()).is_err());
        }
        fs::write(bin.join("rinadesk-root.txt"), "../").unwrap();
        let root = project_root(Some(&bin), None);
        assert!(check_config_anchor(Some(&bin), root.as_deref()).is_ok());
    }
    #[test]
    fn release_anchor_moves_with_the_installation() {
        let active = Fixture::new();
        let old = Fixture::new();
        let executable_dir = active.0.join("bin");
        fs::create_dir_all(&executable_dir).unwrap();
        fs::write(executable_dir.join("rinadesk-root.txt"), "../").unwrap();
        assert_eq!(
            project_root(Some(&executable_dir), Some(&old.0)),
            active.0.canonicalize().ok()
        );
        fs::write(executable_dir.join("rinadesk-root.txt"), "missing").unwrap();
        assert!(project_root(Some(&executable_dir), Some(&old.0)).is_none());
    }

    #[test]
    fn only_development_uses_the_compile_time_root() {
        let source = Fixture::new();
        assert_eq!(
            project_root(None, Some(&source.0)),
            source.0.canonicalize().ok()
        );
        assert!(project_root(None, None).is_none());
    }

    #[test]
    fn release_without_an_anchor_uses_its_current_checkout_ancestor() {
        let active = Fixture::new();
        let old = Fixture::new();
        let executable_dir = active.0.join("app/src-tauri/target/release");
        fs::create_dir_all(&executable_dir).unwrap();
        assert_eq!(
            project_root(Some(&executable_dir), None),
            active.0.canonicalize().ok()
        );
        assert_eq!(
            project_root(Some(&executable_dir), Some(&old.0)),
            active.0.canonicalize().ok()
        );
    }

    #[test]
    fn launcher_supports_an_absolute_anchor_for_a_separate_install_drive() {
        let active = Fixture::new();
        let cache = Fixture::new();
        fs::write(
            cache.0.join("rinadesk-root.txt"),
            active.0.to_string_lossy().as_bytes(),
        )
        .unwrap();
        assert_eq!(
            project_root(Some(&cache.0), None),
            active.0.canonicalize().ok()
        );
    }

    #[test]
    fn missing_local_env_does_not_select_another_configuration() {
        let active = Fixture::new();
        let config = Fixture::new();
        fs::write(config.0.join(".env"), "FOREIGN=true").unwrap();
        assert_eq!(
            env_file(None, Some(&active.0), Some(&config.0)).unwrap(),
            active.0.join(".env")
        );
        assert_eq!(
            env_file(Some("  "), Some(&active.0), Some(&config.0)).unwrap(),
            active.0.join(".env")
        );
    }

    #[test]
    fn explicit_env_wins_and_relative_paths_use_the_installation() {
        let active = Fixture::new();
        let other = Fixture::new();
        let absolute = other.0.join("chosen.env");
        assert_eq!(
            env_file(absolute.to_str(), Some(&active.0), None).unwrap(),
            absolute
        );
        assert_eq!(
            env_file(Some("config/custom.env"), Some(&active.0), None).unwrap(),
            active.0.join("config/custom.env")
        );
    }

    #[test]
    fn standalone_legacy_config_is_not_merged_with_primary() {
        let config = Fixture::new();
        fs::write(config.0.join("config.env"), "LEGACY=true").unwrap();
        assert_eq!(
            env_file(None, None, Some(&config.0)).unwrap(),
            config.0.join("config.env")
        );
        fs::write(config.0.join(".env"), "PRIMARY=true").unwrap();
        assert_eq!(
            env_file(None, None, Some(&config.0)).unwrap(),
            config.0.join(".env")
        );
    }

    #[test]
    fn prompt_override_is_relative_to_the_selected_config_file() {
        let active = Fixture::new();
        let other = Fixture::new();
        let configured = other.0.join("chosen.env");
        let paths = prompt_files(
            Some("prompts/custom.md"),
            Some(&active.0),
            Some(&configured),
            Some(&other.0),
        );
        assert_eq!(
            paths,
            vec![
                other.0.join("prompts/custom.md"),
                active.0.join("prompts/rina_system_prompt.md")
            ]
        );
    }
}
