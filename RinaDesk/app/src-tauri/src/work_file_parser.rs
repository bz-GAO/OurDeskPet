use super::*;
use std::io::Read;
#[cfg(test)]
use std::io::Write;
#[cfg(test)]
use zip::write::SimpleFileOptions;
use zip::ZipArchive;

const MAX_RAW_BYTES: usize = 8 * 1024 * 1024;
const MAX_XML_BYTES: u64 = 16 * 1024 * 1024;
const MAX_TOTAL_XML_BYTES: u64 = 64 * 1024 * 1024;
const MAX_OUTPUT_BYTES: usize = 512 * 1024;
const MAX_ARCHIVE_ENTRIES: usize = 10_000;
const MAX_XLSX_SHEETS: usize = 50;
const TRUNCATED_NOTE: &str = "\n[解析结果已截断到附件上限]";

struct WorkArchive {
    zip: ZipArchive<Cursor<Vec<u8>>>,
    xml_bytes: u64,
}

#[derive(Default)]
struct BoundedOutput {
    text: String,
    truncated: bool,
}

impl BoundedOutput {
    fn push(&mut self, value: &str) {
        if self.truncated {
            return;
        }
        let remaining = (MAX_OUTPUT_BYTES - TRUNCATED_NOTE.len()).saturating_sub(self.text.len());
        if value.len() <= remaining {
            self.text.push_str(value);
        } else {
            let mut end = remaining;
            while !value.is_char_boundary(end) {
                end -= 1;
            }
            self.text.push_str(&value[..end]);
            self.truncated = true;
        }
    }

