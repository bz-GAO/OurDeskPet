use super::*;
use std::collections::BTreeMap;

#[derive(Clone, Serialize, Deserialize, Debug, PartialEq)]
#[serde(rename_all = "camelCase", default)]
pub struct Options {
    pub keep: usize,
    pub trigger: usize,
    pub summary_target: usize,
    pub summary_cap: usize,
    pub context_chars: usize,
    pub read_timeout: u64,
    pub search_mode: String,
    pub search_enabled: bool,
    pub search_url: String,
    pub project_read_enabled: bool,
    pub project_settings_enabled: bool,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            keep: 8,
            trigger: 12,
            summary_target: 300,
            summary_cap: 500,
            context_chars: 12000,
            read_timeout: 180,
            search_mode: "auto".into(),
            search_enabled: true,
            search_url: "https://api.tavily.com".into(),
            project_read_enabled: false,
            project_settings_enabled: false,
        }
    }
}
impl Options {
    pub fn validate(&self) -> Result<(), String> {
        if !(2..=32).contains(&self.keep) || self.trigger <= self.keep || self.trigger > 48 {
            return Err("保留轮数需为2–32，整理轮数应大于保留轮数且不超过48。".into());
        }
        if !(100..=2000).contains(&self.summary_target)
            || self.summary_cap < self.summary_target
            || self.summary_cap > 2000
        {
            return Err("摘要目标至少100字，上限不得小于目标或超过2000字。".into());
        }
        if !(4000..=100000).contains(&self.context_chars)
            || !(15..=600).contains(&self.read_timeout)
        {
            return Err("上下文范围为4000–100000字符，等待时间为15–600秒。".into());
        }
        if !["auto", "off", "required"].contains(&self.search_mode.as_str()) {
            return Err("联网模式无效。".into());
        }
        let url = reqwest::Url::parse(&self.search_url).map_err(|_| "搜索地址无效")?;
        if !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || !(url.scheme() == "https"
                || (url.scheme() == "http"
                    && matches!(url.host_str(), Some("localhost" | "127.0.0.1"))))
        {
            return Err("搜索地址应使用HTTPS，且不包含账号、参数或片段。".into());
        }
        Ok(())
    }
    pub fn from_reader(read: impl Fn(&str) -> Option<String>) -> Self {
        let mut o = Self::default();
        macro_rules! number {
            ($field:ident,$key:literal) => {
                if let Some(v) = read($key).and_then(|s| s.parse().ok()) {
                    o.$field = v;
                }
            };
        }
        number!(keep, "OURDESKPET_HISTORY_KEEP");
        number!(trigger, "OURDESKPET_HISTORY_TRIGGER");
        number!(summary_target, "OURDESKPET_SUMMARY_TARGET");
        number!(summary_cap, "OURDESKPET_SUMMARY_CAP");
        number!(context_chars, "OURDESKPET_CONTEXT_CHARS");
        number!(read_timeout, "OURDESKPET_READ_TIMEOUT_SECS");
        // Before settings existed, values above 12000 were capped. Preserve that default until a preset is saved.
        if read("OURDESKPET_HISTORY_KEEP").is_none() {
            o.context_chars = o.context_chars.min(12000);
        }
        if let Some(v) = read("OURDESKPET_SEARCH_MODE") {
            o.search_mode = v;
        }
        o.search_enabled = read("OURDESKPET_SEARCH_ENABLED").as_deref() != Some("false");
        o.project_read_enabled = read("OURDESKPET_PROJECT_READ_ENABLED").as_deref() == Some("true");
        o.project_settings_enabled =
            read("OURDESKPET_PROJECT_SETTINGS_ENABLED").as_deref() == Some("true");
        if let Some(v) = read("OURDESKPET_TAVILY_BASE_URL") {
            if !v.is_empty() {
                o.search_url = v.trim_end_matches('/').into();
            }
        }
        o
    }
    fn updates(&self) -> BTreeMap<String, String> {
        [
            ("OURDESKPET_HISTORY_KEEP", self.keep.to_string()),
            ("OURDESKPET_HISTORY_TRIGGER", self.trigger.to_string()),
            ("OURDESKPET_SUMMARY_TARGET", self.summary_target.to_string()),
            ("OURDESKPET_SUMMARY_CAP", self.summary_cap.to_string()),
            ("OURDESKPET_CONTEXT_CHARS", self.context_chars.to_string()),
            (
                "OURDESKPET_READ_TIMEOUT_SECS",
                self.read_timeout.to_string(),
            ),
            ("OURDESKPET_SEARCH_MODE", self.search_mode.clone()),
            ("OURDESKPET_SEARCH_ENABLED", self.search_enabled.to_string()),
            ("OURDESKPET_TAVILY_BASE_URL", self.search_url.clone()),
            (
                "OURDESKPET_PROJECT_READ_ENABLED",
                self.project_read_enabled.to_string(),
            ),
        ]
        .into_iter()
        .map(|(k, v)| (k.into(), v))
        .collect()
    }
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    revision: String,
    options: Options,
    has_key: bool,
    search_available: bool,
    account_search_available: bool,
    search_backend: String,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Save {
    revision: String,
    options: Options,
    key: Option<String>,
    #[serde(default)]
    clear_key: bool,
}
#[tauri::command]
pub fn chat_settings_get(app: tauri::AppHandle) -> Result<Snapshot, String> {
    let path = api_profiles::location(Some(&app))?;
    let text = api_profiles::read(&path)?;
    let values = api_profiles::parse(&text)?;
    let options = Options::from_reader(|k| values.get(k).cloned());
    let api = api_profiles::resolve(Some(&app))?;
    let has_key = values.get("TAVILY_API_KEY").is_some_and(|s| !s.is_empty());
    let account_search_available = billing::provider(&api.url) == Some("deepseek")
        && api.key.as_deref().is_some_and(|key| !key.trim().is_empty());
    let search_backend = match (account_search_available, has_key) {
        (true, true) => "DeepSeek · Tavily 备用",
        (true, false) => "DeepSeek",
        (false, true) => "Tavily",
        _ => "未配置",
    }
    .into();
    Ok(Snapshot {
        revision: api_profiles::revision(&text),
        search_available: options.search_enabled && (account_search_available || has_key),
        options,
        has_key,
        account_search_available,
        search_backend,
    })
}
#[tauri::command]
pub fn chat_settings_save(app: tauri::AppHandle, request: Save) -> Result<Snapshot, String> {
    let _guard = api_profiles::WRITE_LOCK
        .lock()
        .map_err(|_| "配置正在处理")?;
    request.options.validate()?;
    let mut updates = request.options.updates();
    updates.insert(
        "OURDESKPET_PROJECT_SETTINGS_ENABLED".into(),
        request.options.project_settings_enabled.to_string(),
    );
    if request.clear_key {
        updates.insert("TAVILY_API_KEY".into(), String::new());
    } else if let Some(key) = request.key.filter(|s| !s.trim().is_empty()) {
        if key.len() > 4096 || key.contains(['\r', '\n']) {
            return Err("搜索密钥格式无效。".into());
        }
        updates.insert("TAVILY_API_KEY".into(), key.trim().into());
    }
    let path = api_profiles::location(Some(&app))?;
    api_profiles::commit(&path, &request.revision, &updates)?;
    let _ = app.emit("deskpet-api-config-changed", ());
    chat_settings_get(app)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn settings_survive_a_fresh_process_and_working_directory() {
        const KEY: &str = "RINADESK_TEST_RESTART_CONFIG";
        if let Some(path) = std::env::var_os(KEY) {
            let text = api_profiles::read(std::path::Path::new(&path)).unwrap();
            let values = api_profiles::parse(&text).unwrap();
            let options = Options::from_reader(|k| values.get(k).cloned());
            assert_eq!(options.keep, 12);
            assert_eq!(options.trigger, 20);
            assert_eq!(options.search_mode, "off");
            assert!(options.project_read_enabled);
            assert_eq!(
                values.get("UNRELATED").map(String::as_str),
                Some("preserved")
            );
            return;
        }
        let root = std::env::temp_dir().join(format!(
            "desk-restart-{}-{}",
            std::process::id(),
            chrono::Utc::now().timestamp_nanos_opt().unwrap()
        ));
        std::fs::create_dir(&root).unwrap();
        let path = root.join("fixture.env");
        std::fs::write(&path, "UNRELATED=preserved\n").unwrap();
        let options = Options {
            keep: 12,
            trigger: 20,
            search_mode: "off".into(),
            project_read_enabled: true,
            ..Options::default()
        };
        api_profiles::commit(
            &path,
            &api_profiles::revision(&api_profiles::read(&path).unwrap()),
            &options.updates(),
        )
        .unwrap();
        let mut command = std::process::Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--exact",
                "chat_settings::tests::settings_survive_a_fresh_process_and_working_directory",
            ])
            .env(KEY, &path)
            .current_dir(std::env::temp_dir());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let result = command.output().unwrap();
        assert!(
            result.status.success(),
            "child restart check failed: {}",
            String::from_utf8_lossy(&result.stdout)
        );
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
    #[test]
    fn defaults_and_validation() {
        let mut o = Options::default();
        assert!(o.validate().is_ok());
        assert!(!o.project_read_enabled);
        o.trigger = o.keep;
        assert!(o.validate().is_err());
        o = Options::default();
        o.summary_cap = 200;
        assert!(o.validate().is_err());
        o = Options::default();
        o.search_url = "https://user:key@example.com".into();
        assert!(o.validate().is_err());
    }
    #[test]
    fn project_read_requires_explicit_true() {
        assert!(!Options::from_reader(|_| None).project_read_enabled);
        assert!(
            Options::from_reader(
                |key| (key == "OURDESKPET_PROJECT_READ_ENABLED").then(|| "true".into())
            )
            .project_read_enabled
        );
    }
    #[test]
    fn roundtrip_presets() {
        for (keep, trigger, target, cap, budget) in
            [(8, 12, 300, 500, 12000), (12, 20, 600, 1000, 24000)]
        {
            let o = Options {
                keep,
                trigger,
                summary_target: target,
                summary_cap: cap,
                context_chars: budget,
                ..Options::default()
            };
            let map = o.updates();
            assert_eq!(Options::from_reader(|k| map.get(k).cloned()), o);
        }
    }
}
