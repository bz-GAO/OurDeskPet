# Development Log

This log keeps milestone-level decisions, meaningful implementation changes, verification results, and unresolved issues. Detailed early troubleshooting is intentionally condensed; exact implementation history can be recovered from code and milestone documents when needed.

## 2026-05-27

### Project Initiation

Created the project direction for OurDeskPet.

Decisions:

- Project root: `E:\OurDeskPet`.
- Main stack: `Tauri 2 + React + TypeScript + Rust`.
- Early scope: desktop pet foundation, pet state system, LLM chat, and screen-region capture.
- Courseware learning is an application scenario, not an independent early module.
- Rina-related assets from `E:\API_test\RinaChanBoard\img` can be used as early placeholders.

Created project structure:

```text
E:\OurDeskPet
  app\
  docs\
  assets\rina\
  prompts\
  skills\
  experiments\
```

Created initial management documents:

- `docs\PROJECT_PLAN.md`
- `docs\MILESTONES.md`
- `docs\FEATURES.md`
- `docs\DEV_LOG.md`
- `docs\QA_CHECKLIST.md`

Copied initial Rina assets into `E:\OurDeskPet\assets\rina`.

### M0 Project Foundation

Initialized the application in:

```text
E:\OurDeskPet\app
```

Created stack:

```text
Tauri 2
React
TypeScript
Rust
npm
```

Environment established:

- `node v24.16.0`
- `npm 11.13.0`
- `Python 3.14.3`
- `rustc 1.95.0`
- `cargo 1.95.0`
- WebView2 present
- Visual Studio Build Tools 2022 with MSVC and Windows SDK present

Useful commands:

```text
cd E:\OurDeskPet\app
npm install
npm run build
npm run tauri info
npm run tauri dev
npm run tauri build -- --debug --no-bundle
```

Verification:

- `npm install` completed.
- `npm run build` passed.
- `npm run tauri info` reported a usable environment.
- `npm run tauri dev` started the app.
- `npm run tauri build -- --debug --no-bundle` passed.

Known packaging note:

- Full installer bundling previously hit a WiX download timeout. This does not block development and belongs to M6.

Build cache policy:

- Rust/Tauri build output is disposable.
- Large Cargo target output was moved outside the app folder:

```text
E:\OurDeskPetBuildCache\cargo-target
```

## 2026-05-28

### M1 Desktop Pet Window

Implemented the first desktop pet shell.

Changes:

- Tauri window made small, transparent, borderless, always-on-top, non-resizable, and shadowless.
- Added project-local pet image using `Rina_bot_cutout.png`.
- Added hover-visible minimize and close controls.
- Added drag behavior through Tauri window APIs and `data-tauri-drag-region`.
- Added explicit Tauri window permissions for close, minimize, and dragging.
- Reduced pet/window size after user feedback.

Important asset paths:

```text
E:\OurDeskPet\assets\rina\Rina_bot.jpg
E:\OurDeskPet\assets\rina\Rina_bot_cutout.png
E:\OurDeskPet\app\public\assets\rina\Rina_bot.jpg
E:\OurDeskPet\app\public\assets\rina\Rina_bot_cutout.png
```

Verification:

- `npm run build` passed.
- `npm run tauri build -- --debug --no-bundle` passed.
- `npm run tauri dev` launched.
- User confirmed dragging, minimize, and close worked after the interaction fix.

### M2 Pet State System

Implemented a basic behavior layer.

Added:

```text
app\src\pet\types.ts
app\src\pet\usePetController.ts
app\src\pet\profiles\defaultPetProfile.ts
app\src\components\PetView.tsx
app\src\components\SpeechBubble.tsx
```

States:

```text
idle
follow
talk
sleep
```

Decisions:

- Pet body remains the drag region.
- Speech bubble is the primary compact interaction/status surface.
- Compact bubble is a status/notification/launcher, not the real chat surface.
- Real API dialogue belongs in a separate dialogue workspace window.
- Pet presentation is profile-driven so later Rina-specific components can replace the default UI.
- No character switching UI for now; replacement stays code-level.

User-confirmed behavior:

- Dragging remains comfortable.
- Hover changes status.
- Right-click toggles sleep/wake and muted visual state.

Remaining M2 checks:

- Bubble click/double-click behavior should be retested after later UI changes.

### M2 Dialogue Surface Refinement

Created a separate dialogue workspace foundation.

Changes:

- Added a dialogue window route with `/?view=dialogue`.
- Added Tauri permissions for creating, showing, focusing, and unminimizing the `dialogue` window.
- Replaced the original `>` launcher with a more recognizable expand-style diagonal-corner icon.
- Moved the launcher away from minimize/close controls.
- Simplified the dialogue workspace so it defaults to chat, not settings.
- Added `data-dialogue-theme="default"` as a future Rina Board theme hook.