    fn finish(mut self) -> String {
        if self.truncated {
            self.text.push_str(TRUNCATED_NOTE);
        }
        self.text
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkFileParseRequest {
    name: String,
    mime_type: String,
    byte_size: usize,
    data_base64: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ParsedWorkFile {
    name: String,
    mime_type: String,
    byte_size: usize,
    language: String,
    kind: String,
    parser: String,
    content: String,
}

fn safe_name(name: &str) -> Result<(), String> {
    if name.trim().is_empty() || name.chars().count() > 260 || name.chars().any(char::is_control) {
        Err("工作文件名无效。".into())
    } else {
        Ok(())
    }
}

fn extension(name: &str) -> String {
    Path::new(name)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
}

fn read_entry(archive: &mut WorkArchive, name: &str) -> Result<String, String> {
    let file = archive
        .zip
        .by_name(name)
        .map_err(|_| format!("文件内缺少 {name}。"))?;
    if file.size() > MAX_XML_BYTES {
        return Err(format!("{name} 解压后过大。"));
    }
    let remaining = MAX_TOTAL_XML_BYTES.saturating_sub(archive.xml_bytes);
    if file.size() > remaining {
        return Err("工作文件解压内容过多。".into());
    }
    let mut text = String::new();
    file.take(MAX_XML_BYTES.min(remaining) + 1)
        .read_to_string(&mut text)
        .map_err(|_| format!("无法读取 {name}。"))?;
    if text.len() as u64 > MAX_XML_BYTES {
        return Err(format!("{name} 解压后过大。"));
    }
    archive.xml_bytes += text.len() as u64;
    if archive.xml_bytes > MAX_TOTAL_XML_BYTES {
        return Err("工作文件解压内容过多。".into());
    }
    Ok(text)
}

fn read_optional_entry(archive: &mut WorkArchive, name: &str) -> Result<Option<String>, String> {
    if archive.zip.file_names().any(|candidate| candidate == name) {
        read_entry(archive, name).map(Some)
    } else {
        Ok(None)
    }
}

fn attr<'a, 'input>(node: roxmltree::Node<'a, 'input>, name: &str) -> Option<&'a str> {
    node.attributes()
        .find(|attribute| attribute.name() == name)
        .map(|attribute| attribute.value())
}

fn node_text(node: roxmltree::Node<'_, '_>) -> String {
    node.descendants()
        .filter(|child| child.is_element() && child.tag_name().name() == "t")
        .filter_map(|child| child.text())
        .collect::<Vec<_>>()
        .join("")
}

fn paragraph_text(paragraph: roxmltree::Node<'_, '_>) -> String {
    let mut value = String::new();
    for node in paragraph.descendants().filter(|node| node.is_element()) {
        match node.tag_name().name() {
            "t" => {
                if let Some(text) = node.text() {
                    value.push_str(text);
                }
            }
            "tab" => value.push('\t'),
            "br" | "cr" => value.push('\n'),
            _ => {}
        }
    }
    value.trim().to_string()
}

fn paragraph_style<'a, 'input>(paragraph: roxmltree::Node<'a, 'input>) -> Option<&'a str> {
    paragraph
        .children()
        .find(|node| node.is_element() && node.tag_name().name() == "pPr")?
        .children()
        .find(|node| node.is_element() && node.tag_name().name() == "pStyle")
        .and_then(|node| attr(node, "val"))
}

fn heading_level(style: &str) -> Option<usize> {
    let lowered = style.trim().to_ascii_lowercase().replace([' ', '-'], "");
    if lowered == "title" || style.trim() == "标题" {
        return Some(1);
    }
    for prefix in ["heading", "标题"] {
        if let Some(suffix) = lowered.strip_prefix(prefix) {
            if let Ok(level) = suffix.parse::<usize>() {
                return Some(level.clamp(1, 6));
            }
        }
    }
    None
}

fn docx_table(
    table: roxmltree::Node<'_, '_>,
    index: usize,
    output: &mut BoundedOutput,
) -> Result<(), String> {
    output.push(&format!("## Table {index}\n"));
    let mut row_number = 0;
    for row in table
        .children()
        .filter(|node| node.is_element() && node.tag_name().name() == "tr")
    {
        row_number += 1;
        let mut column: usize = 1;
        let mut first = true;
        for cell in row
            .children()
            .filter(|node| node.is_element() && node.tag_name().name() == "tc")
        {
            if output.truncated {
                return Ok(());
            }
            let span = cell
                .descendants()
                .find(|node| node.is_element() && node.tag_name().name() == "gridSpan")
                .and_then(|node| attr(node, "val"))
                .map(str::parse::<usize>)
                .transpose()
                .map_err(|_| "DOCX 表格列跨度无效。")?
                .unwrap_or(1);
            if !(1..=16_384).contains(&span) {
                return Err("DOCX 表格列跨度无效。".into());
            }
            let paragraphs = cell
                .children()
                .filter(|node| node.is_element() && node.tag_name().name() == "p")
                .map(paragraph_text)
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>();
            let label = if span == 1 {
                format!("C{column}")
            } else {
                format!("C{column}-C{}", column + span - 1)
            };
            if first {
                output.push(&format!("Row {row_number} | "));
                first = false;
            } else {
                output.push(" | ");
            }
            output.push(&format!("{label}: "));
            for (index, paragraph) in paragraphs.iter().enumerate() {
                if index > 0 {
                    output.push(" ↵ ");
                }
                output.push(paragraph);
                if output.truncated {
                    return Ok(());
                }
            }
            column += span;
        }
        if !first {
            output.push("\n");
        }
    }
    Ok(())
}

fn parse_docx(archive: &mut WorkArchive) -> Result<String, String> {
    let xml = read_entry(archive, "word/document.xml")?;
    let document = roxmltree::Document::parse(&xml).map_err(|_| "DOCX 文档结构无效。")?;
    let body = document
        .descendants()
        .find(|node| node.is_element() && node.tag_name().name() == "body")
        .ok_or_else(|| "DOCX 文档中缺少正文。".to_string())?;
    let paragraphs = body
        .children()
        .filter(|node| node.is_element() && node.tag_name().name() == "p")
        .count();
    let tables = body
        .children()
        .filter(|node| node.is_element() && node.tag_name().name() == "tbl")
        .count();
    let mut output = BoundedOutput::default();
    output.push(&format!(
        "[DOCX document · paragraphs: {paragraphs} · tables: {tables}]\n"
    ));
    let mut has_content = false;
    let mut table_number = 0;
    for block in body.children().filter(|node| node.is_element()) {
        if output.truncated {
            break;
        }
        match block.tag_name().name() {
            "p" => {
                let text = paragraph_text(block);
                if text.is_empty() {
                    continue;
                }
                has_content = true;
                if let Some(level) = paragraph_style(block).and_then(heading_level) {
                    output.push(&format!("{} ", "#".repeat(level)));
                }
                output.push(&text);
                output.push("\n");
            }
            "tbl" => {
                table_number += 1;
                has_content = true;
                docx_table(block, table_number, &mut output)?;
            }
            _ => {}
        }
    }
    if !has_content {
        return Err("DOCX 中没有可读取的段落或表格。".into());
    }
    Ok(output.finish())
}

fn relationship_targets(xml: &str) -> Result<HashMap<String, String>, String> {
    let document = roxmltree::Document::parse(xml).map_err(|_| "XLSX 关系表无效。")?;
    let mut result = HashMap::new();
    for node in document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "Relationship")
    {
        if attr(node, "TargetMode") == Some("External") {
            continue;
        }
        if let (Some(id), Some(target)) = (attr(node, "Id"), attr(node, "Target")) {
            result.insert(id.to_string(), target.to_string());
        }
    }
    Ok(result)
}

