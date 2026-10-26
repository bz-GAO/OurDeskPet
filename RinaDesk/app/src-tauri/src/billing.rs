//! Provider detection and daily local estimates; credentials never leave the backend.
use super::*;
use chrono::{Duration as ChronoDuration, Local, Utc};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    sync::{LazyLock, Mutex},
    time::Instant,
};

static WRITE: Mutex<()> = Mutex::new(());
static APP: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();
type BalanceSlot = std::sync::Arc<tokio::sync::Mutex<Option<(Instant, Balance)>>>;
static BALANCES: LazyLock<Mutex<HashMap<String, BalanceSlot>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));
const REFRESH: Duration = Duration::from_secs(600);
const RETRY_REFRESH: Duration = Duration::from_secs(30);
const LIMIT: u64 = 256 * 1024;
// Standard CNY list price for a non-empty HTTP 200 Search response. Temporary
// launch waivers and promotions are intentionally not deducted from estimates.
const DEEPSEEK_SEARCH_MICRO_CNY: u64 = 5_000;
#[cfg(test)]
#[path = "billing_live_test.rs"]
mod live_test;
#[derive(Clone, Default, Serialize, Deserialize)]
#[serde(default)]
struct Counter {
    amount_micro: u64,
    calls: u64,
    unknown: u64,
    tokens: u64,
}
#[derive(Default, Serialize, Deserialize)]
struct Ledger {
    schema: u32,
    day: String,
    accounts: BTreeMap<String, Counter>,
    #[serde(default)]
    history: BTreeMap<String, BTreeMap<String, Counter>>,
}
#[derive(Serialize)]
struct DailyUsage {
    day: String,
    #[serde(flatten)]
    counter: Counter,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Balance {
    values: Vec<(String, String)>,
    updated_at: String,
    message: String,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Account {
    id: String,
    label: String,
    active: bool,
    balance: Balance,
    today: Counter,
    history: Vec<DailyUsage>,
    day: String,
    incomplete: bool,
    billing_connected: bool,
}
#[derive(Clone)]
struct Credential {
    id: String,
    provider: String,
    key: String,
}

pub fn provider(url: &str) -> Option<&'static str> {
    let parsed = reqwest::Url::parse(url).ok()?;
    if parsed.scheme() != "https"
        || parsed.port_or_known_default() != Some(443)
        || !parsed.username().is_empty()
        || parsed.password().is_some()
    {
        return None;
    }
    match parsed.host_str()? {
        "api.deepseek.com" => Some("deepseek"),
        "dashscope.aliyuncs.com" | "dashscope-intl.aliyuncs.com" | "dashscope-us.aliyuncs.com" => {
            Some("bailian")
        }
        "maas.qianwenaiapi.com" => Some("qianwen"),
        _ => None,
    }
}
fn identity(provider: &str, key: &str) -> String {
    format!(
        "{provider}:{:x}",
        Sha256::digest(format!("{provider}\n{key}").as_bytes())
    )
}
pub(super) fn home(name: &str) -> Result<PathBuf, String> {
    crate::release_profile::data_dir(name)
}
fn safe_read(path: &Path) -> Result<Option<Value>, String> {
    no_redirect(path)?;
    if !path.exists() {
        return Ok(None);
    }
    let file = fs::File::open(path).map_err(|_| "用量文件不可用")?;
    if !file.metadata().map_err(|_| "用量文件不可用")?.is_file() {
        return Err("用量文件无效".into());
    }
    let mut bytes = Vec::new();
    file.take(LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "用量文件不可用")?;
    if bytes.len() as u64 > LIMIT {
        return Err("用量文件过大".into());
    }
    serde_json::from_slice(&bytes)
        .map(Some)
        .map_err(|_| "用量文件损坏".to_string())
}
pub(super) fn no_redirect(path: &Path) -> Result<(), String> {
    for ancestor in path.ancestors() {
        let m = match fs::symlink_metadata(ancestor) {
            Ok(m) => m,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(_) => return Err("用量文件不可用".into()),
        };
        if m.file_type().is_symlink() {
            return Err("用量路径不能是链接".into());
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if m.file_attributes() & 0x400 != 0 {
                return Err("用量路径不能是目录联接".into());
            }
        }
    }
    Ok(())
}
fn daily(path: &Path, day: &str) -> Result<Ledger, String> {
    let Some(v) = safe_read(path)? else {
        return Ok(Ledger {
            schema: 2,
            day: day.into(),
            ..Ledger::default()
        });
    };
    let mut l: Ledger = serde_json::from_value(v).map_err(|_| "用量文件损坏")?;
    if !matches!(l.schema, 1 | 2) {
        return Err("用量文件版本不支持".into());
    }
    l.schema = 2;
    if l.day != day {
        if !l.day.is_empty() && !l.accounts.is_empty() {
            l.history
                .insert(l.day.clone(), std::mem::take(&mut l.accounts));
        }
        l.day = day.into();
    }
    l.history.remove(day);
    while l.history.len() > 31 {
        if let Some(oldest) = l.history.keys().next().cloned() {
            l.history.remove(&oldest);
        } else {
            break;
        }
    }
    Ok(l)
}
fn add_counter(target: &mut Counter, value: Counter) {
    target.amount_micro = target.amount_micro.saturating_add(value.amount_micro);
    target.calls = target.calls.saturating_add(value.calls);
    target.unknown = target.unknown.saturating_add(value.unknown);
    target.tokens = target.tokens.saturating_add(value.tokens);
}
fn number(usage: &Value, names: &[&str]) -> Option<u64> {
    names
        .iter()
        .find_map(|key| usage.get(*key).and_then(Value::as_u64))
        .filter(|n| *n <= 10_000_000)
}
// Reviewed 2026-10-17. DeepSeek uses the peak-rate estimate (holiday/promotion
// discounts are not assumed). Unsupported models/modalities are marked incomplete.
fn estimate(provider: &str, model: &str, usage: &Value) -> Option<(u64, u64)> {
    let input = number(usage, &["prompt_tokens", "input_tokens"])?;
    let output = number(usage, &["completion_tokens", "output_tokens"])?;
    let cached = number(usage, &["prompt_cache_hit_tokens"])
        .or_else(|| {
            usage
                .pointer("/prompt_tokens_details/cached_tokens")
                .and_then(Value::as_u64)
        })
        .unwrap_or(0);
    if cached > input {
        return None;
    }
    let (hit, miss, out) = match (provider, model) {
        ("deepseek", "deepseek-flash" | "deepseek-v4-flash" | "deepseek-v4-flash-vision-exp") => {
            (0.04, 2.0, 8.0)
        }
        ("bailian", "deepseek-v4.1-flash") => (0.04, 2.0, 8.0),
        ("bailian", "qwen3.8-flash") => (0.8, 0.8, 2.7),
        ("bailian", "qwen-mt-flash") => (0.7, 0.7, 1.95),
        ("bailian", "qwen-mt-plus") => (1.8, 1.8, 5.4),
        _ => return None,
    };
    Some((
        (cached as f64 * hit + (input - cached) as f64 * miss + output as f64 * out).ceil() as u64,
        input + output,
    ))
}
fn persist(config: &LlmConfig, addition: Counter) {
    let Some(p) = provider(&config.base_url) else {
        return;
    };
    let Some(key) = config.api_key.as_deref().filter(|k| !k.is_empty()) else {
        return;
    };
    let result = (|| -> Result<(), String> {
        let _lock = WRITE.lock().map_err(|_| "用量写入忙")?;
        let folder = home("RinaDesk")?;
        no_redirect(&folder)?;
        fs::create_dir_all(&folder).map_err(|_| "无法保存用量")?;
        let path = folder.join("billing.json");
        let day = Local::now().format("%Y-%m-%d").to_string();
        let mut ledger = daily(&path, &day)?;
        add_counter(
            ledger.accounts.entry(identity(p, key)).or_default(),
            addition,
        );
        let temporary = folder.join(format!(
            ".billing-{}-{}.tmp",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap_or(0)
        ));
        let bytes = serde_json::to_vec(&ledger).map_err(|_| "无法保存用量")?;
        if bytes.len() as u64 > LIMIT {
            return Err("用量文件过大".into());
        }
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .map_err(|_| "无法保存用量")?;
        if file
            .write_all(&bytes)
            .and_then(|_| file.sync_all())
            .is_err()
        {
            drop(file);
            let _ = fs::remove_file(&temporary);
            return Err("无法保存用量".into());
        }
        drop(file);
        if fs::rename(&temporary, &path).is_err() {
            let _ = fs::remove_file(&temporary);
            return Err("无法替换用量文件".into());
        }
        Ok(())
    })();
    if result.is_err() {
        eprintln!("Daily usage could not be persisted; no credentials logged.");
    }
    if let Some(app) = APP.get() {
        let _ = app.emit("deskpet-billing-updated", ());
    }
}
pub fn record(config: &LlmConfig, usage: Option<&Value>) {
    let Some(p) = provider(&config.base_url) else {
        return;
    };
    let regional = p != "bailian"
        || reqwest::Url::parse(&config.base_url)
            .ok()
            .is_some_and(|u| u.host_str() == Some("dashscope.aliyuncs.com"));
    let addition = if let Some((amount_micro, tokens)) = usage
        .filter(|_| regional)
        .and_then(|value| estimate(p, config.model.as_deref().unwrap_or(""), value))
    {
        Counter {
            amount_micro,
            calls: 1,
            tokens,
            ..Counter::default()
        }
    } else {
        Counter {
            calls: 1,
            unknown: 1,
            ..Counter::default()
        }
    };
    persist(config, addition);
}
pub fn record_search(config: &LlmConfig) {
    if provider(&config.base_url) == Some("deepseek") {
        persist(
            config,
            Counter {
                amount_micro: DEEPSEEK_SEARCH_MICRO_CNY,
                calls: 1,
                ..Counter::default()
            },
        );
    }
}
pub fn start(app: tauri::AppHandle) {
    let _ = APP.set(app.clone());
    tauri::async_runtime::spawn(async move {
        loop {
            let _ = billing_status(app.clone(), false, None).await;
            tokio::time::sleep(REFRESH).await;
        }
    });
}
pub struct Receipt<'a> {
    config: &'a LlmConfig,
    active: bool,
    pub usage: Option<Value>,
}
impl<'a> Receipt<'a> {
    pub fn new(config: &'a LlmConfig) -> Self {
        Self {
            config,
            active: false,
            usage: None,
        }
    }
    pub fn accepted(&mut self) {
        self.active = true;
    }
}
impl Drop for Receipt<'_> {
    fn drop(&mut self) {
        if self.active {
            record(self.config, self.usage.as_ref());
        }
    }
}

