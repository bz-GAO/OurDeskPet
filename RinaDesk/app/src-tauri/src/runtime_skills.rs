//! Explicit, compiled runtime skills; never execute arbitrary skill folders.
const COMMON: &str = include_str!("../../../prompts/tool_policy.md");
const WEB_SEARCH: &str = include_str!("../../../skills/web-search/SKILL.md");
const PROJECT_ASSISTANT: &str = include_str!("../../../skills/project-assistant/SKILL.md");

fn body(document: &str) -> &str {
    document
        .strip_prefix("---")
        .and_then(|rest| rest.split_once("---"))
        .map(|(_, body)| body.trim())
        .unwrap_or(document.trim())
}

pub fn policy(search_available: bool, project_mode: bool, source_read_available: bool) -> String {
    let search = if search_available {
        body(WEB_SEARCH)
    } else {
        "Web search is unavailable for this turn. Do not claim to have browsed or verified current facts. Explain the limitation when verification is necessary."
    };
    let project = if project_mode {
        format!(
            "{}\n\n{}",
            body(PROJECT_ASSISTANT),
            if source_read_available {
                "Current project guide excerpts (or explicitly marked bundled fallbacks) are already attached. The project_help, read_project_file and list_project_files tools are available for further lookup. Locate relevant files and cross-check their line ranges as needed. Budget: 12 project tool calls including guide, listing, reads and failed attempts; at most 8 model rounds. Reserve room for the answer."
            } else {
                "Current project guide excerpts (or explicitly marked bundled fallbacks) are already attached. Source-file reading is not authorized for this turn. Answer from the guide without calling project tools for source reads, and say when implementation detail cannot be verified. project_settings may still be supplied for safe proposals; its executor enforces a separate permission and it does not grant source access."
            }
        )
    } else {
        "Project-assistant mode is off. Do not call project tools or imply access to project guidance or source files. If the user's request clearly needs project source reading, engineering operations, or Desk settings changes, call the suggest_project_mode tool once and briefly tell the user they can jump to project-assistant mode. Settings boundary: bounded Desk chat options (contextChars, readTimeout, searchMode, searchEnabled, startupEnabled) can be proposed only in project-assistant mode; Yaki and Tomo settings are changed in their own panels, never by you.".into()
    };
    format!("{COMMON}\n\n{search}\n\n{project}")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strips_metadata_with_both_line_endings() {
        for newline in ["\n", "\r\n"] {
            let doc = [
                "---",
                "name: example",
                "description: example",
                "---",
                "Use the actual tool.",
            ]
            .join(newline);
            assert_eq!(body(&doc), "Use the actual tool.");
        }
        assert_eq!(body("Plain policy"), "Plain policy");
    }
    #[test]
    fn unavailable_tools_do_not_load_their_skill() {
        assert!(policy(true, false, false).contains(body(WEB_SEARCH)));
        assert!(!policy(false, false, false).contains(body(WEB_SEARCH)));
        assert!(policy(false, false, false).contains(COMMON));
    }
    #[test]
    fn project_skill_and_permission_are_explicit() {
        assert!(policy(false, true, false).contains(body(PROJECT_ASSISTANT)));
        assert!(policy(false, true, false).contains("not authorized"));
        assert!(policy(false, true, true).contains("list_project_files tools are available"));
        assert!(policy(false, true, false).contains("without calling project tools"));
        assert!(!policy(false, false, false).contains(body(PROJECT_ASSISTANT)));
    }
}