fn normalize_xlsx_target(target: &str) -> Option<String> {
    if target.contains('\\') {
        return None;
    }
    let raw = if target.starts_with('/') {
        target.trim_start_matches('/').to_string()
    } else {
        format!("xl/{target}")
    };
    let mut parts = Vec::new();
    for part in raw.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                parts.pop()?;
            }
            value => parts.push(value),
        }
    }
    let normalized = parts.join("/");
    normalized.starts_with("xl/").then_some(normalized)
}

fn workbook_sheets(
    workbook: &str,
    relationships: &HashMap<String, String>,
) -> Result<Vec<(String, String)>, String> {
    let document = roxmltree::Document::parse(workbook).map_err(|_| "XLSX 工作簿结构无效。")?;
    let mut result = Vec::new();
    for node in document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "sheet")
    {
        let name = attr(node, "name").unwrap_or("Sheet").to_string();
        let id = attr(node, "id");
        if let Some(path) = id
            .and_then(|value| relationships.get(value))
            .and_then(|target| normalize_xlsx_target(target))
        {
            result.push((name, path));
        }
    }
    Ok(result)
}

fn workbook_uses_1904_dates(workbook: &str) -> bool {
    let Ok(document) = roxmltree::Document::parse(workbook) else {
        return false;
    };
    let value = document
        .descendants()
        .find(|node| node.is_element() && node.tag_name().name() == "workbookPr")
        .and_then(|node| attr(node, "date1904"));
    value.is_some_and(|value| value == "1" || value.eq_ignore_ascii_case("true"))
}

fn shared_strings(archive: &mut WorkArchive) -> Result<Vec<String>, String> {
    let Some(xml) = read_optional_entry(archive, "xl/sharedStrings.xml")? else {
        return Ok(Vec::new());
    };
    let document = roxmltree::Document::parse(&xml).map_err(|_| "XLSX 共享文字结构无效。")?;
    Ok(document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "si")
        .map(node_text)
        .collect())
}

#[derive(Clone, Copy, Default)]
struct DateFormat {
    date: bool,
    time: bool,
    elapsed: bool,
}

fn builtin_date_format(id: u32) -> DateFormat {
    match id {
        14..=17 | 27..=36 | 50..=58 => DateFormat {
            date: true,
            time: false,
            elapsed: false,
        },
        18..=21 | 45 | 47 => DateFormat {
            date: false,
            time: true,
            elapsed: false,
        },
        46 => DateFormat {
            date: false,
            time: true,
            elapsed: true,
        },
        22 => DateFormat {
            date: true,
            time: true,
            elapsed: false,
        },
        _ => DateFormat::default(),
    }
}

fn custom_date_format(code: &str) -> DateFormat {
    let mut cleaned = String::new();
    let mut quoted = false;
    let mut escaped = false;
    let mut bracket = String::new();
    let mut in_bracket = false;
    let mut elapsed = false;
    for character in code.to_ascii_lowercase().chars() {
        if escaped {
            escaped = false;
            continue;
        }
        if character == '\\' || character == '_' || character == '*' {
            escaped = true;
            continue;
        }
        if character == '"' {
            quoted = !quoted;
            continue;
        }
        if quoted {
            continue;
        }
        if character == '[' {
            in_bracket = true;
            bracket.clear();
            continue;
        }
        if character == ']' && in_bracket {
            if bracket
                .chars()
                .all(|value| matches!(value, 'h' | 'm' | 's'))
            {
                cleaned.push_str(&bracket);
                elapsed = true;
            }
            in_bracket = false;
            continue;
        }
        if in_bracket {
            bracket.push(character);
        } else {
            cleaned.push(character);
        }
    }
    let time = elapsed || cleaned.contains('h') || cleaned.contains('s');
    let date = cleaned.contains('y') || cleaned.contains('d') || (!time && cleaned.contains('m'));
    DateFormat {
        date,
        time,
        elapsed,
    }
}

