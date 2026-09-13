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
