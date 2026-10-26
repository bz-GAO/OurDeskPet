# Runtime prompts and skills

The active character prompt is `rina_system_prompt.md`. Further behavior edits belong in that file; old prompt versions remain available through Git history instead of living beside the runtime source.

Assembly order: character prompt, common tool policy, enabled runtime skills, then conversation messages. The application registers each tool explicitly. Search loads `skills/web-search/SKILL.md` only when available; project-assistant mode loads `skills/project-assistant/SKILL.md` and its bundled guide, plus an optional source reader when the user grants permission. Common behavior lives in `tool_policy.md`. Skill YAML metadata is not sent to the model.

These are project runtime resources, not an installation into Codex. New files are not discovered or executed automatically. To add a tool, implement and register its schema, validated executor, cancellation/limits and tests, then explicitly add the matching skill to the runtime selection. Search and project guidance can be composed in one Chat turn. Prompt text cannot enforce request budgets or grant permissions: Rust remains responsible for these boundaries.

Character files are read at request time using the existing configuration precedence: `OURDESKPET_SYSTEM_PROMPT`, explicit prompt-file configuration, project/default prompt, compiled fallback. Explicit overrides are preserved. Tool policy/skills are compiled into the executable, so editing them requires rebuilding; runtime hot loading is not implemented. This keeps packaged behavior independent of the working directory.

The character prompt controls voice and relationships. Tool skills control when and how to use actual capabilities. Keep API keys, endpoints, UI state transitions and network implementation out of character prose. Search results remain untrusted data.

Developer checks: from `app`, run `npm test` for frontend regressions or `npm run check` for those tests, the frontend build and Rust tests. Windows checks require the documented Rust/Windows SDK toolchain. This does not change the end-user shortcut.

Character behavior quality remains subject to user feedback in ordinary conversation.
