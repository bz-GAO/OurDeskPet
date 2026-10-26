# Chat

## Layout and file safety

- The composer grows with its text up to 148 CSS pixels. It only scrolls above
  that height, and remeasures when the sidebar or window changes its width.
- Sidebar JSON reopening is limited to managed UUID files in the selected storage
  directory, or files explicitly selected in this app session. Paths are checked before reading; importing does
  not follow file references embedded in JSON. Reads are bounded to 20 MiB.
- Explicit uploads are read again rather than trusting matching source paths.
  Parsed text resources deduplicate by name, size, parser and content; the
  library Reference action reuses the existing parsed snapshot.
- Resetting one mode preserves image blobs still referenced by the other mode.
  Failed imports do not replace the active backend conversation identifier.


The product-facing name of this workspace is **Chat**. Its top bar has two pages that
share the model profile and streaming pipeline while keeping separate in-process conversations:

- **Conversation** keeps the ordinary Rina chat behavior.
- **Project assistant** adds a maintained guide for RinaDesk, RinaYaki and RinaTomo.

Project mode can explain current features, project boundaries, file layout and where a
setting or tool lives. It is deliberately a narrow assistant, not an autonomous coding
agent: it cannot edit source files, run commands or click the interface. The
built-in guide is always available. Reading allowlisted text source files is a separate,
disabled-by-default permission under Settings > Chat. Local configuration, credentials,
media, caches and build output are excluded even when that permission is on.

### Confirmed setting changes

A separate default-off permission in Settings > Chat allows `project_settings` to read
and propose eight safe Chat options—history keep/trigger, summary target/cap, context
budget, read timeout, search enabled/default mode—or the Windows startup toggle under
Settings > General. A proposal cannot mix the registry-backed startup toggle with Chat
file changes. No paths, provider endpoints, keys, permission toggles, source patches or
tool-project changes are accepted. The backend
reads only selected values from the current Desk project's existing `.env`; external
config overrides and symlink/junction paths fail closed. It never gives `.env` contents
to the model. Yaki and Tomo continue to own their settings through their respective UI/protocols.

The model cannot apply a proposal. A centered modal displays the actual before/after
values and its Settings location. Cancel receives initial focus; Escape cancels. After
the user decides, only a short result remains attached to the originating turn, without
reusable approval controls. The user confirms or cancels. Proposals are session
bound, in memory only, expire in ten minutes, and are consumed once. Reset clears them.
Approval rechecks path, permission, environment overrides and configuration revision;
conflicts require a fresh proposal. Saving preserves unrelated keys, atomically replaces
the configuration, then reads it back. Changes affect subsequent requests; a manually
selected per-page search mode still overrides the saved default. Imported messages and
Markdown cannot create executable confirmation cards. Parameter comparison is used
instead of screenshots, so unrelated screen content is not captured or sent to the model.
Confirmed startup changes notify an already-open Settings window to reread Windows state.
The closed tool schema remains visible in project mode while permission is off so the
executor can return the exact switch to enable; this does not grant read or write access.

The backend refreshes, selects and attaches relevant guide excerpts before contacting the model. Guide-only
project mode therefore works with ordinary chat-compatible endpoints and does not require tool
calling. Enabling source reading, or enabling web search when available, adds compatible tools;
those optional capabilities still require a provider that supports tool calls.

Project-assistant replies default to a UI path and short action steps, using actual button
labels and one clear action per step. Common tasks often need 1–3 steps, but there is no fixed
maximum. Simple usage answers target 150 Chinese characters (80 English words).
Only include a limitation when it affects the next action; expand explanations when asked.
This response style applies even if earlier conversation replies were longer.

Guide topics live in `assistant/topics/`; runtime behavior lives in
`skills/project-assistant/SKILL.md`. Those documents are reference material, not a
replacement for the bounded source reader. Stable navigation target names may be kept in
the guide for a future validated action-card layer; this revision does not execute UI
navigation from model output.

