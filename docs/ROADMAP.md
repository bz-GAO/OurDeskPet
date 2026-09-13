# Status and roadmap

Updated September 13, 2026. This page describes the current state; earlier discussion drafts are archived locally.

## Implemented

Transparent desktop pet and input regions; dragging and right-click sleep; four artwork states for summer and winter outfits plus the Astromeda single-image pack; three-star board controls, smile settings entry, automatic collapse, completion flashes and unread indicators; chat and settings panels; horizontally draggable two-image previews; API profiles and `.env` synchronization; code highlighting, math, and image attachments; conditional window avoidance; in-process conversation retention; explicit reset, retry, bounded context, reader-aware scrolling and Tavily tool search.

The pet remains idle while waiting for the first response text, talks during streaming, and respects manual sleep until explicitly awakened. Dragging temporarily overrides the displayed artwork. Notifications are independent of the character state.

## Planned, not implemented

1. Character prompt expansion: review `research/RINA-PROMPT-RESEARCH.md` and `research/RINA-PROMPT-DRAFT.md` before activation. Character-to-prompt binding and a prompt editor are not implemented.
2. More consistent hand-drawn artwork and additional characters; walking animation for a separate fully pixel-art pack. The current hand-drawn packs retain dragging poses.
3. A stable installation directory, distribution workflow, and startup at Windows login. The general settings tab currently contains a disabled placeholder.
4. Integration with desktop translation and Japanese audio transcription/translation tools. Notification infrastructure exists; external tools are not connected.
5. Long-conversation summaries, optional cross-restart persistence, multiple sessions, and model vision capability hints.
6. Further electronic-board interactions. The first star in settings is reserved. Switching the system icon with the character is not implemented.

API support currently targets the compatible chat protocol, not every provider's native API. Tavily search uses its compatible tool-call interface; image generation and voice remain future directions.

## Chat follow-up

The first reliability and search pass is implemented; see [Chat sessions and web search](CHAT-AND-SEARCH.md). Validate actual provider behavior after filling the Tavily key. Continue with model capability hints and prompt comparisons before adding summaries or optional cross-restart storage. Session retention deliberately ends when the pet exits.

In parallel, compare the behavior prompt candidate on a fixed set of everyday conversations before activation. The engineering-expert background has been removed from the active prompt and its compiled fallback; the expanded behavior candidate remains a draft.

Before a public release, review repository history for private information, decide the code license and artwork distribution scope, and add a representative screenshot. Repository visibility is controlled by the owner; no visibility change is part of this update.
