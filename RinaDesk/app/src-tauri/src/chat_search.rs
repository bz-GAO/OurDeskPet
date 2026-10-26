use futures_util::StreamExt;
use serde_json::{json, Value};
use std::{collections::HashSet, time::Duration};
use tauri::Emitter;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Backend {
    DeepSeek,
    Tavily,
}

fn plan(config: &super::LlmConfig) -> Vec<Backend> {
    if !config.search_enabled {
        return Vec::new();
    }
    let mut backends = Vec::new();
    if super::billing::provider(&config.base_url) == Some("deepseek")
        && config
            .api_key
            .as_deref()
            .is_some_and(|key| !key.trim().is_empty())
    {
        backends.push(Backend::DeepSeek);
    }
    if config
        .tavily_key
        .as_deref()
        .is_some_and(|key| !key.trim().is_empty())
    {
        backends.push(Backend::Tavily);
    }
    backends
}

pub fn available(config: &super::LlmConfig) -> bool {
    !plan(config).is_empty()
}
pub fn label(config: &super::LlmConfig) -> &'static str {
    match plan(config).as_slice() {
        [Backend::DeepSeek, Backend::Tavily] => "DeepSeek · Tavily 备用",
        [Backend::DeepSeek] => "DeepSeek",
        [Backend::Tavily] => "Tavily",
        _ => "未配置",
    }
}

pub fn tool() -> Value {
    json!({"type":"function","function":{"name":"web_search","description":"Search the web for recent or uncertain factual information. Returns source titles, URLs and excerpts.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Concise search query, at most 128 Unicode characters"}},"required":["query"],"additionalProperties":false}}})
}

pub fn query(arguments: &str) -> Result<String, String> {
    let value: Value = serde_json::from_str(arguments).map_err(|_| "Invalid search arguments.")?;
    let query = value
        .get("query")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if query.is_empty() || query.chars().count() > 128 {
        return Err("Search query must contain 1–128 characters.".into());
    }
    Ok(query.to_string())
}

pub fn phase(window: &tauri::Window, id: &str, phase: &str, detail: &str) {
    let _ = window.emit(
        "llm-chat-phase",
        json!({"requestId":id,"phase":phase,"detail":detail}),
    );
}

pub async fn bounded_json(response: reqwest::Response) -> Result<Value, String> {
    let mut bytes = Vec::new();
    let mut stream = response.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|_| "Response body could not be read.")?;
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err("Response exceeded the size limit.".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| "Response is not valid JSON.".into())
}

pub fn results(value: &Value) -> Result<Vec<Value>, String> {
    let items = value
        .get("results")
        .and_then(Value::as_array)
        .ok_or("Search returned an invalid result list.")?;
    let mut seen = HashSet::new();
    Ok(items
        .iter()
        .filter_map(|v| {
            let url = v.get("url")?.as_str()?;
            if url.len() > 8192 || !seen.insert(url.to_string()) {
                return None;
            }
            let parsed = reqwest::Url::parse(url).ok()?;
            if !matches!(parsed.scheme(), "http" | "https")
                || !parsed.username().is_empty()
                || parsed.password().is_some()
            {
                return None;
            }
            let title = v
                .get("title")
                .and_then(Value::as_str)
                .filter(|s| !s.trim().is_empty())
                .unwrap_or("Source");
            let content = ["content", "summary", "snippet"]
                .iter()
                .find_map(|key| {
                    v.get(*key)
                        .and_then(Value::as_str)
                        .filter(|s| !s.trim().is_empty())
                })
                .unwrap_or("");
            Some(
                json!({"title":title.chars().take(180).collect::<String>(),"url":url,
            "content":content.chars().take(1200).collect::<String>()}),
            )
        })
        .take(5)
        .collect())
}

pub async fn search(config: &super::LlmConfig, query: &str) -> Result<Vec<Value>, String> {
    if query.trim().is_empty() || query.chars().count() > 128 {
        return Err("Search query must contain 1–128 characters.".into());
    }
    tokio::time::timeout(Duration::from_secs(30), search_backends(config, query))
        .await
        .map_err(|_| "搜索总等待时间已到，未再次请求。".to_string())?
}

async fn search_backends(config: &super::LlmConfig, query: &str) -> Result<Vec<Value>, String> {
    let backends = plan(config);
    if backends.is_empty() {
        return Err("搜索服务未配置。".into());
    }
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(8))
        .timeout(Duration::from_secs(29))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "无法初始化搜索服务。")?;
    let mut errors = Vec::new();
    let mut empty = false;
    let multiple = backends.len() > 1;
    for (index, backend) in backends.into_iter().enumerate() {
        // Leave a bounded window for the fallback instead of allowing the
        // primary request to consume the entire 30-second turn budget.
        let seconds = if !multiple {
            28
        } else if index == 0 {
            18
        } else {
            10
        };
        let call = async {
            match backend {
                Backend::DeepSeek => deepseek(&client, config, query).await,
                Backend::Tavily => tavily(&client, config, query).await,
            }
        };
        let result = tokio::time::timeout(Duration::from_secs(seconds), call)
            .await
            .unwrap_or_else(|_| {
                Err(match backend {
                    Backend::DeepSeek => "DeepSeek 搜索超时。",
                    Backend::Tavily => "Tavily 搜索超时。",
                }
                .into())
            });
        match result {
            Ok(items) if !items.is_empty() => return Ok(items),
            Ok(_) => empty = true,
            Err(error) => errors.push(error),
        }
    }
    if empty && errors.is_empty() {
        return Ok(Vec::new());
    }
    if empty {
        errors.insert(0, "首选搜索没有结果".into());
    }
    Err(errors.join("；"))
}