fn cell_date_styles(styles: Option<&str>) -> Result<Vec<DateFormat>, String> {
    let Some(xml) = styles else {
        return Ok(Vec::new());
    };
    let document = roxmltree::Document::parse(xml).map_err(|_| "XLSX 样式表无效。")?;
    let mut custom = HashMap::new();
    for node in document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "numFmt")
    {
        if let (Some(id), Some(code)) = (attr(node, "numFmtId"), attr(node, "formatCode")) {
            if let Ok(id) = id.parse::<u32>() {
                custom.insert(id, custom_date_format(code));
            }
        }
    }
    let Some(cell_xfs) = document
        .descendants()
        .find(|node| node.is_element() && node.tag_name().name() == "cellXfs")
    else {
        return Ok(Vec::new());
    };
    Ok(cell_xfs
        .children()
        .filter(|node| node.is_element() && node.tag_name().name() == "xf")
        .map(|node| {
            attr(node, "numFmtId")
                .and_then(|value| value.parse::<u32>().ok())
                .map(|id| {
                    custom
                        .get(&id)
                        .copied()
                        .unwrap_or_else(|| builtin_date_format(id))
                })
                .unwrap_or_default()
        })
        .collect())
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let shifted = days_since_unix_epoch + 719_468;
    let era = if shifted >= 0 {
        shifted
    } else {
        shifted - 146_096
    } / 146_097;
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    year += if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

fn excel_date(value: &str, format: DateFormat, uses_1904_dates: bool) -> Option<String> {
    if !format.date && !format.time {
        return None;
    }
    let serial = value.parse::<f64>().ok()?;
    // Validate before float-to-integer conversion and calendar arithmetic.
    if !serial.is_finite() || serial.abs() > 4_000_000.0 {
        return None;
    }
    if format.elapsed && !format.date {
        let total_seconds = (serial * 86_400.0).round() as i64;
        if total_seconds < 0 {
            return None;
        }
        return Some(format!(
            "{:02}:{:02}:{:02}",
            total_seconds / 3_600,
            total_seconds / 60 % 60,
            total_seconds % 60
        ));
    }
    let mut whole_days = serial.floor() as i64;
    let mut seconds = ((serial - serial.floor()) * 86_400.0).round() as i64;
    if seconds >= 86_400 {
        whole_days += 1;
        seconds -= 86_400;
    }
    let time = format!(
        "{:02}:{:02}:{:02}",
        seconds / 3_600,
        seconds / 60 % 60,
        seconds % 60
    );
    if !format.date {
        return Some(time);
    }
    if !uses_1904_dates && whole_days == 60 {
        return None;
    } // Excel's fictitious leap day.
    let unix_days = whole_days
        - if uses_1904_dates {
            24_107
        } else if whole_days < 60 {
            25_568
        } else {
            25_569
        };
    let (year, month, day) = civil_from_days(unix_days);
    if !(1..=9_999).contains(&year) {
        return None;
    }
    let date = format!("{year:04}-{month:02}-{day:02}");
    Some(if format.time {
        format!("{date} {time}")
    } else {
        date
    })
}