Decision:

- Model, mode, API key, token usage, and advanced provider controls should live in a future management/settings surface, not in the default chat page.

Verification:

- `npm run build` passed.
- `npm run tauri build -- --debug --no-bundle` passed.
- `npm run tauri dev` launched.

### M3 LLM Text Chat

Created focused module plan:

```text
E:\OurDeskPet\docs\modules\M3_LLM_CHAT.md
```

Accepted scope:

- Minimal API-backed daily chat loop.
- OpenAI-compatible API adapter.
- File/environment based configuration.
- Streaming response display.
- System prompt support.
- Basic in-memory conversation history.
- Image payload shape reserved for M4 screenshot handoff.
- No full file assistant, no research workspace, no default settings clutter in chat UI.

Added config/prompt artifacts:

```text
E:\OurDeskPet\.env
E:\OurDeskPet\.env.example
E:\OurDeskPet\prompts\rina_system_prompt.md
```

Supported configuration:

```text
OURDESKPET_API_KEY
OURDESKPET_BASE_URL
OURDESKPET_MODEL
OURDESKPET_MODEL_OPTIONS
OURDESKPET_SYSTEM_PROMPT
OURDESKPET_PROMPT_FILE
OURDESKPET_ENV_FILE
```

Implementation:

- Rust reads local config and prompt.
- Rust sends OpenAI-compatible `/chat/completions` requests.
- Rust parses SSE streaming response and emits Tauri events:
  - `llm-chat-delta`
  - `llm-chat-complete`
  - `llm-chat-error`
- React `useDialogueChat` consumes events and updates the dialogue thread.
- Chat input supports Enter to send and Shift+Enter for newline.
- Conversation can be cleared.
- Token usage is intentionally not displayed in the chat page.

Model/provider decisions:

- Model names are provider-owned strings.
- `OURDESKPET_MODEL` is passed through as-is.
- `OURDESKPET_MODEL_OPTIONS` is only a future settings UI candidate list.
- One key/base URL may support multiple models, especially with proxy APIs.
- Future settings should separate provider credentials from active model selection.

Proxy/API follow-up:

- OFOX endpoint was reachable from Windows and returned HTTP 401 without credentials.
- A transport-layer error in the Rust client led to switching `reqwest` to native Windows TLS.
- Request/stream errors now include lower-level causes when available.

Dialogue layout follow-up:

- User confirmed API chat can run.
- Dialogue window was enlarged.
- Message thread now scrolls internally.
- Input starts compact, grows with content, caps at `148px`, then scrolls internally.

Verification:

- `npm run build` passed after M3 changes.
- `npm run tauri build -- --debug --no-bundle` passed after M3 changes.
- Browser layout check confirmed the dialogue thread and input sizing behavior.

Remaining M3 checks:

- User should confirm long real conversations are comfortable to scroll.
- Switching `OURDESKPET_MODEL` under the same key/base URL should be checked.
- A vision-capable model should be chosen before M4 image testing.

### M4 Planning Preparation

Current summarized status before M4:

- M0 complete.
- M1 implemented and manually confirmed for core desktop window controls.
- M2 implemented; compact pet/state behavior is usable, with some bubble click/double-click checks still worth retesting.
- M3 implemented enough for real API chat; remaining work is provider QA and later settings polish.

Planning direction:

- M4 should focus on screen-region selection, screenshot capture, and image handoff to the existing dialogue/LLM path.
- Start with a visible capture entry point. Earlier global-hotkey thinking was later superseded by the decision to keep shortcuts out of scope.
- Reuse the M3 image payload path instead of creating a second LLM route.
- Keep OCR, study-note generation, persistent screenshot history, and advanced annotation out of first M4 scope.

Additional M4 planning note:

- M3 already accepts image data URLs, but the dialogue UI does not yet expose image attachments.
- Advanced image compression is not a core M4 requirement; normal screen-region screenshots should first aim to remain readable and work end to end.
- M4 should include a light guard for unusually large captures, but defer heavier compression/format optimization to M5 or later unless real tests require it.
- First capture entry point should live in the dialogue window as a tool button.
- The old discarded bubble-expansion idea can be reused as a small in-dialogue tool popover for capture quick actions, not as the compact pet bubble's main behavior.
- M4 should also consider dialogue image attachment support, especially automatic screenshot attachment and clipboard image paste, so image questions can be composed naturally.

### M4 Dialogue Tool and Image Attachment Start

Started M4 implementation with the dialogue-side attachment foundation, before native desktop screenshot capture.

Implemented:

- Added image payload metadata on the frontend:
  - width
  - height
  - byte size
  - file name
- Added `fileToImagePayload` utilities for PNG/JPEG files.
- Added pending image attachment state to `useDialogueChat`.
- Allowed `sendMessage` to send images with optional/fallback text.
- Rendered sent user image thumbnails in the dialogue thread.
- Added a capture/tool button in the dialogue input row.
- Added a compact tool popover:
  - Explain
  - Ask
  - Summarize
  - Attach Image
