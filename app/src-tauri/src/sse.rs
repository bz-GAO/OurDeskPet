use serde_json::Value;

#[derive(Default, Debug)]
pub struct SseDecoder {
    bytes: Vec<u8>,
    pub finished: bool,
}

impl SseDecoder {
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<String>, String> {
        self.bytes.extend_from_slice(chunk);
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
        if let Some(delta) = value.pointer("/choices/0/delta/content").and_then(Value::as_str) {
            if !delta.is_empty() { deltas.push(delta.into()); }
        }
        if value.pointer("/choices/0/finish_reason").and_then(Value::as_str).is_some() { self.finished = true; }
        Ok(())
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
}
