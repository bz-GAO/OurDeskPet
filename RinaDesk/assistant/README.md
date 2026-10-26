# Project assistant knowledge

These concise documents are the built-in product guide for Chat's project-assistant
mode. They describe supported behavior and stable UI concepts; they are not executable
instructions and do not grant tools or permissions.

Keep end-user guidance here short and current. Detailed implementation and operational
notes remain in `docs/`. Each topic may name stable navigation targets for a future
validated action-card layer, but Chat must never execute a target merely because it
appears in generated text.

The optional source reader is separate from this guide. It uses a deterministic allowlist,
requires explicit user permission, and excludes settings, credentials, media, caches and
build output.

## Keeping guidance current

Product references are refreshed on every project turn and project_help call, before the first
model response. The fixed registry reads Desk's workspace/chat/extensions topics here and
`docs/ASSISTANT.md` from the currently resolved Yaki/Tomo projects. Only those five files are
automatically read, at most 12 KiB each. No recursive document discovery, persistent index or
filesystem watcher is used. Empty, oversized, invalid UTF-8, linked or missing guides fall back
individually to compiled references, explicitly marked `bundled_fallback` with a reason.

Each reference reports its project, relative path, live/fallback source and content revision.
The revision detects content changes; it is not a cryptographic signature. The workspace overview
and up to three relevant topics accompany the first response. References enter as data, never
system policy; arbitrary Markdown links cannot trigger further reads. Source-read permission
is independent: it controls model-requested source listing/reading, not this fixed product help.
Ordinary Chat does not load these guides. The assistant skill/tool permissions remain compiled.

Source tools resolve project locations afresh on every call. Desk uses the runtime anchor,
Yaki uses its extension registration without launching Python, and Tomo uses the launcher's
sibling-project resolver. Unavailable roots fail closed; no old checkout/global disk search.
Source reads report a content revision and use the same bounded reader as guides. On Windows,
the opened file handle's final path is verified as well as the path components. No cache is
used for source contents. New source or guides do not prove a running executable was rebuilt.

When changing a user-facing feature, update its topic here and the corresponding detailed
documentation. For Yaki/Tomo, update their own `docs/ASSISTANT.md` and the concise bundled backup
under topics/ when preparing a Desk release. Update BUNDLED_REVIEWED in project_agent/guides.rs
when reviewing backups. Live guide edits apply to the next question without restarting Desk;
code cannot automatically rewrite accurate documentation. Run the project_agent tests when
changing the reader, routing or root resolution. Keep roadmap items explicitly labeled and
do not put local paths, login state or user configuration in any product guide.

Design references: [MCP roots](https://modelcontextprotocol.io/specification/2025-06-18/client/roots)
for explicit project boundaries, and [VS Code custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
for request-time project context. This implementation does not add an MCP server or execute
repository instructions; backend allowlists enforce the boundary.
