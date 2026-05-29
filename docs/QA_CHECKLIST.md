# QA Checklist

Last updated: 2026-05-28

This checklist should grow with the project. Every milestone should leave behind checks that can be repeated later.

## General Project Checks

- [x] Project root exists at `E:\OurDeskPet`.
- [x] Main source lives under `E:\OurDeskPet\app`.
- [x] Planning documents are under `E:\OurDeskPet\docs`.
- [x] Module-level plans can live under `E:\OurDeskPet\docs\modules`.
- [x] `docs\README.md` indexes project management documents.
- [x] `docs\modules\README.md` indexes module-level plans.
- [x] Asset replacement point exists at `E:\OurDeskPet\assets\rina`.
- [x] Development commands are documented in `DEV_LOG.md`.
- [x] Any new dependency is documented or clearly visible in project config.
- [x] Project-local environment strategy is followed.
- [x] Large build caches are treated as disposable output, not source.
- [x] Rust/Cargo target output is cleaned or moved outside `app` when it grows too large.
- [ ] Build cache cleanup is considered after each completed milestone.
- [x] Pet presentation has a code-level replacement boundary before M5 art work.

## M0: Foundation Checks

- [x] App project is initialized.
- [x] Dependencies install successfully.
- [x] Development server starts successfully.
- [x] App opens locally.
- [x] Initial build command is known.
- [x] Any required system dependency is documented.

## M1: Desktop Pet Window Checks

- [x] Pet window launches.
- [x] Window is borderless.
- [x] Window background is transparent or visually acceptable.
- [x] Window can stay above normal windows.
- [x] Pet image renders.
- [x] Pet image can be replaced from `assets\rina`.
- [x] Pet can be dragged after M1 interaction fix.
- [x] App can be closed or hidden intentionally after M1 interaction fix.
- [x] Restarting the app does not break the window behavior.

## M2: Pet State Checks

- [x] `idle` state exists.
- [x] `follow` state exists.
- [x] `talk` state exists.
- [x] `sleep` state exists.
- [x] State transitions are centralized.
- [x] Mouse hover can trigger a state transition after user test.
- [x] Right-click can trigger a state transition after user test.
- [ ] Bubble click can trigger `talk` after follow-up fix.
- [ ] Bubble double-click can toggle `sleep` after follow-up fix.
- [ ] Bubble open button can launch the separate dialogue workspace after user test.
- [x] Separate dialogue workspace placeholder renders.
- [x] Dialogue workspace defaults to chat instead of visible settings.
- [ ] Chat interaction can trigger `talk`.
- [x] State changes are debuggable during development.

## M3: LLM Chat Checks

- [x] API base URL is configurable.
- [x] Model name is configurable.
- [x] Provider/proxy-specific model names can be passed through without a hardcoded vendor map.
- [x] API key is configurable and not hardcoded.
- [x] User can send a text message after real API configuration.
- [x] Response is displayed after real API configuration.
- [x] Streaming works, or non-streaming fallback is documented.
- [x] Failed or missing API configuration shows a clear error path.
- [x] Conversation can be cleared.
- [x] System prompt is loaded from `prompts\rina_system_prompt.md` or override config.
- [x] Token usage is not displayed in the chat surface.
- [x] Image payload shape is reserved for future screenshot handoff.
- [x] Dialogue message thread is internally scrollable.
- [x] Dialogue input starts compact and grows up to a fixed max height.
- [ ] User confirms long real API conversations are comfortable to scroll.
- [ ] Real configured proxy API can respond with a provider-specific model name.
- [ ] Real configured official API can respond with an official model name.
- [ ] Switching `OURDESKPET_MODEL` under the same key/base URL changes the model used by the next request.
- [x] OFOX or another proxy API can complete a request through the native-TLS Rust client.
- [x] Transport-level API errors include lower-level causes when available.

## M4: Region Capture Checks

- [x] Dialogue window has an initial capture/tool button.
- [x] Dialogue tool popover can show quick actions.
- [x] Visible capture entry point triggers a safe system capture route in code/build.
- [x] Global shortcut is explicitly out of current scope.
- [x] User confirms Windows system screen clipping opens.
- [x] User confirms Windows system screen clipping can be canceled without trapping input.
- [x] User confirms real desktop drag creates a region in the system clipper.
- [x] Capture overlay has an always-visible cancel button.
- [x] Selection flow has an explicit `Capture` submit button.
- [x] Selection flow has an explicit `Cancel` discard button.
- [x] Custom overlay remains disabled from the default user path until the trap issue is resolved.
- [x] Selected rectangle coordinates are handled by Windows system clipping.
- [x] Screenshot capture succeeds in a real desktop test.
- [ ] Unusually large screenshots are warned, confirmed, or handled before API handoff.
- [x] Captured image payload records width, height, MIME type, and approximate byte size for debugging.
- [x] Captured image can be previewed in the dialogue composer during user testing.
- [x] Screenshot handoff has a reusable image attachment payload shape.
- [x] Screenshot can attach to the dialogue composer through clipboard polling in code/build.
- [x] User confirms screenshot attaches to the dialogue composer after real selection.
- [x] Pending image attachment can be previewed and removed before sending.
- [x] Pending image preview can open a larger preview modal.
- [x] Sent image thumbnail can open a larger preview modal.
- [x] Pending image remove control is visually low-profile.
- [x] Multiple pending images can sit in a horizontal strip.
- [x] Pasted clipboard image can attach to the dialogue composer, or a clear fallback is shown.
- [x] Image file can attach to the dialogue composer through the dialogue tool popover.
- [x] Dialogue quick-action popover is compact enough for the chat surface.
- [x] Dialogue composer remains editable while the assistant is streaming.
- [x] Send button changes into a Stop button while streaming.
- [ ] Stop button cancels an active real API stream during user testing.
- [x] Quick action/prompt-template menu appears.
- [x] Prompt templates are optional and not required for M4 completion.
- [ ] At least one screenshot plus prompt reaches a vision-capable model in user testing.
- [ ] Non-vision model fallback is understandable.
- [x] Escape/cancel path exists in code/build.
- [x] Capture call has a frontend timeout fallback to avoid trapping the overlay.
- [x] User confirms the accepted system capture route can be exited cleanly.

## Shared UI Checks

- [x] Scrollbars use a low-presence style by default.
- [ ] User confirms low-presence scrollbars remain discoverable in long chat/image attachment use.

## Documentation Checks

- [x] `PROJECT_PLAN.md` matches the current direction.
- [x] `MILESTONES.md` reflects current milestone status.
- [x] `FEATURES.md` reflects accepted and deferred scope.
- [x] `DEV_LOG.md` records meaningful changes.
- [x] `QA_CHECKLIST.md` includes new checks introduced by new features.
- [x] Project management Markdown is centralized under `docs`.
- [x] Artifact-specific Markdown is kept next to the artifact only when useful.
- [ ] Build cache policy remains documented if build layout changes.

## Pre-Feedback Checks

Before reporting progress to the user after a development step:

- [ ] What changed?
- [ ] How was it verified?
- [ ] What is still uncertain?
- [ ] What is the recommended next step?
