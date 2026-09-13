# Status and roadmap

Updated September 13, 2026. This page describes the current state; earlier discussion drafts are archived locally.

## Implemented

Transparent desktop pet and input regions; dragging and right-click sleep; four artwork states for summer and winter outfits plus the Astromeda single-image pack; three-star board controls, smile settings entry, automatic collapse, completion flashes and unread indicators; chat and settings panels; horizontally draggable two-image previews; API profiles and `.env` synchronization; code highlighting, math, and image attachments; conditional window avoidance.

The pet remains idle while waiting for the first response text, talks during streaming, and respects manual sleep until explicitly awakened. Dragging temporarily overrides the displayed artwork. Notifications are independent of the character state.

## Planned, not implemented

1. Character prompt expansion: review `research/RINA-PROMPT-RESEARCH.md` and `research/RINA-PROMPT-DRAFT.md` before activation. Character-to-prompt binding and a prompt editor are not implemented.
2. More consistent hand-drawn artwork and additional characters; walking animation for a separate fully pixel-art pack. The current hand-drawn packs retain dragging poses.
3. A stable installation directory, distribution workflow, and startup at Windows login. The general settings tab currently contains a disabled placeholder.
4. Integration with desktop translation and Japanese audio transcription/translation tools. Notification infrastructure exists; external tools are not connected.
5. Long-conversation summaries, context budgeting and persistence, model vision capability hints, and clearer network errors.
6. Further electronic-board interactions. The first star in settings is reserved. Switching the system icon with the character is not implemented.

API support currently targets the compatible chat protocol, not every provider's native API. Search, image generation, and voice remain future directions.

## Next chat improvements, in implementation order

1. **Request lifecycle:** distinguish completed, cancelled, failed, and length-limited replies; keep partial text without treating status placeholders as model context; clean up listeners and sending state even if initialization fails; add explicit retry/regenerate actions.
2. **Conversation recovery:** save the current conversation locally, restore it after reopening, and provide an explicit new-conversation action. Keep this separate from long-term character memory.
3. **Context budget:** bound outgoing history while retaining recent turns; consider summaries only after the basic budget is reliable.
4. **Image continuity:** allow explicit reuse of an earlier attachment, limit image size, and let API profiles declare vision support. Do not silently assume every model accepts images.
5. **Reading and waiting:** follow streaming output only while the reader is near the bottom; add a return-to-bottom control and configurable first-response/stream-idle waiting behavior.

In parallel, compare the behavior prompt candidate on a fixed set of everyday conversations before activation. The engineering-expert background has been removed from the active prompt and its compiled fallback; the expanded behavior candidate remains a draft.

Before a public release, review repository history for private information, decide the code license and artwork distribution scope, and add a representative screenshot. Repository visibility is controlled by the owner; no visibility change is part of this update.
