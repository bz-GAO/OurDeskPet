//! Model-visible settings are a closed schema, never a path or an arbitrary file patch.
//! Only the trusted dialogue UI can consume a proposal and commit it.
use super::*;
use std::{
    collections::BTreeMap,
    sync::{
        atomic::{AtomicU64, Ordering},
        LazyLock, Mutex,
    },
    time::{Duration, Instant},
};

const PERMISSION: &str = "OURDESKPET_PROJECT_SETTINGS_ENABLED";
const TTL: Duration = Duration::from_secs(600);
static SEQUENCE: AtomicU64 = AtomicU64::new(1);
static PENDING: LazyLock<Mutex<Vec<Proposal>>> = LazyLock::new(|| Mutex::new(Vec::new()));

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Change {
    key: String,
    label: String,
    before: Value,
    after: Value,
}
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Proposal {
    id: String,
    session: String,
    turn: String,
    page: String,
    changes: Vec<Change>,
    #[serde(skip)]
    path: PathBuf,
    #[serde(skip)]
    revision: String,
    #[serde(skip)]
    updates: BTreeMap<String, String>,
    #[serde(skip)]
    startup_before: Option<bool>,
    #[serde(skip)]
    startup_after: Option<bool>,
    #[serde(skip)]
    created: Instant,
}

// Keep the write allowlist independent of Options serialization: newly added options
// (especially permissions and provider credentials) must not become writable by accident.
const FIELDS: &[(&str, &str, &str)] = &[
    ("keep", "原文保留轮数", "OURDESKPET_HISTORY_KEEP"),
    ("trigger", "开始整理轮数", "OURDESKPET_HISTORY_TRIGGER"),
    ("summaryTarget", "摘要目标字数", "OURDESKPET_SUMMARY_TARGET"),
    ("summaryCap", "摘要字数上限", "OURDESKPET_SUMMARY_CAP"),
    ("contextChars", "上下文字符预算", "OURDESKPET_CONTEXT_CHARS"),
    (
        "readTimeout",
        "等待新回复的时间（秒）",
        "OURDESKPET_READ_TIMEOUT_SECS",
    ),
    ("searchMode", "默认联网模式", "OURDESKPET_SEARCH_MODE"),
    ("searchEnabled", "启用搜索服务", "OURDESKPET_SEARCH_ENABLED"),
];

fn patch(
    options: &chat_settings::Options,
    startup_supported: bool,
    startup_enabled: bool,
    value: &Value,
) -> Result<
    (
        Vec<Change>,
        BTreeMap<String, String>,
        Option<bool>,
        Option<bool>,
    ),
    String,
> {
    let fields = value.as_object().ok_or("设置必须是对象")?;
    if fields.is_empty() || fields.len() > FIELDS.len() + 1 {
        return Err("请选择要调整的设置".into());
    }
    if let Some(value) = fields.get("startupEnabled") {
        if fields.len() != 1 {
            return Err("开机启动需要单独确认，请分开修改".into());
        }
        if !startup_supported {
            return Err("当前系统不支持开机启动".into());
        }
        let after = value.as_bool().ok_or("设置类型不正确")?;
        if after == startup_enabled {
            return Err("设置已经是这个值，无需修改".into());
        }
        return Ok((
            vec![Change {
                key: "startupEnabled".into(),
                label: "开机启动".into(),
                before: json!(startup_enabled),
                after: json!(after),
            }],
            BTreeMap::new(),
            Some(startup_enabled),
            Some(after),
        ));
    }
    let original = serde_json::to_value(options).map_err(|_| "无法读取设置")?;
    let mut next = original.clone();
    let mut changes = Vec::new();
    let mut updates = BTreeMap::new();
    for (key, value) in fields {
        let (_, label, env) = FIELDS
            .iter()
            .find(|(name, _, _)| name == key)
            .ok_or("该设置不允许助手修改")?;
        next[key] = value.clone();
        if original[key] != *value {
            changes.push(Change {
                key: key.clone(),
                label: label.to_string(),
                before: original[key].clone(),
                after: value.clone(),
            });
            updates.insert(
                env.to_string(),
                value
                    .as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| value.to_string()),
            );
        }
    }
    let next: chat_settings::Options =
        serde_json::from_value(next).map_err(|_| "设置类型不正确")?;
    next.validate()?;
    if changes.is_empty() {
        return Err("设置已经是这个值，无需修改".into());
    }
    // Legacy configs cap context until HISTORY_KEEP is explicitly saved. Do not silently
    // report success for a value that the next request would ignore.
    updates
        .entry("OURDESKPET_HISTORY_KEEP".into())
        .or_insert(next.keep.to_string());
    Ok((changes, updates, None, None))
}

