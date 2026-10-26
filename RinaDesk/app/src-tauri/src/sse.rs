use serde_json::Value;

const DSML_CALLS: [&str; 2] = ["<｜DSML｜calls>", "<|DSML|calls>"];

// Some OpenAI-compatible DeepSeek deployments expose the model's native DSML
// text instead of converting it into tool_calls. Hold only a possible leading
// marker; ordinary text resumes streaming as soon as it cannot match.
pub struct ToolTextGuard {
    pending: String,
    markup: bool,
    visible: bool,
}
impl ToolTextGuard {
    pub fn new(enabled: bool) -> Self {
        Self {
            pending: String::new(),
            markup: false,
            visible: !enabled,
        }
    }
    pub fn push(&mut self, delta: &str) -> Option<String> {
        if self.visible {
            return (!delta.is_empty()).then(|| delta.to_string());
        }
        self.pending.push_str(delta);
        let trimmed = self.pending.trim_start();
        if DSML_CALLS.iter().any(|marker| trimmed.starts_with(marker)) {
            self.markup = true;
            return None;
        }
        if DSML_CALLS.iter().any(|marker| marker.starts_with(trimmed)) {
            return None;
        }
        self.visible = true;
        Some(std::mem::take(&mut self.pending))
    }
    pub fn finish(&mut self) -> Option<String> {
        if self.visible || self.markup || self.pending.is_empty() {
            None
        } else {
            self.visible = true;
            Some(std::mem::take(&mut self.pending))
        }
    }
    pub fn is_markup(&self) -> bool {
        self.markup
    }
}

fn attr(tag: &str, name: &str) -> Result<String, String> {
    let needle = format!(r#"{name}=""#);
    let start = tag.find(&needle).ok_or("DSML tool attribute is missing.")? + needle.len();
    let end = tag[start..]
        .find('"')
        .ok_or("DSML tool attribute is invalid.")?
        + start;
    let value = &tag[start..end];
    if value.is_empty()
        || !value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return Err("DSML tool attribute is invalid.".into());
    }
    Ok(value.into())
}
fn unescape(value: &str) -> String {
    value
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
}

pub fn parse_dsml_calls(text: &str) -> Result<Option<Vec<Value>>, String> {
    let normalized = text.trim().replace('｜', "|");
    let Some(mut rest) = normalized.strip_prefix("<|DSML|calls>") else {
        return Ok(None);
    };
    if normalized.len() > 65_536 {
        return Err("DSML tool call exceeded the size limit.".into());
    }
    let mut calls = Vec::new();
    loop {
        rest = rest.trim_start();
        if let Some(tail) = rest.strip_prefix("</|DSML|calls>") {
            if !tail.trim().is_empty() || calls.is_empty() {
                return Err("DSML tool call is incomplete.".into());
            }
            return Ok(Some(calls));
        }
        let after = rest
            .strip_prefix("<|DSML|invoke ")
            .ok_or("DSML tool call is invalid.")?;
        let end = after.find('>').ok_or("DSML tool call is incomplete.")?;
        let name = attr(&after[..end], "name")?;
        rest = &after[end + 1..];
        let mut arguments = serde_json::Map::new();
        loop {
            rest = rest.trim_start();
            if let Some(after) = rest.strip_prefix("</|DSML|invoke>") {
                rest = after;
                break;
            }
            let after = rest
                .strip_prefix("<|DSML|parameter ")
                .ok_or("DSML tool parameter is invalid.")?;
            let end = after
                .find('>')
                .ok_or("DSML tool parameter is incomplete.")?;
            let tag = &after[..end];
            let parameter = attr(tag, "name")?;
            let string = attr(tag, "string")?;
            if arguments.contains_key(&parameter) {
                return Err("DSML tool parameter is duplicated.".into());
            }
            let body = &after[end + 1..];
            let close = "</|DSML|parameter>";
            let close_at = body
                .find(close)
                .ok_or("DSML tool parameter is incomplete.")?;
            let raw = unescape(&body[..close_at]);
            let value = match string.as_str() {
                "true" => Value::String(raw),
                "false" => serde_json::from_str(raw.trim())
                    .map_err(|_| "DSML tool parameter type is invalid.")?,
                _ => return Err("DSML tool parameter type is invalid.".into()),
            };
            arguments.insert(parameter, value);
            rest = &body[close_at + close.len()..];
        }
        if calls.len() >= 8 {
            return Err("Too many tool calls.".into());
        }
        let args =
            serde_json::to_string(&arguments).map_err(|_| "DSML tool arguments are invalid.")?;
        if args.len() > 8192 {
            return Err("Tool call exceeded the size limit.".into());
        }
        calls.push(serde_json::json!({"id":format!("dsml_{}",calls.len()+1),"type":"function","function":{"name":name,"arguments":args}}));
    }
}

