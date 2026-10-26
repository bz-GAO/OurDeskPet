//! Optional read-only Alibaba billing authorization, protected by Windows DPAPI.
use super::*;
use hmac::{Hmac, Mac};
use sha1::Sha1;
use std::collections::BTreeMap;

static WRITE: Mutex<()> = Mutex::new(());
#[derive(Clone, Default, PartialEq, Serialize, Deserialize)]
pub(crate) struct Credential {
    pub id: String,
    pub secret: String,
}
#[derive(Default, PartialEq, Serialize, Deserialize)]
struct Connections {
    accounts: BTreeMap<String, Credential>,
}
#[cfg(windows)]
fn protect(bytes: &[u8], encrypt: bool) -> Result<Vec<u8>, String> {
    #[repr(C)]
    struct Blob {
        len: u32,
        data: *mut u8,
    }
    #[link(name = "crypt32")]
    extern "system" {
        fn CryptProtectData(
            input: *const Blob,
            description: *const u16,
            entropy: *const Blob,
            reserved: *mut std::ffi::c_void,
            prompt: *mut std::ffi::c_void,
            flags: u32,
            output: *mut Blob,
        ) -> i32;
        fn CryptUnprotectData(
            input: *const Blob,
            description: *mut *mut u16,
            entropy: *const Blob,
            reserved: *mut std::ffi::c_void,
            prompt: *mut std::ffi::c_void,
            flags: u32,
            output: *mut Blob,
        ) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(memory: *mut std::ffi::c_void) -> *mut std::ffi::c_void;
    }
    if bytes.len() > 128 * 1024 {
        return Err("账务配置过大".into());
    }
    let input = Blob {
        len: bytes.len() as u32,
        data: bytes.as_ptr() as *mut u8,
    };
    let mut output = Blob {
        len: 0,
        data: std::ptr::null_mut(),
    };
    let success = unsafe {
        if encrypt {
            CryptProtectData(
                &input,
                std::ptr::null(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                1,
                &mut output,
            )
        } else {
            CryptUnprotectData(
                &input,
                std::ptr::null_mut(),
                std::ptr::null(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                1,
                &mut output,
            )
        }
    };
    if success == 0 {
        return Err("账务授权无法加密或读取，请重新连接".into());
    }
    let value = unsafe { std::slice::from_raw_parts(output.data, output.len as usize).to_vec() };
    unsafe {
        LocalFree(output.data.cast());
    }
    Ok(value)
}
#[cfg(not(windows))]
fn protect(_bytes: &[u8], _encrypt: bool) -> Result<Vec<u8>, String> {
    Err("账务授权暂仅支持 Windows".into())
}
fn path() -> Result<PathBuf, String> {
    Ok(billing::home("RinaDesk")?.join("billing-credentials.bin"))
}
fn read() -> Result<Connections, String> {
    read_at(&path()?)
}
fn read_at(path: &Path) -> Result<Connections, String> {
    billing::no_redirect(path)?;
    match fs::File::open(&path) {
        Ok(file) => {
            use std::io::Read;
            let mut v = Vec::new();
            file.take(128 * 1024 + 1)
                .read_to_end(&mut v)
                .map_err(|_| "账务授权不可用")?;
            if v.len() > 128 * 1024 {
                return Err("账务授权文件过大".into());
            }
            serde_json::from_slice(&protect(&v, false)?)
                .map_err(|_| "账务授权损坏，请重新连接".into())
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Connections::default()),
        Err(_) => Err("账务授权不可用".into()),
    }
}
fn credential_from(
    mut connections: Connections,
    account: &str,
) -> Result<Option<Credential>, String> {
    if let Some(value) = connections.accounts.remove(account) {
        return Ok(Some(value));
    }
    if !connections.accounts.is_empty() {
        return Err("当前 API 密钥未关联账务授权".into());
    }
    Ok(None)
}
pub(crate) fn credential(account: &str) -> Result<Option<Credential>, String> {
    credential_from(read()?, account)
}
#[tauri::command]
pub fn billing_connection_save(
    window: tauri::Window,
    account: String,
    id: String,
    secret: String,
    clear: bool,
) -> Result<(), String> {
    if window.label() != "settings" {
        return Err("请在设置中连接账务".into());
    }
    if !billing::known_bailian_account(window.app_handle(), &account) {
        return Err("账务账户已变化，请刷新后重新连接".into());
    }
    let _guard = WRITE.lock().map_err(|_| "账务配置正在处理")?;
    let mut connections = read()?;
    if clear {
        connections.accounts.remove(&account);
    } else {
        let id = id.trim();
        let secret = secret.trim();
        if id.is_empty()
            || secret.is_empty()
            || id.len() > 256
            || secret.len() > 512
            || !id.bytes().all(|b| b.is_ascii_alphanumeric())
            || !secret.bytes().all(|b| b.is_ascii_graphic())
        {
            return Err("请填写有效的账务 AccessKey ID 和 Secret".into());
        }
        connections.accounts.insert(
            account,
            Credential {
                id: id.into(),
                secret: secret.into(),
            },
        );
    }
    save_at(&path()?, &connections)?;
    billing::clear_balance_cache();
    let _ = window.app_handle().emit("deskpet-billing-updated", ());
    Ok(())
}
fn save_at(path: &Path, connections: &Connections) -> Result<(), String> {
    let bytes = protect(
        &serde_json::to_vec(connections).map_err(|_| "账务配置无效")?,
        true,
    )?;
    billing::no_redirect(path)?;
    let parent = path.parent().ok_or("账务路径无效")?;
    fs::create_dir_all(parent).map_err(|_| "无法创建账务目录")?;
    let temporary = parent.join(format!(
        ".billing-auth-{}-{}.tmp",
        std::process::id(),
        chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0)
    ));
    let result = (|| -> std::io::Result<()> {
        use std::io::Write;
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
        let _ = fs::remove_file(&temporary);
        return Err("账务授权保存失败".into());
    }
    if read_at(path)? != *connections {
        return Err("账务授权保存校验失败，请重试".into());
    }
    Ok(())
}
fn encode(value: &str) -> String {
    let mut result = String::new();
    for b in value.bytes() {
        if b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b'~') {
            result.push(b as char);
        } else {
            result.push_str(&format!("%{b:02X}"));
        }
    }
    result
}
fn signed_query(credential: &Credential, timestamp: &str, nonce: &str) -> Result<String, String> {
    let params = BTreeMap::from([
        ("AccessKeyId", credential.id.as_str()),
        ("Action", "QueryAccountBalance"),
        ("Format", "JSON"),
        ("SignatureMethod", "HMAC-SHA1"),
        ("SignatureNonce", nonce),
        ("SignatureVersion", "1.0"),
        ("Timestamp", timestamp),
        ("Version", "2017-12-14"),
    ]);
    let canonical = params
        .iter()
        .map(|(k, v)| format!("{}={}", encode(k), encode(v)))
        .collect::<Vec<_>>()
        .join("&");
    let mut mac = Hmac::<Sha1>::new_from_slice(format!("{}&", credential.secret).as_bytes())
        .map_err(|_| "账务签名失败")?;
    mac.update(format!("GET&%2F&{}", encode(&canonical)).as_bytes());
    Ok(format!(
        "{canonical}&Signature={}",
        encode(&BASE64_STANDARD.encode(mac.finalize().into_bytes()))
    ))
}
pub(crate) async fn balance(account: &str) -> Result<Vec<(String, String)>, String> {
    let credential = credential(account)?.ok_or("余额查询未连接")?;
    let now = chrono::Utc::now();
    let timestamp = now.format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let nonce = format!(
        "{}-{}",
        std::process::id(),
        now.timestamp_nanos_opt().unwrap_or(0)
    );
    let query = signed_query(&credential, &timestamp, &nonce)?;
    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(8))
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|_| "账务查询不可用")?;
    let response = client
        .get(format!("https://business.aliyuncs.com/?{query}"))
        .send()
        .await
        .map_err(|e| billing::balance_network_error(&e))?;
    if !response.status().is_success() {
        return Err(billing::balance_http_error(response.status()).0.into());
    }
    let value = chat_search::bounded_json(response)
        .await
        .map_err(|_| "余额服务暂不可用")?;
    parse_balance(&value)
}
fn parse_balance(value: &Value) -> Result<Vec<(String, String)>, String> {
    if value.get("Success").and_then(Value::as_bool) != Some(true)
        || !matches!(
            value.get("Code").and_then(Value::as_str),
            Some("200" | "Success")
        )
    {
        return Err("账务授权不可用，请检查只读权限".into());
    }
    let currency = value
        .pointer("/Data/Currency")
        .and_then(Value::as_str)
        .ok_or("余额币种不可用")?;
    let amount = value
        .pointer("/Data/AvailableAmount")
        .and_then(Value::as_str)
        .ok_or("余额暂不可用")?
        .replace(',', "");
    if !matches!(currency, "CNY" | "USD" | "JPY")
        || amount.len() > 32
        || amount.parse::<f64>().ok().is_none_or(|n| !n.is_finite())
    {
        return Err("余额结果无效".into());
    }
    Ok(vec![(currency.into(), amount)])
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn authorization_is_never_rebound_to_another_model_key() {
        assert!(credential_from(Connections::default(), "bailian:new")
            .unwrap()
            .is_none());
        let mut saved = Connections::default();
        saved.accounts.insert(
            "bailian:original".into(),
            Credential {
                id: "fakeid".into(),
                secret: "fake-secret".into(),
            },
        );
        assert_eq!(
            credential_from(saved, "bailian:new").err().as_deref(),
            Some("当前 API 密钥未关联账务授权")
        );
    }
    #[test]
    #[ignore = "reads existing authorization and queries the official balance API; no model request"]
    fn read_only_saved_balance_query() {
        tauri::async_runtime::block_on(async {
            use sha2::{Digest, Sha256};
            assert_eq!(
                env::var("RINADESK_BALANCE_SMOKE").as_deref(),
                Ok("read-only")
            );
            let config = PathBuf::from(
                env::var_os("RINADESK_BAILIAN_TEST_ENV")
                    .expect("explicit configuration path required"),
            );
            assert!(config.is_absolute());
            let values = api_profiles::parse(
                &api_profiles::read(&config).expect("configuration unreadable"),
            )
            .expect("invalid configuration");
            let key = values
                .get("DASHSCOPE_API_KEY")
                .expect("model key not configured");
            let account = format!(
                "bailian:{:x}",
                Sha256::digest(format!("bailian\n{}", key.trim()).as_bytes())
            );
            assert!(
                credential(&account)
                    .expect("authorization unavailable")
                    .is_some(),
                "matching authorization not saved"
            );
            let values = balance(&account)
                .await
                .unwrap_or_else(|message| panic!("{message}"));
            assert!(!values.is_empty());
            println!("PASS persisted authorization matches configuration and official balance query succeeds; no credentials, amounts or model requests logged");
        });
    }
    #[cfg(windows)]
    #[test]
    fn saved_authorization_survives_fresh_reads_and_replacement() {
        const KEY: &str = "RINADESK_TEST_RESTART_AUTH";
        if let Some(path) = env::var_os(KEY) {
            let value = read_at(Path::new(&path)).unwrap();
            assert_eq!(value.accounts["bailian:test"].secret, "replacement-secret");
            return;
        }
        let path = env::temp_dir().join(format!(
            "billing-auth-test-{}-{}.bin",
            std::process::id(),
            chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0)
        ));
        let mut connections = Connections::default();
        connections.accounts.insert(
            "bailian:test".into(),
            Credential {
                id: "fakeid".into(),
                secret: "fake-secret".into(),
            },
        );
        save_at(&path, &connections).unwrap();
        assert!(read_at(&path).unwrap() == connections);
        connections.accounts.get_mut("bailian:test").unwrap().secret = "replacement-secret".into();
        save_at(&path, &connections).unwrap();
        assert!(read_at(&path).unwrap() == connections);
        let bytes = fs::read(&path).unwrap();
        assert!(!bytes
            .windows(b"replacement-secret".len())
            .any(|part| part == b"replacement-secret"));
        let mut command = std::process::Command::new(env::current_exe().unwrap());
        command.args(["--exact","billing_connection::tests::saved_authorization_survives_fresh_reads_and_replacement"]).env(KEY,&path).current_dir(env::temp_dir());
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        assert!(
            command.output().unwrap().status.success(),
            "fresh process cannot decrypt saved synthetic authorization"
        );
        connections.accounts.clear();
        save_at(&path, &connections).unwrap();
        assert!(read_at(&path).unwrap().accounts.is_empty());
        fs::remove_file(path).unwrap();
    }
    #[test]
    fn signature_is_encoded_and_closed_to_balance_only() {
        let c = Credential {
            id: "testid".into(),
            secret: "testsecret".into(),
        };
        let query = signed_query(&c, "2026-10-13T00:00:00Z", "fixed").unwrap();
        assert!(query.contains("Action=QueryAccountBalance"));
        assert!(query.contains("Timestamp=2026-10-13T00%3A00%3A00Z"));
        assert!(!query.contains("testsecret"));
        assert!(query.ends_with("Signature=Ocf2cM3T56r36%2BktM3eNS1uecdU%3D"));
        assert_eq!(encode("a +/&"), "a%20%2B%2F%26");
    }
    #[cfg(windows)]
    #[test]
    fn authorization_is_encrypted_for_current_user() {
        let secret = b"fake-private-test-credential";
        let encrypted = protect(secret, true).unwrap();
        assert!(!encrypted.windows(secret.len()).any(|w| w == secret));
        assert_eq!(protect(&encrypted, false).unwrap(), secret);
    }
    #[test]
    fn official_balance_response_and_rejected_authorization() {
        assert_eq!(parse_balance(&json!({"Code":"200","Success":true,"Data":{"Currency":"CNY","AvailableAmount":"1,234.56"}})).unwrap(),vec![("CNY".into(),"1234.56".into())]);
        assert!(parse_balance(
            &json!({"Code":"200","Success":false,"Data":{"Currency":"CNY","AvailableAmount":"0"}})
        )
        .is_err());
    }
}