fn parse_sheet(
    xml: &str,
    shared: &[String],
    styles: &[DateFormat],
    uses_1904_dates: bool,
    output: &mut BoundedOutput,
) -> Result<(), String> {
    let document = roxmltree::Document::parse(xml).map_err(|_| "XLSX 工作表结构无效。")?;
    let merged = document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "mergeCell")
        .filter_map(|node| attr(node, "ref"))
        .collect::<Vec<_>>();
    let mut has_content = false;
    if !merged.is_empty() {
        let shown = merged
            .iter()
            .take(200)
            .copied()
            .collect::<Vec<_>>()
            .join(", ");
        let remainder = merged.len().saturating_sub(200);
        output.push(&if remainder == 0 {
            format!("[Merged cells: {shown}]")
        } else {
            format!("[Merged cells: {shown}; 另有 {remainder} 个合并区域未列出]")
        });
        output.push("\n");
        has_content = true;
    }
    for (fallback_row, row) in document
        .descendants()
        .filter(|node| node.is_element() && node.tag_name().name() == "row")
        .enumerate()
    {
        if output.truncated {
            return Ok(());
        }
        let row_number = attr(row, "r")
            .map(str::to_string)
            .unwrap_or_else(|| (fallback_row + 1).to_string());
        let mut first = true;
        for cell in row
            .children()
            .filter(|node| node.is_element() && node.tag_name().name() == "c")
        {
            if output.truncated {
                return Ok(());
            }
            let address = attr(cell, "r").unwrap_or("?");
            let kind = attr(cell, "t").unwrap_or("");
            let raw = cell
                .children()
                .find(|node| node.is_element() && node.tag_name().name() == "v")
                .and_then(|node| node.text())
                .unwrap_or("");
            let style = attr(cell, "s")
                .and_then(|value| value.parse::<usize>().ok())
                .and_then(|index| styles.get(index))
                .copied()
                .unwrap_or_default();
            let mut value = match kind {
                "s" => raw
                    .parse::<usize>()
                    .ok()
                    .and_then(|index| shared.get(index))
                    .cloned()
                    .ok_or_else(|| format!("XLSX 单元格 {address} 的共享文字引用无效。"))?,
                "inlineStr" => node_text(cell),
                "b" => {
                    if raw == "1" {
                        "TRUE".into()
                    } else {
                        "FALSE".into()
                    }
                }
                "e" => format!("[错误: {raw}]"),
                "d" => raw.to_string(),
                _ => excel_date(raw, style, uses_1904_dates).unwrap_or_else(|| raw.to_string()),
            };
            if let Some(formula) = cell
                .children()
                .find(|node| node.is_element() && node.tag_name().name() == "f")
                .and_then(|node| node.text())
            {
                value = if value.is_empty() {
                    format!("={formula} [无缓存值；未重新计算]")
                } else {
                    format!("={formula} → 缓存值: {value}")
                };
            }
            if !value.is_empty() {
                if first {
                    output.push(&format!("Row {row_number} | "));
                    first = false;
                } else {
                    output.push(" | ");
                }
                output.push(address);
                output.push(": ");
                output.push(&value.replace(['\r', '\n'], " "));
                has_content = true;
            }
        }
        if !first {
            output.push("\n");
        }
    }
    if !has_content {
        output.push("[empty]\n");
    }
    Ok(())
}

fn parse_xlsx(archive: &mut WorkArchive) -> Result<String, String> {
    let shared = shared_strings(archive)?;
    let styles_xml = read_optional_entry(archive, "xl/styles.xml")?;
    let styles = cell_date_styles(styles_xml.as_deref())?;
    let workbook = read_entry(archive, "xl/workbook.xml")?;
    let uses_1904_dates = workbook_uses_1904_dates(&workbook);
    let relationships = read_entry(archive, "xl/_rels/workbook.xml.rels")?;
    let sheets = workbook_sheets(&workbook, &relationship_targets(&relationships)?)?;
    if sheets.is_empty() {
        return Err("XLSX 中没有可读取的工作表。".into());
    }
    let mut output = BoundedOutput::default();
    output.push(&format!(
        "[XLSX workbook · sheets: {} · date system: {}]\n[公式不会重新计算；如有结果，显示的是文件保存时的缓存值]\n",
        sheets.len(),
        if uses_1904_dates { "1904" } else { "1900" }
    ));
    if sheets.len() > MAX_XLSX_SHEETS {
        output.push("[仅解析前 50 个工作表，其余工作表已省略]\n");
    }
    for (name, path) in sheets.into_iter().take(MAX_XLSX_SHEETS) {
        if output.truncated {
            break;
        }
        output.push(&format!("\n## Sheet: {name}\n"));
        if output.truncated {
            break;
        }
        let xml = read_entry(archive, &path)?;
        parse_sheet(&xml, &shared, &styles, uses_1904_dates, &mut output)?;
    }
    Ok(output.finish())
}