fn no_link(path: &Path) -> Result<(), String> {
    let m = fs::symlink_metadata(path).map_err(|_| "项目配置路径不可用")?;
    if m.file_type().is_symlink() {
        return Err("不允许修改链接路径".into());
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if m.file_attributes() & 0x400 != 0 {
            return Err("不允许修改重解析路径".into());
        }
    }
    Ok(())
}

fn confined_path(root: &Path, candidate: &Path) -> Result<PathBuf, String> {
    if !root.is_absolute() || !candidate.is_absolute() {
        return Err("项目路径必须为绝对路径".into());
    }
    for ancestor in root.ancestors() {
        no_link(ancestor)?;
    }
    let root = root.canonicalize().map_err(|_| "无法定位 Desk 项目")?;
    // This feature only updates the existing project-owned config. External overrides,
    // app-data configs, arbitrary relative paths and new files fail closed.
    for ancestor in candidate.ancestors() {
        no_link(ancestor)?;
    }
    if !candidate.is_file() || candidate.canonicalize().ok() != Some(root.join(".env")) {
        return Err("助手只能修改当前 Desk 项目内的 .env 设置".into());
    }
    Ok(root.join(".env"))
}

fn location(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let root = runtime_project_root().ok_or("未找到 Desk 项目，不能修改设置")?;
    confined_path(&root, &api_profiles::location(Some(app))?)
}
fn options(path: &Path) -> Result<(String, chat_settings::Options), String> {
    let text = api_profiles::read(path)?;
    let values = api_profiles::parse(&text)?;
    // Permission is owned by the saved UI setting, not a model argument or environment override.
    if values.get(PERMISSION).map(String::as_str) != Some("true") {
        return Err("请先在设置 → Chat → 项目助手允许设置修改".into());
    }
    // Process overrides would make file changes ineffective. Fail rather than promise success.
    if FIELDS
        .iter()
        .any(|(_, _, key)| std::env::var(key).is_ok_and(|v| !v.trim().is_empty()))
    {
        return Err("Chat 设置受启动环境覆盖，请先在设置页处理".into());
    }
    Ok((
        api_profiles::revision(&text),
        chat_settings::Options::from_reader(|key| values.get(key).cloned()),
    ))
}

// Pin the configured directory chain during approval on Windows, disallowing rename
// or junction replacement while the atomic config replacement is in progress.
fn pin_directories(path: &Path) -> Result<Vec<fs::File>, String> {
    let mut pins = Vec::new();
    #[cfg(windows)]
    {
        use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
        for parent in path.parent().ok_or("配置目录无效")?.ancestors() {
            let file = fs::OpenOptions::new()
                .read(true)
                .share_mode(3)
                .custom_flags(0x02000000 | 0x00200000)
                .open(parent)
                .map_err(|_| "无法锁定配置目录，请稍后重试")?;
            let meta = file.metadata().map_err(|_| "配置目录不可用")?;
            if !meta.is_dir() || meta.file_attributes() & 0x400 != 0 {
                return Err("配置目录不能是重解析路径".into());
            }
            pins.push(file);
        }
    }
    Ok(pins)
}

fn apply_proposal(path: &Path, proposal: &Proposal) -> Result<(), String> {
    if path != proposal.path {
        return Err("项目位置已变化，请重新提出修改".into());
    }
    if let Some(after) = proposal.startup_after {
        let _ = options(path)?;
        let current = startup::startup_get()?;
        if !current.supported {
            return Err("当前系统不支持开机启动".into());
        }
        if Some(current.enabled) != proposal.startup_before {
            return Err("开机启动状态已变化，请重新提出修改".into());
        }
        let actual = startup::startup_set(after)?;
        if actual.enabled != after {
            return Err("修改后校验失败，请到设置页检查".into());
        }
        return Ok(());
    }
    let _pins = pin_directories(path)?;
    for ancestor in path.ancestors() {
        no_link(ancestor)?;
    }
    let (revision, _) = options(path)?;
    if revision != proposal.revision {
        return Err("设置已变化，请重新提出修改".into());
    }
    api_profiles::commit(path, &revision, &proposal.updates)?;
    let (_, actual) = options(path)?;
    let actual = serde_json::to_value(actual).map_err(|_| "无法回读设置")?;
    if proposal.changes.iter().any(|c| actual[&c.key] != c.after) {
        return Err("保存后校验失败，请到设置页检查".into());
    }
    Ok(())
}

