# M4 Region Capture and Agent Handoff Plan

Last updated: 2026-05-28

## Goal

M4 adds the first desktop interaction workflow:

- user captures a screen region
- the image reaches the dialogue composer
- the image can be sent through the existing LLM vision payload path

The milestone should stay focused on the capture-to-agent loop. It should not become a full OCR suite, file manager, annotation app, shortcut manager, or study-note product.

## Product Position

This belongs to the desktop interaction layer, not the character/art layer.

The useful early scenario is:

```text
See something on screen -> capture it -> ask Rina to explain or answer based on it.
```

Courseware-learning is an application of this flow, not a separate early product module.

## Current Dependencies

M1/M2 foundation:

- Transparent always-on-top pet window exists.
- Pet can open a separate dialogue workspace.
- Pet bubble is a status/launcher surface, not the full chat UI.

M3 foundation:

- Dialogue workspace can send text to an OpenAI-compatible API.
- Rust backend can read `.env` configuration.
- Image payload shape exists on the frontend and backend.
- Existing LLM request builder can attach image data URLs to the last user message.

M4 attachment foundation:

- Image file selection works.
- Clipboard image paste works.
- Pending image thumbnails can be previewed, removed, and sent.
- Sent image thumbnails remain visible and previewable in the thread.

## Accepted Capture Route

The accepted M4 route is Windows system clipping plus clipboard handoff:

1. User opens the dialogue tool popover and chooses `Capture`.
2. OurDeskPet launches Windows system screen clipping.
3. User selects a region with the OS clipping surface.
4. Windows places the screenshot on the clipboard.
5. OurDeskPet polls the clipboard and attaches the image to the dialogue composer.
6. A short prompt is prepared, and the user can edit it before sending.

Alternative user flow:

- User captures a screenshot with any preferred tool.
- User pastes the image into the dialogue composer with `Ctrl+V`.
- The same image payload path is used.

## Scope

### In Scope

- A visible capture entry point in the dialogue window.
- Windows system screen clipping as the default selection surface.
- Clipboard image polling after system clipping.
- Manual image paste as a first-class fallback.
- Convert captured or pasted image to a data URL payload.
- Send captured image through the existing chat workflow.
- Lightweight prompt templates:
  - Explain this.
  - Ask about this.
  - Summarize this.
- Clear fallback when the configured model/API does not support image input.

### Out Of Scope

- Global screenshot shortcuts or hotkeys.
- A custom fullscreen capture overlay as the default route.
- Full OCR engine.
- Multi-file upload.
- Persistent capture history.
- Advanced annotation tools.
- Advanced image compression pipeline.
- Study-note generation workflow.
- Multi-monitor perfection beyond what Windows system clipping already provides.
- Full settings UI for shortcut/key/model management.

## Decisions

- Do not add global shortcuts for now.
- Keep the desktop pet small and focused; avoid turning it into a heavyweight system utility.
- The capture button is useful for users who do not remember or prefer system shortcuts.
- Users who already have a preferred screenshot workflow can use clipboard paste.
- `Explain`, `Ask`, and `Summarize` are prompt templates only, not a major quick-action framework.
- The prompt templates may be removed or hidden later if the toolbox feels noisy.

## Custom Overlay Status

A dedicated React overlay was prototyped at:

```text
/?view=capture
```

User testing showed the custom fullscreen transparent overlay could trap mouse/focus state on Windows, even after visible cancel controls were added.

Current status:

- The custom overlay is not the default route.
- It remains experimental code only.
- Do not revive it without a safer window strategy.
- Any future custom capture surface must prove it cannot trap input before it becomes user-facing.

## Screenshot Payload Shape

System clipper and clipboard image handling should produce:

```ts
type CapturedImagePayload = {
  mimeType: "image/png";
  dataUrl: string;
  width: number;
  height: number;
  byteSize: number;
  name: "screen-clip.png";
};
```

Image-size policy:

- Prefer readable screenshots over aggressive compression.
- Defer heavy image compression or resizing to M5/later unless real provider tests require it.
- Normal screen regions are expected to be acceptable for first testing.
- Very large screenshots can later get a warning or confirmation step.

## Chat Handoff

Reuse the M3 chat path:

```ts
sendMessage({
  text: "请解释这张截图中的内容。",
  images: [capturedImage],
  source: "selection"
});
```

Current behavior:

- Dialogue starts Windows system clipping.
- Dialogue polls for a new clipboard image.
- Dialogue attaches the image to the composer as a pending image.
- Dialogue prepares the prompt `请解释这张截图中的内容。`.
- User presses `Send`, keeping the workflow inspectable.

## QA Plan

Manual checks:

- Entry point opens Windows system screen clipping.
- System clipping can be canceled without trapping input.
- Selected image reaches the clipboard.
- Dialogue detects the clipboard image and attaches it to the composer.
- Manual `Ctrl+V` paste remains available.
- Captured image reaches the LLM request path.
- A vision-capable model responds to a screenshot plus prompt.
- Non-vision or incompatible model shows a clear fallback/error.

Technical checks:

- `npm run build`
- `cargo fmt`
- `npm run tauri build -- --debug --no-bundle`
- Confirm no long-running dev process is left after automated checks.

## Exit Criteria

- User can select a screen region through Windows system clipping.
- App can attach the selected image to the dialogue composer.
- Captured image can be sent to the configured LLM as an image.
- Cancel/failure paths are understandable.
- M4 behavior is documented in `DEV_LOG.md` and `QA_CHECKLIST.md`.

## Current Status

M4 initial implementation is complete as of 2026-05-28.

Remaining work is optional polish:

- decide whether prompt templates should stay visible
- improve fallback text for providers without vision support
- remove or fully quarantine the experimental custom overlay code later