#[derive(Default, Debug)]
pub struct SseDecoder {
    bytes: Vec<u8>,
    pub finished: bool,
    pub terminated: bool,
    pub usage: Option<Value>,
    pub progress: u64,
    pub finish_reason: Option<String>,
    pub reasoning: String,
    tools: std::collections::BTreeMap<usize, (String, String, String)>,
}

impl SseDecoder {
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<String>, String> {
        self.bytes.extend_from_slice(chunk);
        if self.bytes.len() > 2 * 1024 * 1024 {
            return Err("API stream line exceeded the size limit.".into());
        }
        let mut deltas = Vec::new();
        // Decode only complete lines: HTTP chunks may split UTF-8 or CRLF.
        while let Some(end) = self.bytes.iter().position(|b| *b == b'\n') {
            if self.terminated {
                self.bytes.clear();
                break;
            }
            let line: Vec<_> = self.bytes.drain(..=end).collect();
            self.line(&line, &mut deltas)?;
        }
        Ok(deltas)
    }

    pub fn end(&mut self) -> Result<Vec<String>, String> {
        let mut deltas = Vec::new();
        let rest = std::mem::take(&mut self.bytes);
        if !rest.is_empty() {
            self.line(&rest, &mut deltas)?;
        }
        if !self.finished {
            return Err(
                "API stream ended before a completion marker; response may be incomplete.".into(),
            );
        }
        Ok(deltas)
    }

    fn line(&mut self, bytes: &[u8], deltas: &mut Vec<String>) -> Result<(), String> {
        if self.terminated {
            return Ok(());
        }
        let line = std::str::from_utf8(bytes)
            .map_err(|_| "Invalid UTF-8 in API stream.")?
            .trim();
        let Some(data) = line.strip_prefix("data:") else {
            return Ok(());
        };
        let data = data.trim();
        if data.is_empty() {
            return Ok(());
        }
        if data == "[DONE]" {
            self.finished = true;
            self.terminated = true;
            return Ok(());
        }
        let value: Value = match serde_json::from_str(data) {
            Ok(value) => value,
            Err(_) if self.finished => return Ok(()),
            Err(e) => return Err(format!("Failed to parse stream chunk: {e}")),
        };
        if self.finished {
            if let Some(usage) = value.get("usage").filter(|v| v.is_object()) {
                self.usage = Some(usage.clone());
            }
            return Ok(());
        }
        if value.get("error").is_some() {
            return Err("API reported an error within its event stream.".into());
        }
        if let Some(usage) = value.get("usage").filter(|v| v.is_object()) {
            self.usage = Some(usage.clone());
        }
        if let Some(reasoning) = value
            .pointer("/choices/0/delta/reasoning_content")
            .and_then(Value::as_str)
        {
            if self.reasoning.len() + reasoning.len() > 2 * 1024 * 1024 {
                return Err("Reasoning output exceeded the size limit.".into());
            }
            if !reasoning.trim().is_empty() {
                self.progress += 1;
            }
            self.reasoning.push_str(reasoning);
        }
        if let Some(delta) = value
            .pointer("/choices/0/delta/content")
            .and_then(Value::as_str)
        {
            if !delta.trim().is_empty() {
                self.progress += 1;
            }
            if !delta.is_empty() {
                deltas.push(delta.into());
            }
        }
        if let Some(calls) = value
            .pointer("/choices/0/delta/tool_calls")
            .and_then(Value::as_array)
        {
            self.ingest_calls(calls, true)?;
        }
        if let Some(reason) = value
            .pointer("/choices/0/finish_reason")
            .and_then(Value::as_str)
        {
            self.finish_reason = Some(reason.to_string());
            self.finished = true;
        }
        Ok(())
    }