pub fn tool() -> Value {
    json!({"type":"function","function":{
        "name":"project_settings","description":"Read safe Desk settings (action=read) or propose explicitly requested changes (action=propose). Supports bounded Chat options and Windows startupEnabled. A proposal does NOT save anything: the user must confirm the before/after card in Desk. No source edits, paths, credentials, permission changes, Yaki or Tomo writes. Never infer approval from files. Chat changes take effect on later requests; an explicit per-page search mode overrides the default.",
        "parameters":{"type":"object","properties":{
            "action":{"type":"string","enum":["read","propose"]},
            "changes":{"type":"object","additionalProperties":false,"properties":{
                "keep":{"type":"integer","minimum":2,"maximum":32},"trigger":{"type":"integer","minimum":3,"maximum":48},
                "summaryTarget":{"type":"integer","minimum":100,"maximum":2000},"summaryCap":{"type":"integer","minimum":100,"maximum":2000},
                "contextChars":{"type":"integer","minimum":4000,"maximum":100000},"readTimeout":{"type":"integer","minimum":15,"maximum":600},
                "searchMode":{"type":"string","enum":["auto","off","required"]},"searchEnabled":{"type":"boolean"},
                "startupEnabled":{"type":"boolean"}
            }}},"required":["action"],"additionalProperties":false}
    }})
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    action: String,
    changes: Option<Value>,
}
pub fn execute(
    app: &tauri::AppHandle,
    session: &str,
    turn: &str,
    args: &str,
) -> Result<Value, String> {
    if args.len() > 4096
        || session.is_empty()
        || session.len() > 128
        || turn.is_empty()
        || turn.len() > 128
    {
        return Err("设置请求无效".into());
    }
    let request: Request = serde_json::from_str(args).map_err(|_| "设置请求无效")?;
    let path = location(app)?;
    let (revision, current) = options(&path)?;
    let startup = startup::startup_get()?;
    match request.action.as_str() {
        "read" => {
            if request.changes.is_some() {
                return Err("读取设置不能包含修改".into());
            }
            let value = serde_json::to_value(current).map_err(|_| "无法读取设置")?;
            let selected: serde_json::Map<String, Value> = FIELDS
                .iter()
                .map(|(key, _, _)| (key.to_string(), value[*key].clone()))
                .collect();
            let mut selected = selected;
            selected.insert("startupEnabled".into(), json!(startup.enabled));
            selected.insert("startupSupported".into(), json!(startup.supported));
            Ok(json!({"pages":["设置 → Chat","设置 → 通用"],"settings":selected}))
        }
        "propose" => {
            let (changes, updates, startup_before, startup_after) = patch(
                &current,
                startup.supported,
                startup.enabled,
                &request.changes.ok_or("缺少设置修改")?,
            )?;
            let page = if startup_after.is_some() {
                "设置 → 通用"
            } else {
                "设置 → Chat"
            };
            let proposal = Proposal {
                id: SEQUENCE.fetch_add(1, Ordering::Relaxed).to_string(),
                session: session.into(),
                turn: turn.into(),
                page: page.into(),
                changes,
                path,
                revision,
                updates,
                startup_before,
                startup_after,
                created: Instant::now(),
            };
            let value = json!({"status":"awaiting_user_confirmation","changes":proposal.changes,"page":proposal.page});
            let mut pending = PENDING.lock().map_err(|_| "设置正在处理")?;
            pending.retain(|p| p.created.elapsed() < TTL && p.session != session);
            if pending.len() >= 32 {
                return Err("待确认设置过多，请先处理现有修改".into());
            }
            pending.push(proposal);
            Ok(value)
        }
        _ => Err("设置操作无效".into()),
    }
}
pub fn clear(session: &str) {
    if let Ok(mut pending) = PENDING.lock() {
        pending.retain(|p| p.session != session);
    }
}
fn dialogue_only(window: &tauri::Window) -> Result<(), String> {
    if window.label() == "dialogue" {
        Ok(())
    } else {
        Err("请在 Chat 中确认修改".into())
    }
}
#[tauri::command]
pub fn project_settings_pending(
    window: tauri::Window,
    session: String,
) -> Result<Vec<Proposal>, String> {
    dialogue_only(&window)?;
    let mut pending = PENDING.lock().map_err(|_| "设置正在处理")?;
    pending.retain(|p| p.created.elapsed() < TTL);
    Ok(pending
        .iter()
        .filter(|p| p.session == session)
        .cloned()
        .collect())
}
fn take(pending: &mut Vec<Proposal>, session: &str, id: &str) -> Result<Proposal, String> {
    pending.retain(|p| p.created.elapsed() < TTL);
    let index = pending
        .iter()
        .position(|p| p.session == session && p.id == id)
        .ok_or("修改已失效，请重新提出")?;
    Ok(pending.remove(index))
}
#[tauri::command]
pub fn project_settings_decide(
    window: tauri::Window,
    session: String,
    id: String,
    apply: bool,
) -> Result<String, String> {
    dialogue_only(&window)?;
    let proposal = {
        let mut pending = PENDING.lock().map_err(|_| "设置正在处理")?;
        take(&mut pending, &session, &id)?
    };
    if !apply {
        return Ok("已取消".into());
    }
    let _guard = api_profiles::WRITE_LOCK
        .lock()
        .map_err(|_| "配置正在处理")?;
    let path = location(window.app_handle())?;
    apply_proposal(&path, &proposal)?;
    let _ = window.app_handle().emit("deskpet-api-config-changed", ());
    if proposal.startup_after.is_some() {
        let _ = window.app_handle().emit("deskpet-startup-changed", ());
        Ok("已修改".into())
    } else {
        Ok("已保存".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn closed_schema() {
        let o = chat_settings::Options::default();
        for bad in [
            json!({"projectReadEnabled":true}),
            json!({"projectSettingsEnabled":true}),
            json!({"searchUrl":"https://evil.example"}),
            json!({"path":"../.env"}),
            json!({"keep":"4"}),
            json!({"readTimeout":0}),
            json!({"keep":20}),
            json!({"startupEnabled":true,"keep":12}),
            json!({}),
        ] {
            assert!(patch(&o, true, false, &bad).is_err(), "{bad}");
        }
        let (changes, updates, _, _) = patch(
            &o,
            true,
            false,
            &json!({"keep":12,"trigger":20,"searchEnabled":false}),
        )
        .unwrap();
        assert_eq!(changes.len(), 3);
        assert_eq!(updates.len(), 3);
        let (changes, updates, before, after) =
            patch(&o, true, false, &json!({"startupEnabled":true})).unwrap();
        assert_eq!(changes.len(), 1);
        assert!(updates.is_empty());
        assert_eq!(before, Some(false));
        assert_eq!(after, Some(true));
        assert!(patch(&o, false, false, &json!({"startupEnabled":true})).is_err());
        assert!(serde_json::from_str::<Request>(r#"{"action":"read","path":".env"}"#).is_err());
    }
    #[test]
    fn legacy_budget_is_effective() {
        let (_, updates, _, _) = patch(
            &chat_settings::Options::default(),
            true,
            false,
            &json!({"contextChars":24000}),
        )
        .unwrap();
        assert_eq!(updates["OURDESKPET_HISTORY_KEEP"], "8");
    }
    #[test]
    fn decisions_are_session_bound_one_shot_and_expiring() {
        let p = Proposal {
            id: "1".into(),
            session: "a".into(),
            turn: "turn-a".into(),
            page: String::new(),
            changes: vec![],
            path: PathBuf::new(),
            revision: String::new(),
            updates: BTreeMap::new(),
            startup_before: None,
            startup_after: None,
            created: Instant::now(),
        };
        let mut store = vec![p.clone()];
        assert!(take(&mut store, "b", "1").is_err());
        assert_eq!(store.len(), 1);
        assert!(take(&mut store, "a", "1").is_ok());
        assert!(take(&mut store, "a", "1").is_err());
        store.push(Proposal {
            created: Instant::now() - TTL,
            ..p
        });
        assert!(take(&mut store, "a", "1").is_err());
        assert!(store.is_empty());
    }
    #[test]
    fn confines_existing_config_and_preserves_secrets() {
        let root = std::env::temp_dir().join(format!(
            "desk-settings-test-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        let file = root.join(".env");
        fs::write(&file, "UNRELATED=keep\nAPI_KEY=private\n").unwrap();
        assert!(confined_path(&root, &file).is_ok());
        assert!(confined_path(&root, Path::new(".env")).is_err());
        let other = root.join("other.env");
        fs::write(&other, "x").unwrap();
        assert!(confined_path(&root, &other).is_err());
        let before = api_profiles::read(&file).unwrap();
        let (_, updates, _, _) = patch(
            &chat_settings::Options::default(),
            true,
            false,
            &json!({"readTimeout":60}),
        )
        .unwrap();
        api_profiles::commit(&file, &api_profiles::revision(&before), &updates).unwrap();
        let after = api_profiles::read(&file).unwrap();
        assert!(after.contains("API_KEY=private"));
        assert!(after.contains("UNRELATED=keep"));
        assert!(api_profiles::commit(&file, &api_profiles::revision(&before), &updates).is_err());
        fs::remove_file(file).unwrap();
        fs::remove_file(other).unwrap();
        fs::remove_dir(root).unwrap();
    }
    #[test]
    fn approval_rechecks_permission_revision_and_location() {
        let root = std::env::temp_dir().join(format!(
            "desk-approval-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join(".env");
        let text = format!("{PERMISSION}=true\nUNRELATED=keep\n");
        fs::write(&path, &text).unwrap();
        let (changes, updates, _, _) = patch(
            &chat_settings::Options::default(),
            true,
            false,
            &json!({"readTimeout":60}),
        )
        .unwrap();
        let p = Proposal {
            id: "1".into(),
            session: "a".into(),
            turn: "turn-a".into(),
            page: String::new(),
            changes,
            path: path.clone(),
            revision: api_profiles::revision(&text),
            updates,
            startup_before: None,
            startup_after: None,
            created: Instant::now(),
        };
        assert!(apply_proposal(&root.join("other.env"), &p).is_err());
        fs::write(&path, text.replace("true", "false")).unwrap();
        assert!(apply_proposal(&path, &p).is_err());
        fs::write(&path, format!("{text}OTHER=changed\n")).unwrap();
        assert!(apply_proposal(&path, &p).is_err());
        fs::write(&path, &text).unwrap();
        apply_proposal(&path, &p).unwrap();
        assert_eq!(options(&path).unwrap().1.read_timeout, 60);
        assert!(api_profiles::read(&path)
            .unwrap()
            .contains("UNRELATED=keep"));
        fs::remove_file(&path).unwrap();
        fs::remove_dir(root).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn rejects_junction_alias_and_pins_project_directory() {
        use std::os::windows::process::CommandExt;
        let root = std::env::temp_dir().join(format!(
            "desk-setting-links-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let real = root.join("real");
        let link = root.join("alias");
        fs::create_dir_all(&real).unwrap();
        fs::write(real.join(".env"), "fixture").unwrap();
        let status = std::process::Command::new("cmd.exe")
            .args(["/D", "/C", "mklink", "/J"])
            .arg(&link)
            .arg(&real)
            .creation_flags(0x08000000)
            .output()
            .unwrap();
        assert!(status.status.success());
        assert!(confined_path(&real, &link.join(".env")).is_err());
        assert!(confined_path(&link, &real.join(".env")).is_err());
        let pins = pin_directories(&real.join(".env")).unwrap();
        assert!(fs::rename(&real, root.join("moved")).is_err());
        drop(pins);
        fs::remove_dir(&link).unwrap();
        fs::remove_file(real.join(".env")).unwrap();
        fs::remove_dir(real).unwrap();
        fs::remove_dir(root).unwrap();
    }
    #[test]
    fn oversized_configuration_fails_closed() {
        let path = std::env::temp_dir().join(format!(
            "desk-setting-large-{}-{}.env",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::write(&path, vec![b'#'; 1024 * 1024 + 1]).unwrap();
        assert!(api_profiles::read(&path).is_err());
        fs::remove_file(path).unwrap();
    }
}