- Added image file selection through a hidden file input.
- Added clipboard image paste handling in the dialogue textarea.
- Added pending image preview cards with remove buttons.

Design note:

- The compact pet bubble remains a status/launcher surface.
- Flexible image work lives in the dialogue workspace.
- Later desktop screenshot capture should produce the same `ImagePayload` shape and attach it to the composer.

Verification:

- `npm run build` passed.
- `npm run tauri build -- --debug --no-bundle` passed.
- Vite dialogue page returned HTTP 200.
- Browser check confirmed the dialogue tool button exists and opens the tool popover.

### M4 Dialogue UI Polish and Stop Control

Applied the first round of user feedback after manual image-message testing.

Implemented:

- Reused the send button as a state-dependent `Send` / `Stop` button.
- Added a Tauri `cancel_chat_stream` command and request-id cancellation state.
- Stream handling checks cancellation before the request, after response creation, and while reading chunks.
- Kept the input composer editable during active streaming so the next message can be drafted early.
- Added click-to-preview behavior for pending and sent image thumbnails.
- Added a larger image preview modal with a low-profile close button.
- Made pending image removal smaller and visually quieter.
- Made the pending image attachment strip horizontally scrollable for crowded image sets.
- Tightened the dialogue tool popover so the quick-action buttons are smaller.
- Added low-presence global scrollbar styling, with stronger thumb contrast only on hover.

Verification:

- `npm run build` passed.
- `cargo fmt` passed.
- `npm run tauri build -- --debug --no-bundle` passed.
- Vite dialogue page returned HTTP 200.
- Static/source checks confirmed the dialogue page has the image preview, tool popover, and `Send` / `Stop` button paths.

Remaining checks:

- User should test `Stop` during a real streaming API response.
- User should confirm the image preview size and low-profile delete button feel comfortable in the desktop window.
- Native screenshot selection is still the next M4 step; current image support covers file attach and paste.

### M4 Region Capture First Pass

Implemented the first native screen-region capture loop.

Implemented:

- Added a `/?view=capture` React view for the temporary selection overlay.
- Added a full-screen, transparent, always-on-top capture window launched from the dialogue tool popover.
- Added drag-to-select rectangle UI with live dimensions.
- Added `Escape` cancellation by closing the capture window.
- Added minimum selection rejection for tiny accidental drags.
- Added Rust `capture_screen_region` command using `xcap`.
- Encoded the selected region as PNG data URL with width, height, byte size, and `screen-capture.png` metadata.
- Hid the overlay before capture so the selected image should contain the desktop content, not the dim overlay.
- Emitted `capture-image-ready` back to the dialogue window.
- Dialogue window now attaches the captured image to the composer and prepares the default prompt.

Verification:

- `npm run build` passed.
- `cargo fmt --check` passed.
- `npm run tauri build -- --debug --no-bundle` passed after adding `xcap`.
- Vite capture view returned HTTP 200.
- Browser check confirmed `CapturePage` renders with hidden body overflow, dim background, and crosshair cursor.

Remaining checks:

- User should manually test whether the capture overlay opens above the desktop.
- User should confirm drag selection coordinates match the expected screen region.
- Multi-monitor and high-DPI behavior would matter for any custom capture surface, but global hotkeys were later removed from scope.
- Cross-monitor drag is not a target for this first pass; selection is clamped to the monitor where the drag starts.

### M4 Capture Safety Fix

User reported that the capture overlay could trap the desktop if the region selection did not complete or hand off correctly.

Implemented:

- Added an always-visible top-right cancel button to the capture overlay.
- Changed capture from auto-submit-on-release to a two-step flow:
  - drag to create a selection
  - click `Capture` to submit or `Cancel` to discard
- Kept `Escape` as a cancellation path.
- Added keyboard confirmation with `Enter` or `Space` after a selection exists.
- Added pointer-cancel cleanup.
- Added an 8-second frontend timeout around the native capture call so the overlay can close instead of leaving the user trapped if capture hangs.

Verification:

- `npm run build` passed.
- `cargo fmt --check` passed.
- `npm run tauri build -- --debug --no-bundle` passed.
- Vite capture view returned HTTP 200.
- Browser check confirmed:
  - capture page renders
  - top-right cancel button exists
  - dragging creates a selection
  - `Capture` and `Cancel` buttons appear after selection

### M4 Capture Route Change

User confirmed the custom fullscreen overlay could still trap input even after adding visible controls. The likely risk is the Windows/WebView2 combination of fullscreen, transparent, always-on-top, and custom pointer capture.

Decision:

