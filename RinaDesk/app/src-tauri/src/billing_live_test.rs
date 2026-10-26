//! Opt-in paid smoke test. Exactly three completion requests; never retries.
//! Run only with explicit authorization and RINADESK_PAID_SMOKE=three-requests.
use super::*;

#[test]
#[ignore = "queries the configured account balance; no model invocation"]
fn read_only_balance_query() {
    tauri::async_runtime::block_on(async {
        assert_eq!(
            env::var("RINADESK_BALANCE_SMOKE").as_deref(),
            Ok("read-only")
        );
        let config = api_profiles::resolve(None).expect("configuration unavailable");
        assert_eq!(provider(&config.url), Some("deepseek"));
        let values = deepseek_balance(config.key.as_deref().expect("missing key"))
            .await
            .unwrap_or_else(|(message, _)| panic!("{message}"));
        assert!(!values.is_empty());
        println!(
            "PASS official balance endpoint, same Rust client and parser as Desk; no model request"
        );
    });
}

#[test]
#[ignore = "makes three paid requests using the active local API configuration"]
fn three_paid_requests() {
    tauri::async_runtime::block_on(async {
        assert_eq!(
            env::var("RINADESK_PAID_SMOKE").as_deref(),
            Ok("three-requests")
        );
        let config = load_llm_config(None).expect("local configuration unavailable");
        assert_eq!(provider(&config.base_url), Some("deepseek"));
        let key = config.api_key.as_deref().expect("missing key");
        let account = identity("deepseek", key);
        let path = home("RinaDesk").unwrap().join("billing.json");
        let day = Local::now().format("%Y-%m-%d").to_string();
        let before = daily(&path, &day)
            .unwrap()
            .accounts
            .remove(&account)
            .unwrap_or_default();
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(90))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .unwrap();
        let mut messages = vec![
            json!({"role":"system","content":"You are testing RinaDesk. Reply briefly in Chinese. Use only the requested tool and never request secrets."}),
        ];
        for index in 0..3 {
            if index == 0 {
                messages.push(json!({"role":"user","content":"只回复：普通对话测试通过。"}));
            }
            if index == 1 {
                messages = vec![
                    json!({"role":"system","content":"Read only the first 20 lines of desk README.md using read_project_file. Exactly one tool call."}),
                    json!({"role":"user","content":"请读取当前 Desk 的 README.md，简述项目用途。"}),
                ];
            }
            let mut payload = json!({"model":config.model,"messages":messages,"stream":true,"stream_options":{"include_usage":true},"max_tokens":512});
            if index == 1 {
                payload["tools"] = json!([project_agent::read_tool()]);
                payload["tool_choice"] =
                    json!({"type":"function","function":{"name":"read_project_file"}});
            }
            stream_chat::forced_tool_compatibility(&mut payload, &config.base_url, index > 0);
            let mut receipt = Receipt::new(&config);
            let response = client
                .post(chat_completions_endpoint(&config.base_url))
                .bearer_auth(key)
                .json(&payload)
                .send()
                .await
                .expect("request failed");
            assert!(
                response.status().is_success(),
                "request {} HTTP {}",
                index + 1,
                response.status().as_u16()
            );
            receipt.accepted();
            let mut stream = response.bytes_stream();
            let mut decoder = sse::SseDecoder::default();
            let mut content = String::new();
            while let Some(chunk) = stream.next().await {
                content.push_str(
                    &decoder
                        .push(&chunk.expect("stream interrupted"))
                        .expect("invalid SSE")
                        .concat(),
                );
                receipt.usage = decoder.usage.clone();
                if decoder.terminated {
                    break;
                }
            }
            content.push_str(&decoder.end().expect("incomplete stream").concat());
            receipt.usage = decoder.usage.clone();
            assert!(
                decoder.usage.is_some(),
                "missing usage for request {}",
                index + 1
            );
            drop(receipt);
            if index == 1 {
                let calls = decoder.calls().unwrap();
                assert_eq!(calls.len(), 1);
                assert_eq!(calls[0]["function"]["name"], "read_project_file");
                let arguments = calls[0]["function"]["arguments"].as_str().unwrap();
                let args: Value = serde_json::from_str(arguments).unwrap();
                assert_eq!(args["project"], "desk");
                assert_eq!(args["path"], "README.md");
                // Synthetic reference only: paid smoke tests never transmit local files.
                // Actual filesystem confinement is exercised by local regression tests.
                let result = json!({"project":"desk","path":"README.md","content":"RinaDesk is a desktop pet with Chat and project help. This is synthetic test documentation, not a local project file."});
                let mut assistant =
                    json!({"role":"assistant","content":content,"tool_calls":calls});
                if !decoder.reasoning.is_empty() {
                    assistant["reasoning_content"] = json!(decoder.reasoning);
                }
                messages.push(assistant);
                messages.push(json!({"role":"tool","tool_call_id":calls[0]["id"],"content":result.to_string()}));
            } else {
                assert!(!content.trim().is_empty());
            }
            println!(
                "request {}: successful SSE, usage received, ledger recorded",
                index + 1
            );
        }
        let after = daily(&path, &day)
            .unwrap()
            .accounts
            .remove(&account)
            .unwrap();
        assert_eq!(after.calls - before.calls, 3);
        assert_eq!(after.unknown, before.unknown);
        assert!(after.tokens > before.tokens);
        assert!(after.amount_micro > before.amount_micro);
        println!("verified: 3 paid requests; estimated CNY {:.6}; tokens {}; synthetic-reference tool roundtrip completed",(after.amount_micro-before.amount_micro) as f64/1_000_000.,after.tokens-before.tokens);
    });
}