fn credentials(app: &tauri::AppHandle) -> Vec<Credential> {
    let mut raw = Vec::new();
    if let Ok(c) = api_profiles::resolve(Some(app)) {
        if let Some(key) = c.key {
            raw.push((c.url, key));
        }
    }
    // Tool-owned configuration locations: read only their documented credential fields.
    // Runtime source roots use the same registration/launcher lookup as tool pages.
    if let Some(root) = rinatomo::project_root() {
        let mut values = api_profiles::read(&root.join(".env"))
            .and_then(|v| api_profiles::parse(&v))
            .unwrap_or_default();
        if let Ok(folder) = tool_home("RinaTomo", "RINATOMO_CONFIG_HOME") {
            if let Ok(v) =
                api_profiles::read(&folder.join(".env")).and_then(|v| api_profiles::parse(&v))
            {
                values.extend(v);
            }
        }
        let get = |k: &str| {
            env::var(k)
                .ok()
                .filter(|v| !v.trim().is_empty())
                .or_else(|| values.get(k).cloned())
                .unwrap_or_default()
        };
        let url = get("DASHSCOPE_BASE_URL");
        raw.push((
            if url.is_empty() {
                "https://dashscope.aliyuncs.com/compatible-mode/v1".into()
            } else {
                url
            },
            get("DASHSCOPE_API_KEY"),
        ));
    }
    if let Ok(root) = extension_tools::source_root(app) {
        if let Ok(folder) = tool_home("RinaYaki", "RINAYAKI_CONFIG_HOME") {
            let stored = safe_read(&folder.join("settings.json"))
                .ok()
                .flatten()
                .unwrap_or(Value::Null);
            let legacy = api_profiles::read(&root.join(".env"))
                .and_then(|v| api_profiles::parse(&v))
                .unwrap_or_default();
            let private = api_profiles::read(&folder.join("credentials.env"))
                .and_then(|v| api_profiles::parse(&v))
                .unwrap_or_default();
            let fallback = |k: &str| {
                env::var(k)
                    .ok()
                    .filter(|v| !v.trim().is_empty())
                    .or_else(|| legacy.get(k).cloned())
                    .unwrap_or_default()
            };
            let url = stored
                .get("base_url")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| fallback("DASHSCOPE_BASE_URL"));
            raw.push((
                if url.is_empty() {
                    "https://dashscope.aliyuncs.com/compatible-mode/v1".into()
                } else {
                    url
                },
                private
                    .get("DASHSCOPE_API_KEY")
                    .cloned()
                    .unwrap_or_else(|| fallback("DASHSCOPE_API_KEY")),
            ));
        }
    }
    let mut seen = std::collections::HashSet::new();
    raw.into_iter()
        .filter_map(|(url, key)| {
            let p = provider(&url)?;
            let key = key.trim().to_string();
            if key.is_empty() {
                return None;
            }
            let id = identity(p, &key);
            seen.insert(id.clone()).then(|| Credential {
                id,
                provider: p.into(),
                key,
            })
        })
        .collect()
}
pub(crate) fn tool_home(name: &str, override_name: &str) -> Result<PathBuf, String> {
    if let Some(p) = env::var_os(override_name).filter(|v| !v.is_empty()) {
        let p = PathBuf::from(p);
        if !p.is_absolute() {
            return Err("工具资料路径无效".into());
        }
        Ok(p)
    } else {
        // Derive sibling tool data from Desk's anchored installation root.
        // Packaged launchers may virtualize LOCALAPPDATA for child processes;
        // that must not split one user's ledgers across two invisible trees.
        let desk = home("RinaDesk")?;
        let parent = desk.parent().ok_or("本机资料目录无效")?;
        Ok(parent.join(name))
    }
}
fn label(p: &str) -> &str {
    match p {
        "deepseek" => "DeepSeek",
        "bailian" => "阿里云百炼",
        "qianwen" => "千问AI平台",
        _ => "其他平台",
    }
}
fn archived_provider(id: &str) -> Option<&str> {
    let (provider, digest) = id.split_once(':')?;
    (matches!(provider, "deepseek" | "bailian" | "qianwen")
        && digest.len() == 64
        && digest.bytes().all(|byte| byte.is_ascii_hexdigit()))
    .then_some(provider)
}
pub fn known_bailian_account(app: &tauri::AppHandle, id: &str) -> bool {
    credentials(app)
        .iter()
        .any(|c| c.id == id && c.provider == "bailian")
}
pub fn clear_balance_cache() {
    BALANCES.lock().unwrap_or_else(|e| e.into_inner()).clear();
}
fn balance_slot(id: &str) -> BalanceSlot {
    BALANCES
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .entry(id.into())
        .or_default()
        .clone()
}
async fn query_once<F, Fut>(slot: &BalanceSlot, force: bool, query: F) -> Balance
where
    F: FnOnce(Option<Balance>) -> Fut,
    Fut: std::future::Future<Output = Balance>,
{
    let requested = Instant::now();
    let mut cache = slot.lock().await;
    if let Some((when, b)) = cache.as_ref() {
        // A concurrent manual refresh shares the query that completed while it waited.
        if *when >= requested || (!force && when.elapsed() < balance_ttl(b)) {
            return b.clone();
        }
    }
    let result = query(cache.as_ref().map(|(_, b)| b.clone())).await;
    *cache = Some((Instant::now(), result.clone()));
    result
}
async fn balance(c: &Credential, force: bool) -> Balance {
    let slot = balance_slot(&c.id);
    query_once(&slot, force, |old| async {
        let result = fetch_balance(c, old).await;
        // An authorization change detaches this slot. Never persist its old response.
        let cache = BALANCES.lock().unwrap_or_else(|e| e.into_inner());
        if result.message.is_empty()
            && cache
                .get(&c.id)
                .is_some_and(|current| std::sync::Arc::ptr_eq(current, &slot))
        {
            save_balance(&c.id, &result);
        }
        result
    })
    .await
}
async fn fetch_balance(c: &Credential, old: Option<Balance>) -> Balance {
    let mut result = Balance {
        values: vec![],
        updated_at: String::new(),
        message: if c.provider == "deepseek" {
            "余额暂不可用"
        } else {
            "余额查询未连接"
        }
        .into(),
    };
    let mut transient = false;
    if c.provider == "deepseek" {
        match deepseek_balance(&c.key).await {
            Ok(values) => {
                result.values = values;
                result.updated_at = Utc::now().to_rfc3339();
                result.message.clear();
            }
            Err((message, retryable)) => {
                result.message = message;
                transient = retryable;
            }
        }
    } else if c.provider == "bailian" {
        match billing_connection::balance(&c.id).await {
            Ok(values) => {
                result.values = values;
                result.updated_at = Utc::now().to_rfc3339();
                result.message = String::new();
            }
            Err(message) => {
                transient = matches!(
                    message.as_str(),
                    "余额查询超时" | "余额网络连接失败" | "余额服务暂不可用" | "余额查询受限"
                );
                result.message = message;
            }
        }
    }
    // Always query the cloud first after restart. Use persisted successful values
    // only on transient failures, never for revoked/mismatched authorization.
    if transient {
        let old = old
            .filter(|b| !b.values.is_empty())
            .or_else(|| cached_balance(&c.id));
        if let Some(old) = old {
            result.values = old.values;
            result.updated_at = old.updated_at;
        }
    }
    result
}
#[tauri::command]
pub async fn billing_balance(
    app: tauri::AppHandle,
    account: String,
    force: bool,
) -> Result<Balance, String> {
    let c = credentials(&app)
        .into_iter()
        .find(|c| c.id == account)
        .ok_or("账户已变化，请刷新")?;
    let result = balance(&c, force).await;
    if !credentials(&app).iter().any(|c| c.id == account) {
        return Err("账户已变化，请刷新".into());
    }
    Ok(result)
}
fn balance_ttl(balance: &Balance) -> Duration {
    if balance.message.is_empty() {
        REFRESH
    } else {
        RETRY_REFRESH
    }
}
fn valid_amount(currency: &str, amount: &str) -> bool {
    matches!(currency, "CNY" | "USD" | "JPY")
        && amount.len() <= 32
        && amount.parse::<f64>().is_ok_and(|n| n.is_finite())
}
fn parse_deepseek_balance(value: &Value) -> Result<Vec<(String, String)>, String> {
    let items = value
        .get("balance_infos")
        .and_then(Value::as_array)
        .ok_or("余额响应格式异常")?;
    let mut values = Vec::new();
    for item in items {
        let currency = item
            .get("currency")
            .and_then(Value::as_str)
            .ok_or("余额响应格式异常")?;
        let amount = item
            .get("total_balance")
            .and_then(Value::as_str)
            .ok_or("余额响应格式异常")?;
        if !matches!(currency, "CNY" | "USD") || !valid_amount(currency, amount) {
            return Err("余额响应格式异常".into());
        }
        values.push((currency.into(), amount.into()));
    }
    if values.is_empty() {
        return Err("余额响应为空".into());
    }
    Ok(values)
}
pub(super) fn balance_http_error(status: reqwest::StatusCode) -> (&'static str, bool) {
    match status.as_u16() {
        401 | 403 => ("余额授权失效", false),
        429 => ("余额查询受限", true),
        500..=599 => ("余额服务暂不可用", true),
        _ => ("余额接口响应异常", false),
    }
}
pub(super) fn balance_network_error(error: &reqwest::Error) -> &'static str {
    if error.is_timeout() {
        "余额查询超时"
    } else {
        "余额网络连接失败"
    }
}
async fn deepseek_balance(key: &str) -> Result<Vec<(String, String)>, (String, bool)> {
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(8))
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|_| ("余额网络组件不可用".into(), false))?;
    let response = client
        .get("https://api.deepseek.com/user/balance")
        .header(reqwest::header::ACCEPT, "application/json")
        .bearer_auth(key)
        .send()
        .await
        .map_err(|e| (balance_network_error(&e).into(), true))?;
    if !response.status().is_success() {
        let (message, transient) = balance_http_error(response.status());
        return Err((message.into(), transient));
    }
    let value = chat_search::bounded_json(response)
        .await
        .map_err(|_| ("余额响应读取失败".into(), true))?;
    parse_deepseek_balance(&value).map_err(|message| (message, false))
}
fn balance_cache_path(id: &str) -> Result<PathBuf, String> {
    let (provider, digest) = id.split_once(':').ok_or("余额缓存标识无效")?;
    if !matches!(provider, "deepseek" | "bailian")
        || digest.len() != 64
        || !digest.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err("余额缓存标识无效".into());
    }
    Ok(home("RinaDesk")?.join(format!("balance-{provider}-{digest}.json")))
}
fn cached_balance(id: &str) -> Option<Balance> {
    let value: Balance =
        serde_json::from_value(safe_read(&balance_cache_path(id).ok()?).ok()??).ok()?;
    if !value.message.is_empty()
        || value.values.is_empty()
        || value.values.len() > 3
        || !value
            .values
            .iter()
            .all(|(currency, amount)| valid_amount(currency, amount))
        || chrono::DateTime::parse_from_rfc3339(&value.updated_at).is_err()
    {
        return None;
    }
    Some(value)
}
fn save_balance(id: &str, value: &Balance) {
    let _ = (|| -> Result<(), String> {
        let path = balance_cache_path(id)?;
        no_redirect(&path)?;
        let parent = path.parent().ok_or("余额缓存路径无效")?;
        fs::create_dir_all(parent).map_err(|_| "余额缓存不可写")?;
        let temporary = parent.join(format!(
            ".balance-{}-{}.tmp",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap_or(0)
        ));
        let bytes = serde_json::to_vec(value).map_err(|_| "余额缓存无效")?;
        let result = (|| -> std::io::Result<()> {
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&temporary)?;
            file.write_all(&bytes)?;
            file.sync_all()?;
            drop(file);
            fs::rename(&temporary, &path)
        })();
        if result.is_err() {
            let _ = fs::remove_file(temporary);
            return Err("余额缓存不可写".into());
        }
        Ok(())
    })();
}
#[tauri::command]
pub async fn billing_status(
    app: tauri::AppHandle,
    force: bool,
    local_only: Option<bool>,
) -> Result<Vec<Account>, String> {
    let credentials = credentials(&app);
    let today = Local::now().date_naive();
    let day = today.format("%Y-%m-%d").to_string();
    let days: Vec<String> = (0..7)
        .rev()
        .map(|offset| {
            (today - ChronoDuration::days(offset))
                .format("%Y-%m-%d")
                .to_string()
        })
        .collect();
    let mut ledger = BTreeMap::<String, BTreeMap<String, Counter>>::new();
    let mut incomplete = false;
    for (name, override_name) in [
        ("RinaDesk", ""),
        ("RinaYaki", "RINAYAKI_CONFIG_HOME"),
        ("RinaTomo", "RINATOMO_CONFIG_HOME"),
    ] {
        let dir = if override_name.is_empty() {
            home(name)
        } else {
            tool_home(name, override_name)
        };
        match dir.and_then(|dir| daily(&dir.join("billing.json"), &day)) {
            Ok(value) => {
                for (date, accounts) in value
                    .history
                    .into_iter()
                    .chain(std::iter::once((value.day, value.accounts)))
                {
                    if !days.contains(&date) {
                        continue;
                    }
                    for (id, c) in accounts {
                        add_counter(
                            ledger
                                .entry(id)
                                .or_default()
                                .entry(date.clone())
                                .or_default(),
                            c,
                        );
                    }
                }
            }
            Err(_) => incomplete = true,
        }
    }
    let mut output = Vec::new();
    let queries: Vec<_> = credentials
        .iter()
        .cloned()
        .map(|c| {
            let local = local_only.unwrap_or(false);
            tauri::async_runtime::spawn(async move {
                if !local {
                    return balance(&c, force).await;
                }
                let slot = balance_slot(&c.id);
                let cached = slot
                    .try_lock()
                    .ok()
                    .and_then(|cache| cache.as_ref().map(|(_, b)| b.clone()));
                cached.unwrap_or(Balance {
                    values: vec![],
                    updated_at: String::new(),
                    message: "查询中…".into(),
                })
            })
        })
        .collect();
    for (c, query) in credentials.into_iter().zip(queries) {
        let b = query.await.map_err(|_| "余额查询中断")?;
        let billing_connected = c.provider == "deepseek"
            || billing_connection::credential(&c.id)
                .ok()
                .flatten()
                .is_some();
        let mut usage = ledger.remove(&c.id).unwrap_or_default();
        let today_counter = usage.get(&day).cloned().unwrap_or_default();
        let history = days
            .iter()
            .map(|date| DailyUsage {
                day: date.clone(),
                counter: usage.remove(date).unwrap_or_default(),
            })
            .collect();
        output.push(Account {
            id: c.id.clone(),
            label: label(&c.provider).into(),
            active: true,
            balance: b,
            today: today_counter,
            history,
            day: day.clone(),
            incomplete,
            billing_connected,
        });
    }
    // A key change must not make its earlier local usage disappear. Keep each
    // unmatched fingerprint separate: different keys may belong to different
    // accounts and must never be silently merged into the current credential.
    for (id, mut usage) in ledger {
        let Some(provider) = archived_provider(&id) else {
            incomplete = true;
            continue;
        };
        let today_counter = usage.get(&day).cloned().unwrap_or_default();
        let history = days
            .iter()
            .map(|date| DailyUsage {
                day: date.clone(),
                counter: usage.remove(date).unwrap_or_default(),
            })
            .collect();
        let archived_label = format!("{} · 本机记录", label(provider));
        output.push(Account {
            id,
            label: archived_label,
            active: false,
            balance: Balance {
                values: vec![],
                updated_at: String::new(),
                message: "对应 API 配置已变更".into(),
            },
            today: today_counter,
            history,
            day: day.clone(),
            incomplete,
            billing_connected: false,
        });
    }
    // Same platform can contain distinct credentials. Never silently sum their balances.
    for index in 0..output.len() {
        if output
            .iter()
            .filter(|a| a.label == output[index].label)
            .count()
            > 1
        {
            let base = output[index].label.clone();
            let positions: Vec<usize> = output
                .iter()
                .enumerate()
                .filter_map(|(i, a)| (a.label == base).then_some(i))
                .collect();
            for (n, i) in positions.into_iter().enumerate() {
                output[i].label = format!("{base} · {}", n + 1);
            }
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn account_queries_are_independent_and_concurrent_refreshes_coalesce() {
        tauri::async_runtime::block_on(async {
            let slow: BalanceSlot = Default::default();
            let fast: BalanceSlot = Default::default();
            let hold = slow.lock().await;
            let calls = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
            let mut tasks = Vec::new();
            for _ in 0..2 {
                let slot = slow.clone();
                let calls = calls.clone();
                tasks.push(tauri::async_runtime::spawn(async move {
                    query_once(&slot, true, |_| async {
                        calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                        tokio::time::sleep(Duration::from_millis(20)).await;
                        Balance {
                            values: vec![],
                            updated_at: String::new(),
                            message: "test".into(),
                        }
                    })
                    .await
                }));
            }
            tokio::time::sleep(Duration::from_millis(20)).await;
            let result = tokio::time::timeout(
                Duration::from_secs(1),
                query_once(&fast, false, |_| async {
                    Balance {
                        values: vec![],
                        updated_at: String::new(),
                        message: "fast".into(),
                    }
                }),
            )
            .await
            .unwrap();
            assert_eq!(result.message, "fast");
            assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
            drop(hold);
            for task in tasks {
                assert_eq!(task.await.unwrap().message, "test");
            }
            assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
            query_once(&slow, false, |_| async {
                panic!("fresh failure must respect retry TTL")
            })
            .await;
            query_once(&slow, true, |_| async {
                Balance {
                    values: vec![],
                    updated_at: String::new(),
                    message: "manual".into(),
                }
            })
            .await;
            assert_eq!(slow.lock().await.as_ref().unwrap().1.message, "manual");
        });
    }
    #[test]
    fn balance_response_zero_is_not_failure() {
        let zero = json!({"is_available":false,"balance_infos":[{"currency":"CNY","total_balance":"0.00"}]});
        assert_eq!(
            parse_deepseek_balance(&zero).unwrap(),
            vec![("CNY".into(), "0.00".into())]
        );
        for invalid in [
            json!({}),
            json!({"balance_infos":[]}),
            json!({"balance_infos":[{"currency":"CNY","total_balance":"NaN"}]}),
            json!({"balance_infos":[{"currency":"CNY","total_balance":null}]}),
        ] {
            assert!(parse_deepseek_balance(&invalid).is_err());
        }
    }
    #[test]
    fn balance_failure_retry_and_authentication_policy() {
        let mut b = Balance {
            values: vec![],
            updated_at: String::new(),
            message: "余额查询超时".into(),
        };
        assert_eq!(balance_ttl(&b), Duration::from_secs(30));
        b.message.clear();
        assert_eq!(balance_ttl(&b), Duration::from_secs(600));
        assert!(!balance_http_error(reqwest::StatusCode::UNAUTHORIZED).1);
        assert!(!balance_http_error(reqwest::StatusCode::FORBIDDEN).1);
        assert!(balance_http_error(reqwest::StatusCode::TOO_MANY_REQUESTS).1);
        assert!(balance_http_error(reqwest::StatusCode::SERVICE_UNAVAILABLE).1);
        for id in [
            "../secret",
            "deepseek:../secret",
            "unknown:bad",
            "bailian:invalid",
        ] {
            assert!(balance_cache_path(id).is_err());
        }
    }
    #[test]
    fn exact_hosts_only() {
        assert_eq!(provider("https://api.deepseek.com/v1"), Some("deepseek"));
        for url in [
            "http://api.deepseek.com",
            "https://api.deepseek.com.evil.test",
            "https://user@api.deepseek.com",
            "https://api.deepseek.com:8443",
        ] {
            assert!(provider(url).is_none());
        }
        assert_eq!(
            provider("https://maas.qianwenaiapi.com/compatible-mode/v1"),
            Some("qianwen")
        );
        assert_eq!(
            archived_provider(&format!("bailian:{}", "a".repeat(64))),
            Some("bailian")
        );
        assert_eq!(archived_provider("bailian:not-a-fingerprint"), None);
    }
    #[test]
    fn usage_prices_and_missing_data() {
        assert_eq!(DEEPSEEK_SEARCH_MICRO_CNY, 5_000);
        assert_eq!(
            estimate(
                "deepseek",
                "deepseek-flash",
                &json!({"prompt_tokens":100,"completion_tokens":10,"prompt_cache_hit_tokens":50})
            ),
            Some((182, 110))
        );
        assert_eq!(
            estimate(
                "bailian",
                "deepseek-v4.1-flash",
                &json!({"prompt_tokens":100,"completion_tokens":10,"prompt_cache_hit_tokens":50})
            ),
            Some((182, 110))
        );
        assert!(estimate(
            "deepseek",
            "unknown",
            &json!({"prompt_tokens":1,"completion_tokens":1})
        )
        .is_none());
        assert!(estimate(
            "deepseek",
            "deepseek-flash",
            &json!({"prompt_tokens":1,"completion_tokens":1,"prompt_cache_hit_tokens":2})
        )
        .is_none());
    }
    #[test]
    fn shared_price_examples_match() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/billing-estimates-v1.json"
        ))
        .unwrap();
        assert_eq!(fixture["schema"], 1);
        assert_eq!(fixture["currency"], "CNY");
        assert_eq!(fixture["amount_unit"], "micro-CNY");
        for case in fixture["cases"].as_array().unwrap() {
            let actual = estimate(
                case["provider"].as_str().unwrap(),
                case["model"].as_str().unwrap(),
                &case["usage"],
            )
            .unwrap();
            assert_eq!(
                actual,
                (
                    case["expected_amount_micro"].as_u64().unwrap(),
                    case["expected_tokens"].as_u64().unwrap()
                )
            );
        }
    }
    #[test]
    fn day_rollover_and_corruption() {
        let p = env::temp_dir().join(format!("billing-test-{}.json", std::process::id()));
        fs::write(
            &p,
            serde_json::to_vec(&Ledger {
                schema: 1,
                day: "2000-01-01".into(),
                accounts: BTreeMap::from([(
                    "old".into(),
                    Counter {
                        calls: 1,
                        ..Counter::default()
                    },
                )]),
                history: BTreeMap::new(),
            })
            .unwrap(),
        )
        .unwrap();
        let migrated = daily(&p, "2000-01-02").unwrap();
        assert_eq!(migrated.schema, 2);
        assert!(migrated.accounts.is_empty());
        assert_eq!(migrated.history["2000-01-01"]["old"].calls, 1);
        fs::write(&p, "broken").unwrap();
        assert!(daily(&p, "2000-01-02").is_err());
        fs::remove_file(p).unwrap();
    }
}