- The custom overlay is no longer the default capture entry.
- Default capture now uses the Windows system screen clipping surface.
- The app polls the native clipboard after system clipping and attaches the resulting image to the dialogue composer.
- The custom `/?view=capture` overlay remains code-only/experimental until we have a safer window strategy.

Implemented:

- Added Rust `start_system_screen_clip`.
- Added Rust `read_clipboard_image` using `arboard`.
- Added Rust `close_capture_window` as a backend cleanup command.
- Dialogue `Capture` button now launches the system clipper instead of the custom overlay.
- Dialogue prepares the screenshot prompt and waits up to 30 seconds for a new clipboard image.
- If no image is detected, the UI reports that the user can paste manually with `Ctrl+V`.

Verification:

- `npm run build` passed.
- `cargo fmt` passed.
- `npm run tauri build -- --debug --no-bundle` passed.

Remaining checks:

- User should test whether the Windows clipper opens reliably.
- User should confirm the screenshot is automatically attached after selecting a region.
- If clipboard polling is unreliable, keep `Ctrl+V` paste as the fallback and revisit native clipboard monitoring.

### M4 Scope Closure Decision

User confirmed the Windows system clipping route works well enough for the screenshot workflow.

Product decisions:

- Treat the system clipper plus clipboard handoff as the accepted M4 capture route.
- Do not add global screenshot shortcuts to the roadmap for now.
- Keep desktop-pet scope small; the pet should not become a heavyweight system utility.
- Keep ordinary clipboard paste support as an equally valid path for users who already have a preferred screenshot tool.
- Keep `Explain`, `Ask`, and `Summarize` only as lightweight prompt templates for now, not as a major quick-action system.
- Revisit or remove those templates later if the toolbox feels visually noisy.

M4 initial status:

- M4 is considered initially complete after user validation of system capture.
- Remaining work is polish/fallback refinement, not core milestone completion.
- The custom fullscreen overlay remains experimental and should not be revived without a safer window strategy.

### Post-M4 Optimization Planning

User noted that the main functional layers are now implemented and future work should become reliability, art, and capability optimization rather than more large feature layers.

Added:

- `docs\modules\OPTIMIZATION_PACKAGES.md`

Optimization packages:

- R1 Reliability and Long-Conversation Management.
- A1 Art and Pet-State Presentation.
- L1 LLM Capability Expansion.
- M4P Screenshot and Image Polish.
- S1 Settings and Management Surface.

Current chat-context note:

- The app sends text history from the current in-memory dialogue session.
- The initial assistant placeholder and error messages are excluded.
- Historical images are not repeatedly resent; image payloads attach to the latest user request.
- There is no token estimation, truncation, or summary memory yet.

Recommended next package:

- Start with R1, especially long-context summarization, because long real conversations can otherwise grow unbounded.

### Documentation Organization Pass

Reviewed project Markdown files and chose a centralized documentation layout.

Decision:

- Project management documentation stays under `docs`.
- Module/milestone plans stay under `docs\modules`.
- Artifact-specific Markdown stays next to the artifact only when it is directly useful there:
  - `app\README.md`
  - `assets\rina\README.md`
  - `prompts\rina_system_prompt.md`

Implemented:

- Added `docs\README.md` as the documentation index.
- Added `docs\modules\README.md` as the module-plan index.
- Replaced the default Tauri `app\README.md` with project-specific app notes and commands.
- Updated `assets\rina\README.md` to reflect the current placeholder and future A1 state-image naming.
- Updated `PROJECT_PLAN.md` with documentation organization rules.
- Updated `QA_CHECKLIST.md` documentation checks.

Notes:

- `prompts\rina_system_prompt.md` is valid UTF-8 Chinese content. Some PowerShell reads may display it incorrectly unless UTF-8 output is selected.
- `node_modules` Markdown files are dependency docs and should be ignored for project documentation review.

### GitHub Preparation Pass

Prepared the project for a possible GitHub upload without creating a remote or pushing.

Implemented:

- Added root `README.md` for the future GitHub repository page.
- Expanded root `.gitignore` for secrets, build output, caches, logs, editor files, and local Python environment.
- Added `.gitattributes` for stable text normalization.
- Added `docs\GITHUB_PREP.md` with first-publish checklist and suggested commands.
- Linked `GITHUB_PREP.md` from `docs\README.md`.
- Initialized a local Git repository at `E:\OurDeskPet`.
- Renamed the local branch to `main`.

Verification:

- `git status --short --ignored` shows `.env`, `.venv`, `node_modules`, `dist`, and `logs` ignored.
- `git ls-files --others --exclude-standard` lists the files that would be considered for the first commit.
- Sensitive-pattern scan found only example variable names and code references, not a real API key.

Remaining before publishing:

- Decide whether the repository should be private or public.
- Review Rina image asset rights before a public repository.
- Create the GitHub repository and add the remote.
- Stage, commit, and push.