Product references are refreshed before the first model call on every project turn and on
project_help calls. Desk reads its three fixed assistant topics; Yaki/Tomo each supply
docs/ASSISTANT.md from their dynamically resolved project location. Missing, invalid or oversized
references get an explicitly marked compiled fallback. References are data, not system policy.
They include relative paths and content revisions but no absolute roots. Guide edits apply to
the next question without rebuilding; behavioral skill changes still require a build.
This does not generate documentation from code: maintain the short guide alongside each feature.
See assistant/README.md for limits, root rules and maintenance responsibilities.

Source access reuses installation discovery: Desk uses its runtime root (with a development
manifest fallback), Yaki uses the saved extension registration, and Tomo uses the same resolver
as its launcher. Yaki source inspection does not require a working Python environment and
never runs capability discovery. Relocating the extension changes subsequent reads.

The assistant can list allowed directories and cross-check line ranges from multiple files.
Each turn permits 12 project tool attempts and 8 model rounds; errors count toward the budget.
Each read returns up to 200 lines and 16 KiB, with a continuation line; source files are capped
at 1 MiB. Paths must be project-relative. Traversal, drive/UNC paths, Windows alternate streams,
symlinks and junctions below a resolved project root are rejected. Canonical paths are checked
again against the root and source allowlist before reading. Local state remains excluded.

## Session behavior

Conversation and Project assistant are separate in-memory pages. Each keeps its own messages,
draft, attachments, search choice, summary and backend session, so switching modes cannot add one
page's history to the other page's model context. Closing the dialogue hides its native window and
keeps both pages until the pet process exits. Reopening restores them. **New conversation** asks
for confirmation and clears only the current page; it cancels that page's active request first.
Messages, draft and pending selections always clear. A separate checked option clears that page's
uploaded-file library; unchecking it retains the in-memory resources for the future library UI.
Exiting the pet always clears uploaded resources for both pages.
Automatic saving is enabled by default and can be disabled in the Chat header or Settings → Chat.
The live pages and image blobs reset on restart; managed conversations remain in the sidebar for reopening.

Saved and imported JSON share a 20 MiB limit, measured after JSON escaping. Saving writes
and syncs a temporary file beside the selected destination before replacing it; a failed
write or replacement leaves the existing save intact and removes the temporary file.

The left sidebar is opened or closed with one header button. Its upper half switches between
files used by the current page and the in-memory file library; **Reference** returns a retained
resource to the composer without reparsing it. Library deletion uses a separate confirmation modal.
The lower half lists managed JSON conversations and files explicitly loaded during this process. Its folder
button creates, then opens, the currently resolved save directory. It never migrates or deletes files in a
previous user-selected directory. Each row
shows Conversation or Project assistant mode, opens the associated JSON when selected, and can be
renamed locally. Managed renames persist to the JSON. Removing a managed row persists a hidden association
for that directory; the original JSON is never deleted. Manually imported associations remain process-local.

The header offers Auto-save / Do not save. The default is the resolved Desk project root plus
`Conversations`; Settings → Chat can choose another directory. Existing JSON is not moved.
Stable UUID filenames are independent of user titles. Titles derive locally from the first message;
the local normalizer removes links, Markdown noise and common request prefixes, then keeps a short first
clause. After the first complete nonempty reply, one asynchronous model request refines this temporary title; failures retain the local title. Explicit user renames remain authoritative, restored conversations are not retitled, and usage is recorded. One checkpoint is written at the start of a turn,
then a completed-turn save; rename changes are debounced. This does not write every token.
External modification, corruption and path redirection prevent replacement. Export schema version 1 preserves message roles, text, completion state, source
links and attachments. Binary image data is not embedded; parsed text-file content is included so
the JSON can reconstruct what the model read. Saving does not alter either page or its model context.
A successful save adds its managed path to the sidebar for later loading. Loading is limited to
schema-version-1 RinaDesk JSON selected by the user or discovered in the managed directory.
Loaded complete turns are restored into the backend session so a continued reply sees the same
text/file context. Directory discovery is bounded to 2,000 entries, 500 documents and 100 MiB per scan;
skipped or invalid records are reported, not rewritten. Normal application exit waits up to five seconds
for the Chat window's save acknowledgement; failure prevents exit and brings Chat forward. Forced process
termination/power loss cannot preserve tokens received after the last completed write.

