use super::*;
use tree_sitter::{Language, Node, Parser};

const MAX_CODE_BYTES: usize = 8 * 1024 * 1024;
const MAX_OUTPUT_BYTES: usize = 8 * 1024 * 1024;
const MAX_ITEMS: usize = 200;
const MAX_NODES: usize = 100_000;

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CodeFileParseRequest {
    name: String,
    mime_type: String,
    byte_size: usize,
    content: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CodeSymbol {
    pub name: String,
    pub kind: String,
    pub line: usize,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CodeFileMeta {
    pub ast: bool,
    pub syntax_errors: usize,
    pub imports: Vec<String>,
    pub symbols: Vec<CodeSymbol>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ParsedCodeFile {
    name: String,
    mime_type: String,
    byte_size: usize,
    language: String,
    kind: String,
    parser: String,
    content: String,
    code_meta: CodeFileMeta,
}

fn extension(name: &str) -> String {
    Path::new(name)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
}
fn grammar(ext: &str) -> Option<(&'static str, Language)> {
    match ext {
        "ts" => Some((
            "typescript",
            tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
        )),
        "tsx" => Some(("tsx", tree_sitter_typescript::LANGUAGE_TSX.into())),
        "js" | "mjs" | "cjs" | "jsx" => {
            Some(("javascript", tree_sitter_javascript::LANGUAGE.into()))
        }
        "py" => Some(("python", tree_sitter_python::LANGUAGE.into())),
        "rs" => Some(("rust", tree_sitter_rust::LANGUAGE.into())),
        _ => None,
    }
}

fn text(node: Node<'_>, source: &str) -> String {
    node.utf8_text(source.as_bytes())
        .unwrap_or_default()
        .trim()
        .to_string()
}
fn bounded(value: &str, limit: usize) -> String {
    let mut end = value.len().min(limit);
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    value[..end].to_string()
}
fn clean_import(value: &str, language: &str) -> String {
    let value = value.trim().trim_end_matches(';');
    if language == "python" {
        if let Some(rest) = value.strip_prefix("from ") {
            return rest.split_whitespace().next().unwrap_or(rest).to_string();
        }
        if let Some(rest) = value.strip_prefix("import ") {
            return rest
                .split(|value: char| value == ',' || value.is_whitespace())
                .next()
                .unwrap_or(rest)
                .to_string();
        }
    }
    if language == "rust" {
        return value
            .strip_prefix("use ")
            .unwrap_or(value)
            .split("::{")
            .next()
            .unwrap_or(value)
            .trim()
            .to_string();
    }
    if let Some(index) = value.rfind(" from ") {
        return value[index + 6..]
            .trim_matches(|value| value == '\'' || value == '"')
            .to_string();
    }
    value
        .trim_matches(|value| value == '\'' || value == '"')
        .to_string()
}

fn symbol(node: Node<'_>, source: &str, language: &str) -> Option<CodeSymbol> {
    let kind = node.kind();
    let label = match language {
        "python" => match kind {
            "function_definition" | "class_definition" => kind,
            _ => return None,
        },
        "rust" => match kind {
            "function_item" | "struct_item" | "enum_item" | "trait_item" | "type_item"
            | "mod_item" | "impl_item" => kind,
            _ => return None,
        },
        _ => match kind {
            "function_declaration"
            | "class_declaration"
            | "interface_declaration"
            | "type_alias_declaration"
            | "enum_declaration"
            | "method_definition" => kind,
            "variable_declarator" => {
                let value = node.child_by_field_name("value")?;
                if !matches!(value.kind(), "arrow_function" | "function_expression") {
                    return None;
                }
                "function_variable"
            }
            _ => return None,
        },
    }
    .trim_end_matches("_declaration")
    .trim_end_matches("_definition")
    .trim_end_matches("_item")
    .replace('_', " ");
    let name_node = node.child_by_field_name("name").or_else(|| {
        if kind == "impl_item" {
            node.child_by_field_name("type")
        } else {
            None
        }
    })?;
    let name = text(name_node, source);
    if name.is_empty() {
        None
    } else {
        Some(CodeSymbol {
            name: bounded(&name, 200),
            kind: label,
            line: node.start_position().row + 1,
        })
    }
}

fn import(node: Node<'_>, source: &str, language: &str) -> Option<String> {
    let raw = match language {
        "python" if matches!(node.kind(), "import_statement" | "import_from_statement") => {
            text(node, source)
        }
        "rust" if node.kind() == "use_declaration" => text(node, source),
        "javascript" | "typescript" | "tsx" if node.kind() == "import_statement" => node
            .child_by_field_name("source")
            .map(|child| text(child, source))
            .unwrap_or_else(|| text(node, source)),
        _ => return None,
    };
    let result = clean_import(&raw, language);
    if result.is_empty() || result.len() > 300 {
        None
    } else {
        Some(result)
    }
}

fn inspect(root: Node<'_>, source: &str, language: &str) -> CodeFileMeta {
    let mut stack = vec![root];
    let mut visited = 0usize;
    let mut syntax_errors = 0usize;
    let mut imports = Vec::new();
    let mut symbols = Vec::new();
    while let Some(node) = stack.pop() {
        visited += 1;
        if visited > MAX_NODES {
            break;
        }
        if node.is_error() || node.is_missing() {
            syntax_errors += 1;
        }
        if imports.len() < MAX_ITEMS {
            if let Some(value) = import(node, source, language) {
                if !imports.contains(&value) {
                    imports.push(value);
                }
            }
        }
        if symbols.len() < MAX_ITEMS {
            if let Some(value) = symbol(node, source, language) {
                symbols.push(value);
            }
        }
        let mut cursor = node.walk();
        let children = node.children(&mut cursor).collect::<Vec<_>>();
        stack.extend(children.into_iter().rev());
    }
    CodeFileMeta {
        ast: true,
        syntax_errors,
        imports,
        symbols,
    }
}

fn fit_source(header: &str, source: &str) -> String {
    let numbered = source
        .lines()
        .enumerate()
        .map(|(index, line)| format!("{} | {}", index + 1, line))
        .collect::<Vec<_>>()
        .join("\n");
    let room = MAX_OUTPUT_BYTES.saturating_sub(header.len() + 80);
    if numbered.len() <= room {
        return format!("{header}{numbered}");
    }
    let mut end = room.min(numbered.len());
    while !numbered.is_char_boundary(end) {
        end -= 1;
    }
    format!(
        "{}{}\n[Source truncated to attachment limit]",
        header,
        &numbered[..end]
    )
}

fn parse(request: CodeFileParseRequest) -> Result<ParsedCodeFile, String> {
    if request.name.trim().is_empty()
        || request.name.chars().count() > 260
        || request.name.chars().any(char::is_control)
    {
        return Err("代码文件名无效。".into());
    }
    if request.byte_size == 0
        || request.byte_size > MAX_CODE_BYTES
        || request.content.len() > MAX_CODE_BYTES
    {
        return Err("代码文件过大。".into());
    }
    if request.mime_type.len() > 120 || request.content.as_bytes().len() != request.byte_size {
        return Err("代码文件大小校验失败。".into());
    }
    let ext = extension(&request.name);
    let (language_name, language) = grammar(&ext).ok_or("该语言尚未启用 AST 解析。")?;
    let mut parser = Parser::new();
    parser
        .set_language(&language)
        .map_err(|_| "代码语法解析器不可用。")?;
    let tree = parser
        .parse(&request.content, None)
        .ok_or("代码语法解析没有完成。")?;
    let meta = inspect(tree.root_node(), &request.content, language_name);
    let imports = if meta.imports.is_empty() {
        "- none detected".into()
    } else {
        meta.imports
            .iter()
            .map(|value| format!("- {value}"))
            .collect::<Vec<_>>()
            .join("\n")
    };
    let symbols = if meta.symbols.is_empty() {
        "- none detected".into()
    } else {
        meta.symbols
            .iter()
            .map(|value| format!("- L{} · {} · {}", value.line, value.kind, value.name))
            .collect::<Vec<_>>()
            .join("\n")
    };
    let header=format!("[Code structure · Tree-sitter AST v1]\nLanguage: {language_name}\nLines: {}\nSyntax errors: {}\nImports:\n{imports}\nSymbols:\n{symbols}\n\n[Source · {}]\n",request.content.lines().count(),meta.syntax_errors,request.name);
    let content = fit_source(&header, &request.content);
    Ok(ParsedCodeFile {
        name: request.name,
        mime_type: request.mime_type,
        byte_size: request.byte_size,
        language: language_name.into(),
        kind: "code".into(),
        parser: "tree-sitter-ast-v1".into(),
        content,
        code_meta: meta,
    })
}

#[tauri::command]
pub async fn parse_code_file(request: CodeFileParseRequest) -> Result<ParsedCodeFile, String> {
    tauri::async_runtime::spawn_blocking(move || parse(request))
        .await
        .map_err(|_| "代码解析任务未完成。".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unicode_symbols_fit_attachment_contract() {
        let name = "中".repeat(100);
        let parsed = parse(request("long.py", &format!("def {name}():\n    pass\n"))).unwrap();
        assert!(!parsed.code_meta.symbols.is_empty());
        assert!(parsed.code_meta.symbols[0].name.len() <= 200);
    }
    #[test]
    fn bom_and_jsx_remain_ast() {
        let parsed = parse(request("bom.ts", "\u{feff}export function hello() {}")).unwrap();
        assert!(parsed.code_meta.symbols.iter().any(|s| s.name == "hello"));
        assert_eq!(
            parse(request("view.jsx", "const View = () => <div>Hello</div>;"))
                .unwrap()
                .code_meta
                .syntax_errors,
            0
        );
    }
    fn request(name: &str, content: &str) -> CodeFileParseRequest {
        CodeFileParseRequest {
            name: name.into(),
            mime_type: "text/plain".into(),
            byte_size: content.len(),
            content: content.into(),
        }
    }
    #[test]
    fn parses_typescript_symbols_and_imports() {
        let parsed = parse(request(
            "main.ts",
            "import {x} from './dep';\nexport function greet(name:string){return name+x}",
        ))
        .unwrap();
        assert_eq!(parsed.parser, "tree-sitter-ast-v1");
        assert_eq!(parsed.code_meta.imports, vec!["./dep"]);
        assert!(parsed
            .code_meta
            .symbols
            .iter()
            .any(|value| value.name == "greet"));
    }
    #[test]
    fn parses_python_and_rust() {
        let python = parse(request(
            "main.py",
            "from tools import run\nclass App:\n    def start(self): pass\n",
        ))
        .unwrap();
        assert!(python
            .code_meta
            .symbols
            .iter()
            .any(|value| value.name == "App"));
        let rust = parse(request(
            "lib.rs",
            "use crate::tools::run;\npub fn start() {}",
        ))
        .unwrap();
        assert!(rust
            .code_meta
            .imports
            .iter()
            .any(|value| value.contains("crate::tools::run")));
        assert!(rust
            .code_meta
            .symbols
            .iter()
            .any(|value| value.name == "start"));
    }
}
