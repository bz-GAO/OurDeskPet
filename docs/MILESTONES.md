# Milestones

Last updated: 2026-05-28

## M0: Project Foundation

Status: Completed on 2026-05-27

Goal:

Create the project foundation and confirm the chosen stack can run locally.

Tasks:

- Create `E:\OurDeskPet` directory structure.
- Create project management documents.
- Initialize the main app project.
- Confirm local development commands.
- Confirm project-local dependency management.
- Start the development server.
- Record the first runnable command in `DEV_LOG.md`.

Exit criteria:

- The repository or project folder has a clear structure. Done.
- The app can be launched locally. Done via `npm run tauri dev`.
- The development command is documented. Done in `DEV_LOG.md`.
- The first QA checklist items exist. Done.

## M1: Desktop Pet Window

Status: Implemented on 2026-05-28

Goal:

Create the first traditional desktop pet shell.

Tasks:

- Create a transparent window. Done via Tauri window config.
- Make the window borderless. Done via Tauri window config.
- Keep the window above normal windows. Done via Tauri window config.
- Render a placeholder pet image. Done with `Rina_bot_cutout.png`.
- Use `assets\rina` as the pet image replacement location. Done.
- Support dragging the pet. Done after explicit Tauri window permission and `data-tauri-drag-region` fix.
- Add basic close or hide behavior. Done after explicit Tauri window permissions.

Exit criteria:

- The pet appears on the desktop. Verified by `npm run tauri dev` process startup.
- The background is transparent or close to transparent. Implemented via transparent window config and cutout PNG.
- The window can be moved. Done after user retest.
- The image source path is documented. Done.
- The app remains runnable after restart. Verified by repeated build and dev startup.

## M2: Pet State System

Status: Implemented on 2026-05-28; minor bubble interaction retests remain

Goal:

Add a simple behavior layer so the pet is more than a static image.

Tasks:

- Define pet states: `idle`, `follow`, `talk`, `sleep`. Done.
- Add a state machine or equivalent state controller. Done with `usePetController`.
- Add basic mouse interaction. Hover and right-click confirmed; click/double-click reworked to bubble-only interactions and need retest.
- Add simple state transitions. Done.
- Add a right-click or tray-accessible control surface. Done with a temporary right-click sleep/wake toggle; tray remains future work.
- Add logging for state changes during development. Done via console state transition logs.

Exit criteria:

- The pet can switch between at least three states. Hover and right-click confirmed; bubble click/double-click need retest.
- State logic is centralized. Done.
- State changes can be tested manually. Done.
- The user can still drag or control the pet predictably. Build/start verified; awaiting user check after M2 interaction changes.

## M3: LLM Text Chat

Status: Implemented on 2026-05-28; model-switching and long-chat comfort checks remain

Goal:

Connect the pet to an OpenAI-compatible chat API.

Tasks:

- Build a compact chat UI. Done in the separate dialogue workspace.
- Add text input. Done.
- Add response display. Done.
- Add API configuration: base URL, model, API key. Done through `.env` or environment variables.
- Add OpenAI-compatible provider abstraction. Started with a Rust-side OpenAI-compatible adapter.
- Support streaming if feasible in this milestone. Done through Tauri events.
- Add clear error messages for failed requests. Done for missing config and API request failure paths.
- Add basic conversation history. Done in memory for the current dialogue session.

Module plan:

```text
docs\modules\M3_LLM_CHAT.md
```

Exit criteria:

- The user can send a text message. Done.
- The configured model can respond. Done in user test.
- API credentials are not hardcoded. Done.
- Failures are visible and understandable. Done for missing config, transport, and API error paths.
- The pet can enter a `talk` state during chat. Implemented through dialogue launcher path; worth retesting with M2 bubble checks.

## M4: Region Capture and Agent Handoff

Status: Initial implementation completed on 2026-05-28

Goal:

Let the user select a desktop region and send that region to the pet/LLM workflow.

Tasks:

- Add a visible entry point for region selection. Done through the dialogue tool popover.
- Use a safe region selection route. Done through Windows system screen clipping.
- Capture the selected region as an image. Done through Windows clipboard handoff.
- Attach the image to the dialogue composer. Done through clipboard image polling and existing paste support.
- Send the image to a vision-capable model when configured. Implemented through the M3 image payload path.
- Provide fallback messaging when the model does not support image input. Basic API error path exists; provider-specific polish remains later.

Module plan:

```text
docs\modules\M4_REGION_CAPTURE.md
```

Exit criteria:

- The user can select a region on screen. Done through Windows system clipping.
- The app can capture or receive the selected image. Done through clipboard handoff.
- The image can be sent into the agent workflow. Done through existing image attachments.
- The flow avoids trapping input. Done by replacing the custom fullscreen overlay as the default route.
- The flow fails understandably when API or model support is missing. Basic path exists; polish remains later.

Roadmap decision:

- Global screenshot shortcuts are not planned for now.
- Prompt templates such as `Explain`, `Ask`, and `Summarize` are optional convenience text, not core milestone requirements.

## Optimization Phase

Status: Planned after M4

Goal:

Improve reliability, presentation, and LLM capability without inflating the desktop pet into a heavy system utility.

Module plan:

```text
docs\modules\OPTIMIZATION_PACKAGES.md
```

Packages:

- R1 Reliability and Long-Conversation Management.
- A1 Art and Pet-State Presentation.
- L1 LLM Capability Expansion.
- M4P Screenshot and Image Polish.
- S1 Settings and Management Surface.

Suggested first package:

- R1, because long conversations currently send the in-memory text history without summarization.

## M5: Character and Art System

Status: Future

Goal:

Turn the technical pet into a character-driven pet.

Tasks:

- Define Rina character prompt.
- Define tone and response rules.
- Replace placeholder image with chosen Rina image assets.
- Add emotion-to-state mapping.
- Explore spritesheet, frame animation, or Live2D-style approaches.
- Create a future Rina-specific skill if useful.

Exit criteria:

- The character behavior is documented.
- Art assets have a stable source and replacement workflow.
- The app can map pet states to character visuals.

## M6: Packaging and Reliability

Status: Future

Goal:

Make the project comfortable to run repeatedly.

Tasks:

- Add settings persistence.
- Add tray menu completeness.
- Add logs.
- Add crash or request failure recovery.
- Add Windows packaging.
- Consider startup behavior.
- Consider auto-update later.

Exit criteria:

- The app can be packaged for Windows.
- User settings survive restart.
- Logs are available for debugging.
- The app can be closed, hidden, and reopened predictably.