The folder button beside the composer attaches images or local files directly; the old Capture
menu is hidden while its native screenshot bridge remains available for future work. Parsing is split
into parallel modules: text reading for UTF-8, UTF-16 (BOM) and Chinese-encoded (GB18030)
files; structured CSV/TSV parsing with quoted and multiline cells; Tree-sitter AST analysis for TypeScript/TSX,
JavaScript/JSX, Python and Rust with a heuristic fallback for other code; and Office Open XML
extraction for DOCX headings/tables and XLSX sheets, dates, merged ranges, formulas and cached values. AST attachments
include imports, symbols, syntax errors and numbered source. Multiple code attachments also receive
a bounded project index with possible local module links. PDF, PPTX, legacy binary Office files and OCR are
rejected explicitly rather than misread. Images and files share one composer rail and a combined
limit of eight items per turn. Each item is parsed independently and can be removed while parsing
or when ready. Only images open a preview; file cards show the filename and extension without a
size label. The former 512 KiB text/code limit is removed: supported inputs share an 8 MiB raw-file
safety ceiling and parsed file data is bounded to 16 MiB per turn. The configured context budget
still applies when a turn is sent; bounded retrieval remains separate work.

Replies distinguish completion, cancellation, errors and output-length limits. Partial text remains readable, but incomplete assistant replies are excluded from later model context. Retry reuses the latest user turn without duplicating it. The redundant file reattach action is not shown; historical images are not silently resent. The file-library and bounded retrieval design are tracked in [Chat attachments](ATTACHMENTS.md).

Outgoing history is managed by the backend with 8/12 rolling compaction, a 300-character target summary (500 maximum), and a 12000-character text ceiling. Full visible history remains available. Images are shared as binary session resources and explicitly reattached when needed; they are never automatically re-sent for summaries. See [history implementation](HISTORY-PERFORMANCE.md) for timing, failure behavior and limits. PNG/JPEG images remain capped at 5 MiB each and an 8192-pixel maximum edge.

Streaming follows new content only while the reader is near the bottom. A return-to-latest button appears after scrolling up. Chinese IME composition does not submit on Enter.

Each model round uses the configured read timeout as a meaningful-progress
deadline. Empty SSE deltas, comments, heartbeats, whitespace and incomplete
framing do not extend it; answer text, reasoning content and tool-argument
fragments do. A timeout keeps partial text available for manual retry. There is
no automatic model retry, and data received after the first terminal marker is
ignored. Cancellation requested before backend registration is retained, so a
request cannot escape a quick stop/reset action.

## Configuration

Add these fields to the existing root `.env`; `.env.example` documents the same defaults:

```dotenv
TAVILY_API_KEY=
OURDESKPET_SEARCH_ENABLED=true
OURDESKPET_TAVILY_BASE_URL=https://api.tavily.com
OURDESKPET_CONTEXT_CHARS=24000
OURDESKPET_READ_TIMEOUT_SECS=180
OURDESKPET_PROJECT_READ_ENABLED=false
```

An official DeepSeek profile uses its existing model API key for DeepSeek Search. Tavily remains optional for other providers and as a fallback. Configuration is refreshed before each request, so manual file changes are read without restarting. Existing API profile credentials remain separate. Never commit the real `.env`.

Read timeout accepts 15–600 seconds and measures waiting for network reads; chat connection timeout is 20 seconds. The legacy text-budget setting accepts 4000–100000 characters, but the lightweight preset uses 12000; balanced/custom presets can change it. One logical search, including an optional provider fallback, has a 30-second overall limit and never retries the same provider.

