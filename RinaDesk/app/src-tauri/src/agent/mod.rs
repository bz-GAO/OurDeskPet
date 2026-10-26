//! 封闭的 agent 工具注册表。工具在编译期登记，模型只能从本集合选择；
//! 永不从文档、插件或模型输出动态加载（与 runtime_skills 的纪律一致）。
//! 增量 1 仅只读工具；分级权限、确认式动作与长任务卡片见 docs/AGENT-TOOLS.md。
//!
//! 注意：yaki_status 走 `extension_tools::diagnostic` 而非 `extension_status`——
//! 后者在当前工具链下会让测试二进制以 STATUS_ENTRYPOINT_NOT_FOUND 启动失败
//! （2026-10-24 两次二分定位；原因未深究，改路径即规避）。

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

pub mod proposals;

/// 只读工具：无参数、无副作用、不产生费用。handler 全部同步且快速返回
/// （最长一次本机回环请求 + 读本地文件）。
struct AgentTool {
    name: &'static str,
    description: &'static str,
    handler: fn(&AppHandle) -> Result<Value, String>,
}

const TOOLS: &[AgentTool] = &[
    AgentTool {
        name: "desk_diagnostics",
        description: "Read RinaDesk's own runtime status: app version, build time, config path, and the registered Yaki/Tomo extension diagnostics. No arguments. Use when the user asks whether Desk or its extensions are set up correctly.",
        handler: |app| {
            serde_json::to_value(crate::diagnostics::collect(app))
                .map_err(|_| "诊断信息序列化失败".into())
        },
    },
    AgentTool {
        name: "tomo_status",
        description: "Read RinaTomo (QQ bot) live status over the local control protocol: running state, login state, feature and LLM usage snapshot. Returns an offline snapshot when the Tomo controller is not running. No arguments.",
        handler: |_app| Ok(crate::rinatomo::rinatomo_status()),
    },
    AgentTool {
        name: "yaki_status",
        description: "Read the RinaYaki extension registration status: connected, available, registered path and version. No arguments.",
        handler: |app| {
            let status = crate::extension_tools::diagnostic(app)?;
            Ok(json!({
                "connected": status.connected,
                "available": status.available,
                "path": status.path,
                "version": status.version,
            }))
        },
    },
];

/// OpenAI function-tool schema 数组，按轮注入对话请求。
/// `suggest_project_mode` 仅日常聊天模式注入（项目模式本身具备全部能力）。
pub fn tools(project_mode: bool) -> Vec<Value> {
    let mut all: Vec<Value> = TOOLS
        .iter()
        .map(|tool| {
            json!({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": false,
                    },
                },
            })
        })
        .collect();
    all.push(json!({
        "type": "function",
        "function": {
            "name": "yaki_start_translation",
            "description": "Propose a RinaYaki video translation job for a web video URL (YouTube/Bilibili). This NEVER starts downloading or paid work by itself: it creates a task card in the chat that the user must confirm twice (once to fetch video info, once before the paid download/transcribe/translate chain starts). Use when the user asks to translate or subtitle a video from a link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The http/https web video URL to translate."
                    }
                },
                "required": ["url"],
                "additionalProperties": false,
            },
        },
    }));
    if !project_mode {
        all.push(json!({
            "type": "function",
            "function": {
                "name": "suggest_project_mode",
                "description": "Zero-side-effect signal: tell the app the user's request belongs to project-assistant mode (project source reading, engineering operations, or Desk settings changes like contextChars/searchMode/startupEnabled). Call it once and briefly tell the user they can jump. Never claim the work was done.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": false,
                },
            },
        }));
    }
    all
}

pub fn is_agent_tool(name: &str) -> bool {
    TOOLS.iter().any(|tool| tool.name == name)
        || name == "yaki_start_translation"
        || name == "suggest_project_mode"
}

/// 只读工具一律无参数；拒绝任何非空参数，防止模型往参数里夹带内容。
fn validate_arguments(name: &str, arguments: &str) -> Result<(), String> {
    let parsed: Value = if arguments.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(arguments).map_err(|_| "工具参数不是有效 JSON。".to_string())?
    };
    if parsed != json!({}) {
        return Err(format!("{name} 不接受参数。"));
    }
    Ok(())
}

