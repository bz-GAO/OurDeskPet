use serde_json::Value;

#[derive(Default, Debug)]
pub struct SseDecoder {
    bytes: Vec<u8>,
    pub finished: bool,
    pub finish_reason: Option<String>,
    pub reasoning: String,
    tools: std::collections::BTreeMap<usize, (String,String,String)>,
}

impl SseDecoder {
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<String>, String> {
        self.bytes.extend_from_slice(chunk);
        if self.bytes.len()>2*1024*1024 { return Err("API stream line exceeded the size limit.".into()); }
        let mut deltas = Vec::new();
        // Decode only complete lines: HTTP chunks may split UTF-8 or CRLF.
        while let Some(end) = self.bytes.iter().position(|b| *b == b'\n') {
            let line: Vec<_> = self.bytes.drain(..=end).collect();
            self.line(&line, &mut deltas)?;
        }
        Ok(deltas)
    }

    pub fn end(&mut self) -> Result<Vec<String>, String> {
        let mut deltas = Vec::new();
        let rest = std::mem::take(&mut self.bytes);
        if !rest.is_empty() { self.line(&rest, &mut deltas)?; }
        if !self.finished { return Err("API stream ended before a completion marker; response may be incomplete.".into()); }
        Ok(deltas)
    }

    fn line(&mut self, bytes: &[u8], deltas: &mut Vec<String>) -> Result<(), String> {
        let line = std::str::from_utf8(bytes).map_err(|_| "Invalid UTF-8 in API stream.")?.trim();
        let Some(data) = line.strip_prefix("data:") else { return Ok(()); };
        let data = data.trim();
        if data.is_empty() { return Ok(()); }
        if data == "[DONE]" { self.finished = true; return Ok(()); }
        let value: Value = serde_json::from_str(data).map_err(|e| format!("Failed to parse stream chunk: {e}"))?;
        if value.get("error").is_some() { return Err("API reported an error within its event stream.".into()); }
        if let Some(reasoning)=value.pointer("/choices/0/delta/reasoning_content").and_then(Value::as_str){
            if self.reasoning.len()+reasoning.len()>2*1024*1024{return Err("Reasoning output exceeded the size limit.".into());}
            self.reasoning.push_str(reasoning);
        }
        if let Some(delta) = value.pointer("/choices/0/delta/content").and_then(Value::as_str) {
            if !delta.is_empty() { deltas.push(delta.into()); }
        }
        if let Some(calls)=value.pointer("/choices/0/delta/tool_calls").and_then(Value::as_array){self.ingest_calls(calls,true)?;}
        if let Some(reason)=value.pointer("/choices/0/finish_reason").and_then(Value::as_str) { self.finish_reason=Some(reason.to_string());self.finished = true; }
        Ok(())
    }

    pub fn ingest_calls(&mut self,calls:&[Value],streaming:bool)->Result<(),String>{
        for (position,call) in calls.iter().enumerate(){
            let index=if streaming{call.get("index").and_then(Value::as_u64).ok_or("Tool call index is missing.")? as usize}else{position};
            if index>=8{return Err("Too many tool calls.".into());}
            let entry=self.tools.entry(index).or_default();
            if let Some(id)=call.get("id").and_then(Value::as_str){entry.0.push_str(id);}
            if let Some(name)=call.pointer("/function/name").and_then(Value::as_str){entry.1.push_str(name);}
            if let Some(args)=call.pointer("/function/arguments").and_then(Value::as_str){entry.2.push_str(args);}
            if entry.0.len()>256 || entry.1.len()>100 || entry.2.len()>8192{return Err("Tool call exceeded the size limit.".into());}
        }
        Ok(())
    }
    pub fn calls(&self)->Result<Vec<Value>,String>{
        let mut ids=std::collections::HashSet::new();
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
        let bytes = "data: {\"choices\":[{\"delta\":{\"content\":\"璃奈\"}}]}\r\n\r\ndata: [DONE]\r\n\r\n".as_bytes();
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
        decoder.push(b"data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n").unwrap();
        assert!(decoder.end().is_err());
    }
    #[test]
    fn finish_reason_without_done_is_supported() {
        let mut decoder = SseDecoder::default();
        decoder.push(b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}").unwrap();
        assert!(decoder.end().is_ok());
    }
    #[test]
    fn stream_errors_are_not_completions() {
        assert!(SseDecoder::default().push(b"data: {\"error\":{\"message\":\"failed\"}}\n").is_err());
        assert!(SseDecoder::default().push(b"data: invalid\n").is_err());
    }
    #[test]
    fn fragmented_tool_arguments_and_length_reason(){
        let mut d=SseDecoder::default();
        d.ingest_calls(&[serde_json::json!({"index":0,"id":"call_1","function":{"name":"web_search","arguments":"{\"query\":"}})],true).unwrap();
        d.ingest_calls(&[serde_json::json!({"index":0,"function":{"arguments":"\"test\"}"}})],true).unwrap();
        let calls=d.calls().unwrap();assert_eq!(calls[0]["function"]["arguments"],"{\"query\":\"test\"}");
        d.push(b"data: {\"choices\":[{\"delta\":{},\"finish_reason\":\"length\"}]}\n").unwrap();assert_eq!(d.finish_reason.as_deref(),Some("length"));
    }
}
