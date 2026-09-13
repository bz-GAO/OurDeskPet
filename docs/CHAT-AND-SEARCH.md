# Chat sessions and web search

## Session behavior

Closing the dialogue hides its native window. Messages, drafts, attachments and an in-progress response remain in memory until the pet process exits. Reopening restores that same window. **Reset conversation** asks for confirmation; it cancels any active request before clearing the conversation. No chat log is written to disk, and restarting the process starts a fresh conversation.

Replies distinguish completion, cancellation, errors and output-length limits. Partial text remains readable, but incomplete assistant replies are excluded from later model context. Retry reuses the latest user turn without duplicating it. Older attachments can be explicitly reattached; historical images are not silently resent.

Outgoing text history keeps recent complete user turns within a configurable character budget. Older turns remain visible in the UI, with a notice when omitted from the API request. This is an approximate text budget, not token counting or automatic summarization. Images are limited to four PNG/JPEG files per request, 5 MiB each and an 8192-pixel maximum edge. The selected model must support image input.

Streaming follows new content only while the reader is near the bottom. A return-to-latest button appears after scrolling up. Chinese IME composition does not submit on Enter.

## Configuration

Add these fields to the existing root `.env`; `.env.example` documents the same defaults:

```dotenv
TAVILY_API_KEY=
OURDESKPET_SEARCH_ENABLED=true
OURDESKPET_TAVILY_BASE_URL=https://api.tavily.com
OURDESKPET_CONTEXT_CHARS=24000
OURDESKPET_READ_TIMEOUT_SECS=180
```

Only the Tavily key needs filling for the standard endpoint. Configuration is refreshed before each request, so manual file changes are read without restarting. Existing API profile credentials remain separate. Never commit the real `.env`.

Read timeout accepts 15–600 seconds and measures waiting for network reads; chat connection timeout is 20 seconds. Text budget accepts 4000–100000 characters. Search uses a 25-second overall timeout and does not automatically retry.

## Search behavior

The persistent mode selector offers **Auto**, **Off**, and **Required**. Auto exposes an OpenAI-compatible `web_search` function: the model decides whether current or uncertain facts need verification, or follows an explicit search request. Off sends no tools. Required forces the first search call and reports a clear error if the model ignores it. A blank key disables search; ordinary chat remains available in Auto/Off.

The model returns a structured tool call, the backend queries Tavily, and the model then answers with the returned evidence. A separate system instruction specifies the current date, when to search, source citation, and how to handle unavailable evidence. The character behavior draft is not activated by this feature.

Each user turn permits at most two searches and three model calls. Repeated identical queries are skipped. Results contain at most five sources per search with bounded excerpts. Search errors and empty results remain visible; retrieved sources have a collapsible list. Sources are evidence, not instructions. Only query text goes to Tavily; the complete conversation is not sent to the search provider. The chosen chat provider receives the excerpts needed for the answer.

Providers must support the compatible tools/tool_calls protocol. If an endpoint rejects it, switch search Off or choose a compatible model. Reasoning fields needed by some providers are retained only inside the active tool round and are not rendered in chat. This is not a guarantee of compatibility with every provider.

## Validation and remaining work

Rust tests cover fragmented SSE/tool arguments, stream failure detection, search arguments and bounded source parsing. `node tests/chat-context.test.mjs` covers history budgeting, incomplete-reply exclusion and attachment limits. Native WebView testing uses local simulated model/search endpoints, avoiding real credentials or search charges.

Still separate work: optional cross-restart chat persistence, multiple sessions, history summaries, model vision capability declarations, and a search-key settings editor. Search currently uses `.env` configuration.

Final verification (September 13, 2026): production build, 21 Rust tests, context tests, artwork/notification/Markdown regressions, and 16 native workflow assertions passed. Native checks include hidden-window completion, draft retention, search cancellation/failure/budget, retry, reset, fresh process state, missing keys, unsupported tools, reasoning-field round-trip and non-overlapping search controls. The local QA script/results/screenshot are archived outside Git; live Tavily/provider validation awaits the user's key.