fn parse(request: WorkFileParseRequest) -> Result<ParsedWorkFile, String> {
    safe_name(&request.name)?;
    if request.byte_size == 0 || request.byte_size > MAX_RAW_BYTES {
        return Err("工作文件请控制在 8 MiB 以内。".into());
    }
    if request.mime_type.len() > 120 {
        return Err("工作文件类型无效。".into());
    }
    if request.data_base64.len() > ((MAX_RAW_BYTES + 2) / 3) * 4 {
        return Err("工作文件传输数据过大。".into());
    }
    let bytes = BASE64_STANDARD
        .decode(request.data_base64)
        .map_err(|_| "工作文件传输数据无效。")?;
    if bytes.len() != request.byte_size {
        return Err("工作文件大小校验失败。".into());
    }
    let zip = ZipArchive::new(Cursor::new(bytes))
        .map_err(|_| "工作文件不是有效的 Office Open XML 文件。")?;
    if zip.len() > MAX_ARCHIVE_ENTRIES {
        return Err("工作文件包含过多内部条目。".into());
    }
    let mut archive = WorkArchive { zip, xml_bytes: 0 };
    let ext = extension(&request.name);
    let (kind, parser, content) = match ext.as_str() {
        "docx" => ("document", "docx-structure-v2", parse_docx(&mut archive)?),
        "xlsx" => ("spreadsheet", "xlsx-cells-v2", parse_xlsx(&mut archive)?),
        _ => return Err("当前工作文件解析仅支持 DOCX 和 XLSX。".into()),
    };
    Ok(ParsedWorkFile {
        name: request.name,
        mime_type: request.mime_type,
        byte_size: request.byte_size,
        language: ext,
        kind: kind.into(),
        parser: parser.into(),
        content,
    })
}

