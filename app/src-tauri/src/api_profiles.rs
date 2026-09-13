use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet, HashMap},
    fs,
    hash::{Hash, Hasher},
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{Emitter, Manager};
static WRITE_LOCK: Mutex<()> = Mutex::new(());
const ACTIVE: &str = "OURDESKPET_ACTIVE_PROFILE";
const PREFIX: &str = "OURDESKPET_PROFILE_";

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Profile {
    id: String,
    name: String,
    base_url: String,
    model: String,
    has_key: bool,
    ready: bool,
    read_only: bool,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    revision: String,
    path: String,
    active: String,
    profiles: Vec<Profile>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveRequest {
    create: bool,
    revision: String,
    id: String,
    name: String,
    base_url: String,
    model: String,
    key: Option<String>,
}
pub struct Resolved {
    pub key: Option<String>,
    pub url: String,
    pub model: Option<String>,
}

fn profile_key(id: &str, field: &str) -> String {
    format!("{PREFIX}{}_{field}", id.to_ascii_uppercase())
}
fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 40
        && id != "legacy"
        && id
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
}
fn comment_at(s: &str) -> Option<usize> {
    let mut quote = None;
    let mut escaped = false;
    let mut previous = ' ';
    for (i, c) in s.char_indices() {
        if escaped {
            escaped = false;
            previous = c;
            continue;
        }
        if quote == Some('"') && c == '\\' {
            escaped = true;
            previous = c;
            continue;
        }
        if let Some(q) = quote {
            if c == q {
                quote = None;
            }
        } else if c == '\'' || c == '"' {
            quote = Some(c);
        } else if c == '#' && previous.is_whitespace() {
            return Some(i);
        }
        previous = c;
    }
    None
}
fn assignment(line: &str) -> Option<(&str, &str)> {
    let line = line.trim().trim_start_matches('\u{feff}');
    if line.starts_with('#') {
        return None;
    }
    let line = line.strip_prefix("export ").unwrap_or(line);
    let (key, value) = line.split_once('=')?;
    let key = key.trim();
    if key.is_empty() || !key.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_') {
        return None;
    }
    Some((key, value))
}
fn parse(text: &str) -> Result<HashMap<String, String>, String> {
    let mut values = HashMap::new();
    for (n, line) in text.lines().enumerate() {
        if let Some((key, raw)) = assignment(line) {
            let raw = raw[..comment_at(raw).unwrap_or(raw.len())].trim();
            let value = if raw.starts_with('"') {
                serde_json::from_str::<String>(raw)
                    .map_err(|_| format!("配置第 {} 行的引号或转义不完整", n + 1))?
            } else if raw.starts_with('\'') {
                if raw.len() < 2 || !raw.ends_with('\'') {
                    return Err(format!("配置第 {} 行的引号不完整", n + 1));
                }
                raw[1..raw.len() - 1].into()
            } else {
                raw.into()
            };
            values.insert(key.into(), value);
        }
    }
    Ok(values)
}
fn revision(text: &str) -> String {
    let mut h = std::collections::hash_map::DefaultHasher::new();
    text.hash(&mut h);
    format!("{:x}", h.finish())
}
fn read(path: &Path) -> Result<String, String> {
    match fs::read_to_string(path) {
        Ok(s) => Ok(s),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
        Err(_) => Err("无法读取 API 配置文件".into()),
    }
}
fn location(app: Option<&tauri::AppHandle>) -> Result<PathBuf, String> {
    if let Ok(path) = std::env::var("OURDESKPET_ENV_FILE") {
        return Ok(PathBuf::from(path));
    }
    if let Some(path) = super::candidate_env_paths(app)
        .into_iter()
        .find(|p| p.is_file())
    {
        return Ok(path);
    }
    app.ok_or("配置目录不可用")?
        .path()
        .app_config_dir()
        .map(|p| p.join(".env"))
        .map_err(|_| "配置目录不可用".into())
}
fn field(values: &HashMap<String, String>, id: &str, key: &str) -> String {
    values
        .get(&profile_key(id, key))
        .cloned()
        .unwrap_or_default()
}
fn legacy(values: &HashMap<String, String>, key: &str) -> String {
    std::env::var(key)
        .ok()
        .filter(|s| !s.trim().is_empty())
        .or_else(|| values.get(key).cloned())
        .unwrap_or_default()
}
fn active(values: &HashMap<String, String>) -> String {
    values
        .get(ACTIVE)
        .map(|s| s.trim().to_ascii_lowercase())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "legacy".into())
}
fn ids(values: &HashMap<String, String>) -> BTreeSet<String> {
    values
        .keys()
        .filter_map(|key| {
            let rest = key.strip_prefix(PREFIX)?;
            ["BASE_URL", "API_KEY", "MODEL", "NAME"]
                .iter()
                .find_map(|suffix| {
                    rest.strip_suffix(&format!("_{suffix}"))
                        .map(str::to_ascii_lowercase)
                })
        })
        .filter(|id| valid_id(id))
        .collect()
}
fn valid_url(url: &str) -> bool {
    reqwest::Url::parse(url).is_ok_and(|u| {
        matches!(u.scheme(), "http" | "https")
            && u.host_str().is_some()
            && u.username().is_empty()
            && u.password().is_none()
            && u.query().is_none()
            && u.fragment().is_none()
    })
}
fn snapshot(path: &Path, text: &str) -> Result<Snapshot, String> {
    let values = parse(text)?;
    let mut profiles = Vec::new();
    let key = legacy(&values, "OURDESKPET_API_KEY");
    let model = legacy(&values, "OURDESKPET_MODEL");
    let mut url = legacy(&values, "OURDESKPET_BASE_URL");
    if url.is_empty() {
        url = super::DEFAULT_BASE_URL.into();
    }
    if !key.is_empty() || !model.is_empty() {
        profiles.push(Profile {
            id: "legacy".into(),
            name: "现有配置".into(),
            base_url: url.clone(),
            model: model.clone(),
            has_key: !key.is_empty(),
            ready: !key.is_empty() && !model.is_empty() && valid_url(&url),
            read_only: true,
        });
    }
    for id in ids(&values) {
        let url = field(&values, &id, "BASE_URL");
        let model = field(&values, &id, "MODEL");
        let has_key = !field(&values, &id, "API_KEY").trim().is_empty();
        let name = field(&values, &id, "NAME");
        profiles.push(Profile {
            name: if name.is_empty() { id.clone() } else { name },
            ready: has_key && !model.is_empty() && valid_url(&url),
            id,
            base_url: url,
            model,
            has_key,
            read_only: false,
        });
    }
    Ok(Snapshot {
        revision: revision(text),
        path: path.display().to_string(),
        active: active(&values),
        profiles,
    })
}
pub fn resolve(app: Option<&tauri::AppHandle>) -> Result<Resolved, String> {
    let path = location(app)?;
    let values = parse(&read(&path)?)?;
    resolve_values(&values)
}
fn resolve_values(values: &HashMap<String, String>) -> Result<Resolved, String> {
    let id = active(values);
    if id == "legacy" {
        let key = legacy(&values, "OURDESKPET_API_KEY");
        let model = legacy(&values, "OURDESKPET_MODEL");
        let url = legacy(&values, "OURDESKPET_BASE_URL");
        return Ok(Resolved {
            key: (!key.is_empty()).then_some(key),
            model: (!model.is_empty()).then_some(model),
            url: if url.is_empty() {
                super::DEFAULT_BASE_URL.into()
            } else {
                url
            },
        });
    }
    if !valid_id(&id) {
        return Err("当前 API 配置代号无效，请到设置重新选择".into());
    }
    let url = field(&values, &id, "BASE_URL");
    let model = field(&values, &id, "MODEL");
    let key = field(&values, &id, "API_KEY");
    if !valid_url(&url) || model.trim().is_empty() || key.trim().is_empty() {
        return Err("当前 API 配置不完整，请到设置补齐地址、密钥和模型".into());
    }
    Ok(Resolved {
        key: Some(key),
        url,
        model: Some(model),
    })
}
fn patch(text: &str, updates: &BTreeMap<String, String>) -> String {
    let newline = if text.contains("\r\n") { "\r\n" } else { "\n" };
    let mut seen = BTreeSet::new();
    let mut lines = Vec::new();
    for line in text.lines() {
        if let Some((key, raw)) = assignment(line) {
            if let Some(value) = updates.get(key) {
                if seen.insert(key.to_string()) {
                    let comment = comment_at(raw)
                        .map(|i| format!(" {}", &raw[i..]))
                        .unwrap_or_default();
                    lines.push(format!(
                        "{key}={}{}",
                        serde_json::to_string(value).unwrap(),
                        comment
                    ));
                }
                continue;
            }
        }
        lines.push(line.to_string());
    }
    for (key, value) in updates {
        if !seen.contains(key) {
            lines.push(format!("{key}={}", serde_json::to_string(value).unwrap()));
        }
    }
    format!("{}{}", lines.join(newline), newline)
}
fn commit(path: &Path, expected: &str, updates: &BTreeMap<String, String>) -> Result<(), String> {
    let text = read(path)?;
    if revision(&text) != expected {
        return Err("配置文件已在外部修改；请重新载入后保存，当前草稿已保留".into());
    }
    let next = patch(&text, updates);
    parse(&next)?;
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent).map_err(|_| "无法创建配置目录")?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| "系统时间不可用")?
        .as_nanos();
    let temp = parent.join(format!(".rinadesk-{}-{stamp}.tmp", std::process::id()));
    let result = (|| {
        let mut f = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|_| "无法创建临时配置文件")?;
        f.write_all(next.as_bytes())
            .and_then(|_| f.sync_all())
            .map_err(|_| "无法写入配置文件")?;
        drop(f);
        if revision(&read(path)?) != expected {
            return Err("保存前配置发生变化，请重新载入后重试".into());
        }
        fs::rename(&temp, path).map_err(|_| "无法替换配置文件，原文件保持不变".into())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}