async fn deepseek(
    client: &reqwest::Client,
    config: &super::LlmConfig,
    query: &str,
) -> Result<Vec<Value>, String> {
    let key = config
        .api_key
        .as_deref()
        .filter(|key| !key.trim().is_empty())
        .ok_or("DeepSeek 搜索密钥不可用。")?;
    let response = client
        .post("https://api.deepseek.com/v1/tools/search")
        .bearer_auth(key)
        .json(&json!({"query":query,"count":5,"need_content":true}))
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "DeepSeek 搜索超时。"
            } else {
                "DeepSeek 搜索连接失败。"
            }
            .to_string()
        })?;
    if !response.status().is_success() {
        return Err(format!(
            "DeepSeek 搜索返回 HTTP {}。",
            response.status().as_u16()
        ));
    }
    let value = bounded_json(response).await?;
    // DeepSeek charges a successful response with a non-empty server result
    // list even if every item is later rejected by our URL/content filters.
    if server_has_results(&value) {
        super::billing::record_search(config);
    }
    let items = results(&value)?;
    Ok(items)
}

fn server_has_results(value: &Value) -> bool {
    value
        .get("results")
        .and_then(Value::as_array)
        .is_some_and(|items| !items.is_empty())
}

async fn tavily(
    client: &reqwest::Client,
    config: &super::LlmConfig,
    query: &str,
) -> Result<Vec<Value>, String> {
    let key = config
        .tavily_key
        .as_deref()
        .ok_or("Tavily key is not configured.")?;
    let url = format!("{}/search", config.tavily_url.trim_end_matches('/'));
    let parsed = reqwest::Url::parse(&url).map_err(|_| "Invalid Tavily base URL.")?;
    if !parsed.username().is_empty()
        || parsed.password().is_some()
        || !(parsed.scheme() == "https"
            || (parsed.scheme() == "http"
                && matches!(parsed.host_str(), Some("127.0.0.1" | "localhost"))))
    {
        return Err("Tavily requires HTTPS (HTTP is permitted only for localhost tests).".into());
    }
    let response=client.post(parsed).bearer_auth(key).json(&json!({"query":query,"search_depth":"basic","max_results":5,
        "include_answer":false,"include_raw_content":false,"include_images":false,"auto_parameters":false}))
        .send().await.map_err(|e|if e.is_timeout(){"Tavily 搜索超时。"}else{"Tavily 搜索连接失败。"}.to_string())?;
    if !response.status().is_success() {
        return Err(format!(
            "Tavily returned HTTP {}. Check the key, quota or connection.",
            response.status().as_u16()
        ));
    }
    results(&bounded_json(response).await?)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_invalid_queries() {
        assert!(query("{}").is_err());
        assert!(query("bad").is_err());
        assert!(query(&json!({"query":"a".repeat(129)}).to_string()).is_err());
        assert_eq!(query("{\"query\":\" 天气 \"}").unwrap(), "天气");
    }
    #[test]
    fn bounds_untrusted_results() {
        let v = json!({"results":[{"url":"javascript:alert(1)"},{"url":"https://user:secret@example.com"},{"url":"https://example.com","title":"Source","summary":"a".repeat(2000)},{"url":"https://example.com","content":"duplicate"}]});
        let r = results(&v).unwrap();
        assert_eq!(r.len(), 1);
        assert_eq!(r[0]["content"].as_str().unwrap().len(), 1200);
    }
    #[test]
    fn server_billing_signal_precedes_local_filtering() {
        assert!(server_has_results(
            &json!({"results":[{"url":"javascript:bad"}]})
        ));
        assert!(!server_has_results(&json!({"results":[]})));
    }
    #[test]
    fn selects_deepseek_then_optional_fallback() {
        let mut config = super::super::LlmConfig {
            api_key: Some("x".into()),
            base_url: "https://api.deepseek.com".into(),
            model: Some("deepseek-flash".into()),
            model_options: Vec::new(),
            system_prompt: String::new(),
            prompt_source: String::new(),
            tavily_key: None,
            tavily_url: "https://api.tavily.com".into(),
            search_enabled: true,
            context_chars: 12000,
            read_timeout_secs: 180,
            options: super::super::chat_settings::Options::default(),
        };
        assert_eq!(plan(&config), vec![Backend::DeepSeek]);
        assert!(available(&config));
        config.tavily_key = Some("t".into());
        assert_eq!(plan(&config), vec![Backend::DeepSeek, Backend::Tavily]);
        config.base_url = "https://example.com/v1".into();
        assert_eq!(plan(&config), vec![Backend::Tavily]);
        config.search_enabled = false;
        assert!(plan(&config).is_empty());
    }
}
