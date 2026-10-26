//! Validate project identity without importing code or depending on the working directory.
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
};

pub(crate) fn python_root(
    root: &Path,
    name: &str,
    markers: &[&str],
) -> Result<(PathBuf, String), String> {
    if !root.is_absolute() {
        return Err("项目位置无效，请重新定位。".into());
    }
    let root = root
        .canonicalize()
        .map_err(|_| "项目位置已失效，请重新定位。")?;
    for marker in std::iter::once("pyproject.toml").chain(markers.iter().copied()) {
        let mut path = root.clone();
        for component in Path::new(marker).components() {
            path.push(component);
            let meta = fs::symlink_metadata(&path).map_err(|_| "项目文件不完整，请重新定位。")?;
            if meta.file_type().is_symlink() {
                return Err("项目入口不能是链接。".into());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if meta.file_attributes() & 0x400 != 0 {
                    return Err("项目入口不能是目录链接。".into());
                }
            }
        }
        if !path.is_file()
            || !path
                .canonicalize()
                .map_err(|_| "项目入口不可用。")?
                .starts_with(&root)
        {
            return Err("项目入口不在所选项目中。".into());
        }
    }
    let mut text = String::new();
    fs::File::open(root.join("pyproject.toml"))
        .map_err(|_| "项目声明不可用。")?
        .take(64 * 1024 + 1)
        .read_to_string(&mut text)
        .map_err(|_| "项目声明无法读取。")?;
    if text.len() > 64 * 1024 {
        return Err("项目声明过大。".into());
    }
    let manifest: toml::Value = toml::from_str(&text).map_err(|_| "项目声明格式无效。")?;
    let project = manifest.get("project").ok_or("缺少项目声明。")?;
    if project.get("name").and_then(toml::Value::as_str) != Some(name) {
        return Err("所选目录不是对应工具项目。".into());
    }
    let version = project
        .get("version")
        .and_then(toml::Value::as_str)
        .unwrap_or("未知")
        .to_string();
    Ok((root, version))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_project_section_not_arbitrary_matching_text() {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root =
            std::env::temp_dir().join(format!("desk-identity-{}-{stamp}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("entry.py"), "").unwrap();
        for invalid in [
            "[tool.fake]\nname = 'rinayaki'",
            "[project]\nname='other'",
            "not toml",
        ] {
            fs::write(root.join("pyproject.toml"), invalid).unwrap();
            assert!(python_root(&root, "rinayaki", &["entry.py"]).is_err());
        }
        fs::write(
            root.join("pyproject.toml"),
            "[project]\nname='rinayaki' # comment\nversion='2.0'\n",
        )
        .unwrap();
        assert_eq!(
            python_root(&root, "rinayaki", &["entry.py"]).unwrap().1,
            "2.0"
        );
        assert!(python_root(Path::new("relative/project"), "rinayaki", &[]).is_err());
        assert!(python_root(&root, "rinayaki", &["missing.py"]).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
