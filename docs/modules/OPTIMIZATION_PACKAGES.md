# Optimization Packages

Last updated: 2026-05-28

After M0-M4, the main functional layers are in place:

- desktop pet shell
- pet state system
- OpenAI-compatible dialogue
- image attachment and screenshot handoff

Future work should be organized as small optimization packages rather than large new feature milestones. Each package should stay independently useful and testable.

## R1 Reliability and Long-Conversation Management

Purpose:

Make the existing app safer and more comfortable during real use.

Scope:

- Long-context management for chat history.
- Summarize older conversation turns when the conversation reaches a configurable threshold.
- Keep recent turns verbatim and send older content as a compact summary.
- Avoid resending historical images; images should stay attached only to the relevant user message unless a future feature explicitly needs memory.
- Provider/model capability hints, especially whether a model supports image input.
- Better error text for common provider failures:
  - model does not support vision
  - payload too large
  - API key/base URL/model mismatch
  - network or proxy failure
- Debug logging for LLM requests, without logging secret keys.
- Review Stop/cancel behavior during real streaming responses.

Current context behavior:

- The app currently sends text history from the current in-memory dialogue session.
- The initial assistant placeholder is excluded.
- Error-state messages are excluded.
- Images are only attached to the latest user request through the `images` payload.
- There is no token estimation, truncation, or summary memory yet.

Suggested first task:

Implement conversation summarization when the text history grows beyond a simple message-count or character-count threshold. Start with character count before token estimation, because it is easier to test and good enough for first reliability work.

Exit checks:

- Long conversations do not grow unbounded.
- The summary is visible enough for debugging, but not intrusive in the chat UI.
- Recent user/assistant turns remain verbatim.
- A normal short conversation is unchanged.
- `npm run build` and Tauri debug build pass.

## A1 Art and Pet-State Presentation

Purpose:

Let the pet look different across states without rewriting behavior logic.

Scope:

- Expand the pet profile so each state can choose an image:
  - idle
  - hover/follow
  - dragging
  - sleep
  - talk/dialogue-open
  - notification/message-ready, if needed later
- Define asset naming and replacement rules under `assets\rina`.
- Keep static image swapping as the first implementation.
- Defer animation, spritesheets, and Live2D-style rendering until static replacement works well.
- Keep character switching UI out of scope until the profile structure is stable.

Dependency:

- User will provide or approve the required Rina images.

Exit checks:

- Missing state images fall back gracefully.
- Replacing a file in `assets\rina` is enough to update the pet appearance after rebuild or reload.
- Dragging and window controls still work.
- Pet state logic remains separate from presentation data.

## L1 LLM Capability Expansion

Purpose:

Add useful assistant abilities without bloating the desktop pet surface.

Scope:

- Search module inspired by the prior Board project, likely as an explicit tool or mode rather than default behavior.
- Image-generation/drawing module, if a provider and UI route are chosen.
- Better image-task templates:
  - explain screenshot
  - extract visible text
  - summarize screenshot
  - answer a question about screenshot
- Reuse proven logic from the Board project where it fits:
  - streaming parsing
  - response cleanup
  - model list patterns
  - provider-specific request shape notes
- Keep token/cost display out of the chat surface; reserve it for a future management/settings UI.

Design rule:

Do not turn the compact pet or chat input into a crowded control panel. New capabilities should enter through a clear tool surface or future management window.

Exit checks:

- Normal chat remains simple.
- Search/drawing/image tools are explicit and understandable.
- Provider failures are readable.
- No API key or sensitive config is displayed casually in the chat UI.

## M4P Screenshot and Image Polish

Purpose:

Polish the already-working M4 screenshot path.

Scope:

- Keep Windows system screen clipping as the accepted route.
- Keep manual `Ctrl+V` image paste as an equally valid path.
- Do not add global screenshot shortcuts.
- Decide whether `Explain`, `Ask`, and `Summarize` prompt templates should remain visible, be folded into a smaller menu, or be removed.
- Improve image payload size warnings only if real provider tests show a problem.
- Quarantine or remove the experimental custom fullscreen overlay code later.

Exit checks:

- Capture button opens Windows clipping reliably.
- Canceling the system clipper never traps input.
- Captured image attaches to the composer.
- Pasted image attaches to the composer.
- Vision-capable model can answer a screenshot prompt.

## S1 Settings and Management Surface

Purpose:

Move configuration and diagnostics out of the chat surface.

Scope:

- API key update flow.
- Base URL and model selection.
- Model option list per provider/key.
- Token/cost/debug information.
- Pet position or behavior preferences.
- Possibly a small management window opened from the pet or dialogue.

Timing:

This is useful, but it should probably come after R1 unless configuration pain becomes the main bottleneck.

Exit checks:

- Chat UI stays clean.
- API key is never displayed after saving.
- Model/base URL changes are explicit and testable.
- Settings persist across restarts.

## Suggested Priority

1. R1 Reliability and Long-Conversation Management.
2. M4P Screenshot and Image Polish, only if new screenshot issues appear.
3. A1 Art and Pet-State Presentation once image assets are ready.
4. L1 LLM Capability Expansion.
5. S1 Settings and Management Surface.

This order can change based on pain points during real use.