/// 执行一个注册表内的工具并向前端推送 llm-chat-tool 事件（芯片渲染用）。
/// 返回值直接作为 role:"tool" 消息内容回填给模型。
pub async fn dispatch(app: &AppHandle, request_id: &str, name: &str, arguments: &str) -> Value {
    if !is_agent_tool(name) {
        return json!({"error": "Unsupported tool."});
    }
    let emit = |state: &str, detail: &str| {
        let _ = app.emit(
            "llm-chat-tool",
            json!({"requestId": request_id, "name": name, "state": state, "detail": detail}),
        );
    };
    if name == "suggest_project_mode" {
        // 零副作用信号：仅通知前端出"跳转项目助手"卡片。
        emit("done", "已建议切换项目助手");
        let _ = app.emit("agent-suggest-project", json!({"requestId": request_id}));
        return json!({
            "status": "suggested",
            "detail": "已向用户展示跳转项目助手模式的卡片。不要声称已经完成任何项目操作；等用户跳转后在新模式中重新提出请求。",
        });
    }
    if name == "yaki_start_translation" {
        emit("running", "创建翻译提案");
        let parsed: Result<Value, _> = if arguments.trim().is_empty() {
            Err(())
        } else {
            serde_json::from_str(arguments).map_err(|_| ())
        };
        let outcome = match parsed
            .ok()
            .and_then(|value| value.get("url").and_then(Value::as_str).map(str::to_string))
        {
            Some(url) => proposals::register(app, request_id, &url),
            None => json!({"error": "请通过 url 参数提供视频链接。"}),
        };
        if outcome.get("error").is_some() {
            emit("error", "提案创建失败");
        } else {
            emit("done", "已创建提案，等待确认");
        }
        return outcome;
    }
    if let Err(error) = validate_arguments(name, arguments) {
        emit("error", &error);
        return json!({"error": error});
    }
    let Some(tool) = TOOLS.iter().find(|tool| tool.name == name) else {
        return json!({"error": "Unsupported tool."});
    };
    emit("running", "调用中");
    let handler = tool.handler;
    let worker_app = app.clone();
    let result = tauri::async_runtime::spawn_blocking(move || (handler)(&worker_app)).await;
    match result {
        Err(_) => {
            let error = "状态工具运行线程意外退出。".to_string();
            emit("error", &error);
            json!({"error": error})
        }
        Ok(Ok(value)) => {
            emit("done", "完成");
            json!({"result": value})
        }
        Ok(Err(error)) => {
            emit("error", &error);
            json!({"error": error})
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_is_closed_and_schemas_are_valid() {
        let chat_schemas = tools(false);
        let names: Vec<&str> = chat_schemas
            .iter()
            .map(|tool| tool["function"]["name"].as_str().unwrap())
            .collect();
        assert_eq!(
            names,
            [
                "desk_diagnostics",
                "tomo_status",
                "yaki_status",
                "yaki_start_translation",
                "suggest_project_mode"
            ]
        );
        for tool in &chat_schemas {
            assert!(tool["function"]["description"].as_str().unwrap().len() > 20);
            assert_eq!(tool["function"]["parameters"]["type"], "object");
            assert_eq!(
                tool["function"]["parameters"]["additionalProperties"],
                false
            );
        }
        // 项目模式：翻译提案在、模式跳转不在（项目模式本身即目标）。
        let project_schemas = tools(true);
        let project_names: Vec<&str> = project_schemas
            .iter()
            .map(|tool| tool["function"]["name"].as_str().unwrap())
            .collect();
        assert!(project_names.contains(&"yaki_start_translation"));
        assert!(!project_names.contains(&"suggest_project_mode"));
        let translation = chat_schemas
            .iter()
            .find(|tool| tool["function"]["name"] == "yaki_start_translation")
            .unwrap();
        assert_eq!(translation["function"]["parameters"]["required"][0], "url");
        assert_eq!(
            translation["function"]["parameters"]["additionalProperties"],
            false
        );
        assert!(is_agent_tool("tomo_status"));
        assert!(is_agent_tool("suggest_project_mode"));
        assert!(!is_agent_tool("web_search"));
        assert!(!is_agent_tool("run_command"));
    }

    #[test]
    fn read_only_tools_reject_any_arguments() {
        assert!(validate_arguments("tomo_status", "").is_ok());
        assert!(validate_arguments("tomo_status", "{}").is_ok());
        assert!(validate_arguments("tomo_status", "  {}  ").is_ok());
        assert!(validate_arguments("tomo_status", r#"{"path":"/etc"}"#).is_err());
        assert!(validate_arguments("yaki_status", "not json").is_err());
        assert!(validate_arguments("desk_diagnostics", r#"{"query":"x"}"#).is_err());
    }
}