fn settings_only(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() == "settings" {
        Ok(())
    } else {
        Err("仅设置窗口可管理 API 配置".into())
    }
}
#[tauri::command]
pub fn api_profiles_list(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
) -> Result<Snapshot, String> {
    settings_only(&window)?;
    let path = location(Some(&app))?;
    snapshot(&path, &read(&path)?)
}
#[tauri::command]
pub fn api_profiles_save(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    request: SaveRequest,
) -> Result<Snapshot, String> {
    settings_only(&window)?;
    let _lock = WRITE_LOCK.lock().map_err(|_| "配置写入锁不可用")?;
    let id = request.id.trim().to_ascii_lowercase();
    if !valid_id(&id) {
        return Err("代号请用 1–40 位英文字母、数字或下划线，legacy 为保留名称".into());
    }
    let url = request.base_url.trim().trim_end_matches('/');
    if !valid_url(url) {
        return Err("请填写不含密钥、查询参数的 http/https 基础地址".into());
    }
    let model = request.model.trim();
    if model.is_empty() || model.contains(['\r', '\n']) {
        return Err("请填写有效的模型名".into());
    }
    let path = location(Some(&app))?;
    let old = read(&path)?;
    let values = parse(&old)?;
    if request.create && ids(&values).contains(&id) {
        return Err("这个代号已存在，请从左侧选择编辑，或使用新代号".into());
    }
    let key = request
        .key
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| field(&values, &id, "API_KEY"));
    if key.trim().is_empty() || key.contains(['\r', '\n']) {
        return Err("新配置需要填写有效密钥；编辑时留空可保留原密钥".into());
    }
    let mut updates = BTreeMap::new();
    for (field, value) in [
        ("BASE_URL", url.to_string()),
        ("MODEL", model.into()),
        ("API_KEY", key),
        ("NAME", request.name.trim().to_string()),
    ] {
        updates.insert(profile_key(&id, field), value);
    }
    commit(&path, &request.revision, &updates)?;
    let result = snapshot(&path, &read(&path)?)?;
    let _ = app.emit("deskpet-api-config-changed", ());
    Ok(result)
}
#[tauri::command]
pub fn api_profiles_activate(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    id: String,
    revision: String,
) -> Result<Snapshot, String> {
    settings_only(&window)?;
    let _lock = WRITE_LOCK.lock().map_err(|_| "配置写入锁不可用")?;
    let path = location(Some(&app))?;
    let text = read(&path)?;
    let current = snapshot(&path, &text)?;
    if !current.profiles.iter().any(|p| p.id == id && p.ready) {
        return Err("该配置不完整，不能启用".into());
    }
    commit(
        &path,
        &revision,
        &BTreeMap::from([(ACTIVE.to_string(), id)]),
    )?;
    let result = snapshot(&path, &read(&path)?)?;
    let _ = app.emit("deskpet-api-config-changed", ());
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn named_profile_is_selected_and_missing_profile_never_falls_back() {
        let mut values = HashMap::from([
            (ACTIVE.into(), "ds".into()),
            ("OURDESKPET_API_KEY".into(), "legacy-secret".into()),
            (
                profile_key("ds", "BASE_URL"),
                "https://example.test/v1".into(),
            ),
            (profile_key("ds", "MODEL"), "demo".into()),
            (profile_key("ds", "API_KEY"), "named-secret".into()),
        ]);
        let resolved = resolve_values(&values).unwrap();
        assert_eq!(resolved.key.as_deref(), Some("named-secret"));
        assert_eq!(resolved.model.as_deref(), Some("demo"));
        values.insert(ACTIVE.into(), "missing".into());
        assert!(resolve_values(&values).is_err());
    }
    #[test]
    fn preserves_comments_and_secret_characters() {
        let source =
            "# keep\r\nOTHER=untouched\r\nOURDESKPET_PROFILE_DS_API_KEY=\"old\" # note\r\n";
        let key = "a#b=c\"d\\e";
        let next = patch(
            source,
            &BTreeMap::from([(profile_key("ds", "API_KEY"), key.into())]),
        );
        assert!(next.contains("# keep\r\nOTHER=untouched"));
        assert!(next.contains(" # note"));
        assert_eq!(parse(&next).unwrap()[&profile_key("ds", "API_KEY")], key);
    }
    #[test]
    fn discovers_profiles_and_does_not_expose_keys() {
        let s="OURDESKPET_PROFILE_DS_BASE_URL=https://example.com/v1\nOURDESKPET_PROFILE_DS_MODEL=m\nOURDESKPET_PROFILE_DS_API_KEY=super-secret\nOURDESKPET_PROFILE_QWEN_MODEL=q\nOURDESKPET_ACTIVE_PROFILE=ds\n";
        let snap = snapshot(Path::new("test.env"), s).unwrap();
        let ds = snap.profiles.iter().find(|p| p.id == "ds").unwrap();
        assert!(ds.ready);
        assert!(!snap.profiles.iter().find(|p| p.id == "qwen").unwrap().ready);
        assert!(!serde_json::to_string(&snap)
            .unwrap()
            .contains("super-secret"));
    }
    #[test]
    fn rejects_partial_quotes_and_credential_urls() {
        assert!(parse("KEY=\"unterminated").is_err());
        assert!(!valid_url("https://user:key@example.com"));
        assert!(!valid_url("https://example.com?key=x"));
        assert!(!valid_id("ds-fast"));
    }
    #[test]
    fn file_conflict_is_non_destructive() {
        let path =
            std::env::temp_dir().join(format!("rinadesk-config-test-{}.env", std::process::id()));
        fs::write(&path, "OTHER=first\n").unwrap();
        let rev = revision("OTHER=first\n");
        fs::write(&path, "OTHER=external\n").unwrap();
        assert!(commit(&path, &rev, &BTreeMap::from([(ACTIVE.into(), "ds".into())])).is_err());
        assert_eq!(read(&path).unwrap(), "OTHER=external\n");
        let rev = revision(&read(&path).unwrap());
        commit(&path, &rev, &BTreeMap::from([(ACTIVE.into(), "ds".into())])).unwrap();
        assert_eq!(parse(&read(&path).unwrap()).unwrap()[ACTIVE], "ds");
        fs::remove_file(path).unwrap();
    }
}