#[tauri::command]
pub async fn parse_work_file(request: WorkFileParseRequest) -> Result<ParsedWorkFile, String> {
    tauri::async_runtime::spawn_blocking(move || parse(request))
        .await
        .map_err(|_| "工作文件解析任务未完成。".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    fn archive(files: &[(&str, &str)]) -> Vec<u8> {
        let mut cursor = Cursor::new(Vec::new());
        {
            let mut writer = zip::ZipWriter::new(&mut cursor);
            for (name, content) in files {
                writer
                    .start_file(name, SimpleFileOptions::default())
                    .unwrap();
                writer.write_all(content.as_bytes()).unwrap();
            }
            writer.finish().unwrap();
        }
        cursor.into_inner()
    }

    fn request(name: &str, bytes: Vec<u8>) -> WorkFileParseRequest {
        WorkFileParseRequest {
            name: name.into(),
            mime_type: "application/octet-stream".into(),
            byte_size: bytes.len(),
            data_base64: BASE64_STANDARD.encode(bytes),
        }
    }

    #[test]
    fn rejects_broken_shared_string_reference() {
        assert!(parse_sheet(
            r#"<worksheet><row><c r="A1" t="s"><v>9</v></c></row></worksheet>"#,
            &[],
            &[],
            false,
            &mut BoundedOutput::default()
        )
        .is_err());
    }

    #[test]
    fn extracts_docx_headings_and_tables_without_duplicate_cell_paragraphs() {
        let bytes = archive(&[(
            "word/document.xml",
            r#"<w:document xmlns:w="w"><w:body>
            <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>概要</w:t></w:r></w:p>
            <w:tbl><w:tr><w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>说明</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
            <w:p><w:r><w:t>结束</w:t></w:r></w:p></w:body></w:document>"#,
        )]);
        let parsed = parse(request("note.docx", bytes)).unwrap();
        assert_eq!(parsed.parser, "docx-structure-v2");
        assert!(parsed.content.contains("# 概要"));
        assert!(parsed.content.contains("Row 1 | C1: 项目 | C2-C3: 说明"));
        assert_eq!(parsed.content.matches("项目").count(), 1);
    }

    #[test]
    fn extracts_xlsx_dates_merges_and_formula_cache_state() {
        let bytes = archive(&[
            (
                "xl/workbook.xml",
                r#"<workbook xmlns:r="rel"><workbookPr date1904="0"/><sheets><sheet name="Data" r:id="rId1"/></sheets></workbook>"#,
            ),
            (
                "xl/_rels/workbook.xml.rels",
                r#"<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>"#,
            ),
            (
                "xl/styles.xml",
                r#"<styleSheet><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>"#,
            ),
            ("xl/sharedStrings.xml", r#"<sst><si><t>项目</t></si></sst>"#),
            (
                "xl/worksheets/sheet1.xml",
                r#"<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" s="1"><v>45292</v></c><c r="C1"><f>1+1</f><v>2</v></c><c r="D1"><f>2+2</f></c></row></sheetData><mergeCells><mergeCell ref="A1:A2"/></mergeCells></worksheet>"#,
            ),
        ]);
        let parsed = parse(request("book.xlsx", bytes)).unwrap();
        assert_eq!(parsed.parser, "xlsx-cells-v2");
        assert!(parsed.content.contains("Merged cells: A1:A2"));
        assert!(parsed.content.contains("B1: 2024-01-01"));
        assert!(parsed.content.contains("=1+1 → 缓存值: 2"));
        assert!(parsed.content.contains("=2+2 [无缓存值；未重新计算]"));
    }

    #[test]
    fn supports_1904_dates_and_rejects_external_sheet_targets() {
        assert_eq!(
            excel_date(
                "0",
                DateFormat {
                    date: true,
                    time: false,
                    elapsed: false,
                },
                true
            )
            .as_deref(),
            Some("1904-01-01")
        );
        let relationships = relationship_targets(
            r#"<Relationships><Relationship Id="rId1" Target="https://example.invalid/a.xml" TargetMode="External"/></Relationships>"#,
        )
        .unwrap();
        assert!(relationships.is_empty());
    }

    #[test]
    fn formats_elapsed_time_without_wrapping_at_twenty_four_hours() {
        let format = custom_date_format("[h]:mm");
        assert!(format.elapsed);
        assert_eq!(
            excel_date("1.5", format, false).as_deref(),
            Some("36:00:00")
        );
        assert_eq!(
            excel_date("1.5", builtin_date_format(46), false).as_deref(),
            Some("36:00:00")
        );
    }

    #[test]
    fn bounds_shared_string_expansion_and_stops_before_later_cells() {
        let shared = vec!["中日文".repeat(30_000)];
        let repeated = r#"<c t="s"><v>0</v></c>"#.repeat(100);
        let xml = format!(r#"<worksheet><row>{repeated}<c t="s"><v>999</v></c></row></worksheet>"#);
        let mut output = BoundedOutput::default();
        parse_sheet(&xml, &shared, &[], false, &mut output).unwrap();
        let text = output.finish();
        assert!(text.len() <= MAX_OUTPUT_BYTES);
        assert!(text.ends_with(TRUNCATED_NOTE));
        assert!(text.contains("中日文"));
    }

    #[test]
    fn bounds_docx_output_and_rejects_overflowing_table_spans() {
        let paragraph = format!("<p><r><t>{}</t></r></p>", "文字".repeat(100_000));
        let xml = format!("<document><body>{paragraph}{paragraph}</body></document>");
        let parsed = parse(request(
            "large.docx",
            archive(&[("word/document.xml", &xml)]),
        ))
        .unwrap();
        assert!(parsed.content.len() <= MAX_OUTPUT_BYTES);
        assert!(parsed.content.ends_with(TRUNCATED_NOTE));
        let xml = r#"<document><body><tbl><tr><tc><tcPr><gridSpan val="18446744073709551615"/></tcPr><p><r><t>x</t></r></p></tc></tr></tbl></body></document>"#;
        assert!(parse(request("bad.docx", archive(&[("word/document.xml", xml)]))).is_err());
    }

    #[test]
    fn counts_total_xml_bytes_even_when_an_entry_is_referenced_again() {
        let zip = ZipArchive::new(Cursor::new(archive(&[("data.xml", "abcd")]))).unwrap();
        let mut input = WorkArchive {
            zip,
            xml_bytes: MAX_TOTAL_XML_BYTES - 6,
        };
        assert_eq!(read_entry(&mut input, "data.xml").unwrap(), "abcd");
        assert!(read_entry(&mut input, "data.xml").is_err());
    }

    #[test]
    fn handles_early_and_invalid_excel_dates_without_integer_overflow() {
        let format = builtin_date_format(14);
        assert_eq!(
            excel_date("1", format, false).as_deref(),
            Some("1900-01-01")
        );
        assert_eq!(
            excel_date("59", format, false).as_deref(),
            Some("1900-02-28")
        );
        assert_eq!(excel_date("60", format, false), None);
        assert_eq!(
            excel_date("61", format, false).as_deref(),
            Some("1900-03-01")
        );
        for value in ["-1e308", "1e308", "NaN", "inf"] {
            assert_eq!(excel_date(value, format, false), None);
        }
    }
}