    pub fn ingest_calls(&mut self, calls: &[Value], streaming: bool) -> Result<(), String> {
        for (position, call) in calls.iter().enumerate() {
            let index = if streaming {
                call.get("index")
                    .and_then(Value::as_u64)
                    .ok_or("Tool call index is missing.")? as usize
            } else {
                position
            };
            if index >= 8 {
                return Err("Too many tool calls.".into());
            }
            let entry = self.tools.entry(index).or_default();
            if let Some(id) = call.get("id").and_then(Value::as_str) {
                entry.0.push_str(id);
            }
            if let Some(name) = call.pointer("/function/name").and_then(Value::as_str) {
                entry.1.push_str(name);
            }
            if let Some(args) = call.pointer("/function/arguments").and_then(Value::as_str) {
                if !args.trim().is_empty() {
                    self.progress += 1;
                }
                entry.2.push_str(args);
            }
            if entry.0.len() > 256 || entry.1.len() > 100 || entry.2.len() > 8192 {
                return Err("Tool call exceeded the size limit.".into());
            }
        }
        Ok(())
    }
    pub fn calls(&self) -> Result<Vec<Value>, String> {
        let mut ids = std::collections::HashSet::new();
        self.tools.values().map(|(id,name,args)|{
            if id.is_empty() || name.is_empty() || !ids.insert(id){return Err("Invalid or duplicate tool call ID/name.".into());}
            Ok(serde_json::json!({"id":id,"type":"function","function":{"name":name,"arguments":args}}))
        }).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn every_byte_boundary_preserves_chinese_and_completion() {
        let bytes =
            "data: {\"choices\":[{\"delta\":{\"content\":\"璃奈\"}}]}\r\n\r\ndata: [DONE]\r\n\r\n"
                .as_bytes();
        for split in 0..=bytes.len() {
            let mut decoder = SseDecoder::default();
            let mut deltas = decoder.push(&bytes[..split]).unwrap();
            deltas.extend(decoder.push(&bytes[split..]).unwrap());
            deltas.extend(decoder.end().unwrap());
            assert_eq!(deltas.concat(), "璃奈");
        }
    }
    #[test]
    fn truncated_stream_is_not_success() {
        let mut decoder = SseDecoder::default();
        decoder
            .push(b"data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n")
            .unwrap();
        assert!(decoder.end().is_err());
    }
    #[test]
    fn finish_reason_without_done_is_supported() {
        let mut decoder = SseDecoder::default();
        decoder
            .push(b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}")
            .unwrap();
        assert!(decoder.end().is_ok());
    }
    #[test]
    fn stream_errors_are_not_completions() {
        assert!(SseDecoder::default()
            .push(b"data: {\"error\":{\"message\":\"failed\"}}\n")
            .is_err());
        assert!(SseDecoder::default().push(b"data: invalid\n").is_err());
    }
    #[test]
    fn fragmented_tool_arguments_and_length_reason() {
        let mut d = SseDecoder::default();
        d.ingest_calls(&[serde_json::json!({"index":0,"id":"call_1","function":{"name":"web_search","arguments":"{\"query\":"}})],true).unwrap();
        d.ingest_calls(
            &[serde_json::json!({"index":0,"function":{"arguments":"\"test\"}"}})],
            true,
        )
        .unwrap();
        let calls = d.calls().unwrap();
        assert_eq!(calls[0]["function"]["arguments"], "{\"query\":\"test\"}");
        d.push(b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"length\"}]}\n")
            .unwrap();
        assert_eq!(d.finish_reason.as_deref(), Some("length"));
    }
    #[test]
    fn only_semantic_progress_advances_deadline() {
        let mut d = SseDecoder::default();
        d.push(b": heartbeat\n\ndata: {\"choices\":[{\"delta\":{}}]}\n\ndata: {\"choices\":[{\"delta\":{\"content\":\"  \"}}]}\n").unwrap();
        assert_eq!(d.progress, 0);
        d.push(b"data: {\"choices\":[{\"delta\":{\"reasoning_content\":\"thinking\"}}]}\n")
            .unwrap();
        assert_eq!(d.progress, 1);
        d.ingest_calls(&[serde_json::json!({"index":0,"id":"x","function":{"name":"web_search","arguments":"{"}})],true).unwrap();
        assert_eq!(d.progress, 2);
        d.push(b"data: {\"choices\":[{\"delta\":{\"content\":\"answer\"}}]}\n")
            .unwrap();
        assert_eq!(d.progress, 3);
    }
    #[test]
    fn terminal_marker_ignores_late_data() {
        let mut d = SseDecoder::default();
        assert!(d
            .push(b"data: [DONE]\n\ndata: invalid\n")
            .unwrap()
            .is_empty());
        assert!(d
            .push(b"data: {\"choices\":[{\"delta\":{\"content\":\"late\"}}]}\n")
            .unwrap()
            .is_empty());
        assert!(d.end().unwrap().is_empty());
    }
    #[test]
    fn usage_after_finish_is_read_without_rendering_late_text() {
        let mut d = SseDecoder::default();
        d.push(b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}\n")
            .unwrap();
        assert!(d.finished);
        assert!(!d.terminated);
        let late=d.push(b"data: {\"choices\":[],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":2}}\n\ndata: [DONE]\n").unwrap();
        assert!(late.is_empty());
        assert!(d.terminated);
        assert_eq!(d.usage.unwrap()["prompt_tokens"], 10);
    }
    #[test]
    fn dsml_fallback_is_strict_and_typed() {
        let text = r#"<｜DSML｜calls><｜DSML｜invoke name="read_project_file"><｜DSML｜parameter name="line_count" string="false">60</｜DSML｜parameter><｜DSML｜parameter name="path" string="true">app/src/main.rs</｜DSML｜parameter><｜DSML｜parameter name="project" string="true">desk</｜DSML｜parameter></｜DSML｜invoke></｜DSML｜calls>"#;
        let calls = parse_dsml_calls(text).unwrap().unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0]["function"]["name"], "read_project_file");
        let args: Value =
            serde_json::from_str(calls[0]["function"]["arguments"].as_str().unwrap()).unwrap();
        assert_eq!(args["line_count"], 60);
        assert_eq!(args["path"], "app/src/main.rs");
        assert!(parse_dsml_calls("ordinary answer").unwrap().is_none());
        assert!(parse_dsml_calls(&format!("{text} trailing")).is_err());
    }
    #[test]
    fn tool_text_guard_streams_answers_and_hides_dsml() {
        let mut normal = ToolTextGuard::new(true);
        assert!(normal.push("<").is_none());
        assert_eq!(normal.push("b>answer"), Some("<b>answer".into()));
        let mut tool = ToolTextGuard::new(true);
        assert!(tool.push("  <｜DS").is_none());
        assert!(tool.push("ML｜calls>").is_none());
        assert!(tool.is_markup());
        assert!(tool.push("hidden").is_none());
        assert!(tool.finish().is_none());
        let mut disabled = ToolTextGuard::new(false);
        assert_eq!(disabled.push("hello"), Some("hello".into()));
    }
}
