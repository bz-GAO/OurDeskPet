# History and attachment performance

The settings page offers presets and custom values; the existing chat search selector remains. The values below describe the lightweight default; see [settings](SETTINGS.md).

## Context and summaries

Rust owns the bounded model-context working set. The UI sends only the current question and current attachments, plus session/turn IDs; it no longer rebuilds and retransmits all historical text on every send. Full visible messages stay in the chat window until reset or process exit.

After 12 successful completed turns, the next send summarizes the oldest four and keeps eight verbatim turns. Another four completed turns make the next batch eligible. Before that threshold, the small batch awaiting summarization remains available verbatim (up to 11 completed turns), subject to the character budget. This avoids dropping unsummarized content merely to enforce a strict eight-turn count. No summary request runs merely because the app is idle.

The summary targets about 300 Chinese characters with a hard 500-character cap. Each update consumes the old summary plus newly removed text, not the whole conversation. Summary input is bounded to about 12000 characters, with bounded per-message excerpts for unusually long turns. Model context uses at most 12000 text characters, or a lower configured `OURDESKPET_CONTEXT_CHARS`; the summary occupies that budget. This is not exact token accounting and excludes character/tool instructions and current images. Long content can trigger compaction before 12 turns.

Summaries are derived conversation data at user-message priority, never system instructions. They may be lossy. Only completed replies enter the backend context; errors, cancellations and length-limited replies remain visible but are not committed. Regeneration replaces the latest completed turn rather than duplicating it.

Summary calls use the current API/model, no tools or images, a 45-second total timeout and a 1000-token output request. They are covered by the ordinary Stop/Reset cancellation path. Empty, failed, filtered or length-limited summaries fall back to recent context. A failed attempt is not immediately retried at the same history revision. After more conversation it can be tried again. The backend working set is limited to 20 turns if failures persist; full UI history is unaffected. Session/revision checks prevent obsolete summaries from being installed after reset.

## Images and rendering

An attachment is converted once from base64 to a binary Blob resource. Pending/history views and explicit reuse share its object URL. Base64 is reconstructed only for the attachments in the outgoing request; historical images do not get re-sent or reinterpreted during summarization. Reset releases object URLs. No temporary disk image store or cross-restart chat persistence has been introduced.

Historical images use lazy loading and asynchronous decoding. Completed offscreen messages use browser content-visibility so their layout/painting can be skipped; existing memoized Markdown rendering is retained. This is not full list virtualization: message records and DOM nodes still exist, and original image blobs remain while the session retains them. Future measurements can determine whether thumbnail generation or a disk-backed store is worthwhile.

User-facing setup: none required. The existing shortcut uses the updated executable. Chat settings are available; packaging remains a later agenda item.