## Search behavior

The persistent mode selector offers **Auto**, **Off**, and **Required**. Auto exposes an OpenAI-compatible `web_search` function: the model decides whether current or uncertain facts need verification, or follows an explicit search request. Off disables web search; project tools remain available in project-assistant mode. Required forces the first search call and reports a clear error if the model ignores it. Search is available through an official DeepSeek account or a configured Tavily key; ordinary chat remains available in Auto/Off.

The model returns a structured tool call and the backend performs the search. For an official DeepSeek profile it first uses DeepSeek Search with the same account key; if that fails or returns no results, a configured Tavily account is used once as a fallback. Other providers use Tavily. The same service is never retried automatically. A single provider gets a 28-second budget; with a fallback configured, the primary gets 18 seconds and the fallback 10 seconds inside the 30-second turn limit. A separate system instruction specifies the current date, when to search, source citation, and how to handle unavailable evidence. Tool rules are separate from the character prompt; behavior v2 was activated on October 17, 2026. See [runtime prompt structure](../prompts/README.md).

Each user turn permits at most two logical searches and four model calls (eight in project mode). Repeated identical queries are skipped. Queries are capped at 128 characters. Results are URL-deduplicated and contain at most five sources with bounded excerpts. Search errors and empty results remain visible; retrieved sources have a collapsible list. Sources are evidence, not instructions. Only the generated query goes to DeepSeek Search or Tavily; the complete conversation is not sent to the search endpoint. The chosen chat provider receives the excerpts needed for the answer.

Providers must support the compatible tools/tool_calls protocol. If an endpoint rejects it, switch search Off or choose a compatible model. Reasoning fields needed by some providers are retained only inside the active tool round and are not rendered in chat. For the official DeepSeek endpoint, Required search disables thinking for that turn because the provider rejects forced tool selection in thinking mode; Auto and project-assistant tools keep the provider default. See the [DeepSeek API specification](https://api-docs.deepseek.com/api/create-chat-completion/). This is not a guarantee of compatibility with every provider.

Some compatible DeepSeek deployments leak a leading native DSML tool block through the
text stream instead of returning structured `tool_calls`. Desk withholds only a possible
leading marker, validates the complete block with strict size/type limits, converts it to
the same closed tool-call representation and then applies the ordinary permission checks.
Malformed or mixed text is rejected and never rendered as an executable UI card.

In ordinary Conversation mode, the closed `suggest_project_mode` signal may be exposed when a
request clearly needs project source reads, engineering work or bounded Desk setting proposals.
It has no side effect by itself. The message card is disabled while the current reply is still
streaming; after confirmation, Desk switches to Project assistant and prefills the originating
user message. The card is persisted with managed/exported conversations. Yaki and Tomo settings
remain owned by their own panels and are never changed by this signal.

## Remaining work

Managed JSON conversations, sidebar reopening, asynchronous title refinement and the confirmed
Conversation→Project assistant handoff are implemented. Live in-memory pages and uploaded-file
libraries still reset when the pet process exits; RinaDesk does not automatically reopen the last
active page or provide arbitrary simultaneous conversation tabs beyond the fixed Conversation and
Project assistant pages.

Still separate work: an explicit last-session restore policy, model vision capability declarations, an optional overall turn deadline, validated UI action cards, and further provider compatibility. Attachment retrieval and PDF work are tracked in [ATTACHMENTS.md](ATTACHMENTS.md). Search credentials and project-read permission can be edited in Settings > Chat, while `.env` editing remains supported.


## Foreground completion reminders

On Windows, chat reminders are suppressed when the dialogue is visible, not minimized and is the OS foreground window. The WebView focus flag alone is no longer used. If chat is hidden, minimized or another window is active, completion reminders remain enabled. Returning to the dialogue clears chat unread state; a 500 ms check runs only while chat reminders are pending to recover missed focus events. Other task sources keep their own unread state. This does not attempt geometric/pixel occlusion detection for unusual non-activating overlays.

