# OurDeskPet Project Plan

Last updated: 2026-05-28

## 1. Project Goal

OurDeskPet is a Windows desktop intelligent pet application.

The project starts as a traditional desktop pet, then grows into an LLM-powered desktop companion that can chat, receive screenshots, and interact with selected screen regions.

The first goal is not to build a polished character product immediately. The first goal is to create a stable, runnable engineering foundation:

- A desktop pet window that can live on the desktop.
- A small but clear pet state system.
- A chat interface connected to an OpenAI-compatible API.
- A safe screenshot/image handoff workflow that can send screen captures to the agent.

Character art, Rina-specific prompts, and custom pet behavior will be added after the technical foundation works.

The code should keep a clear boundary between pet behavior and pet presentation. The early app can use a default profile, but future character work should be able to replace profile data, images, message style, and visual components without rewriting the state controller.

## 2. Product Layers

### 2.1 Desktop Pet Layer

This layer provides the traditional desktop pet experience.

Core capabilities:

- Transparent pet window.
- Always-on-top display.
- Borderless window.
- Dragging and repositioning.
- Basic mouse interaction.
- Basic state switching.
- Tray menu.
- Simple animation placeholder.

Initial states:

- `idle`: default waiting state.
- `follow`: follows or reacts to the mouse.
- `talk`: active dialogue state.
- `sleep`: low-activity state.

### 2.2 LLM Chat Layer

This layer makes the pet usable as an API-backed assistant.

Core capabilities:

- Chat bubble or compact chat panel.
- Text input.
- Streaming response display.
- OpenAI-compatible API adapter.
- Configurable base URL, model name, and API key.
- System prompt support.
- Basic conversation history.
- Error handling for failed API calls.

Planned provider abstraction:

```text
LLMProvider
  OpenAICompatibleProvider
  FutureProvider
```

### 2.3 Desktop Interaction Layer

This layer lets the pet interact with the user's screen.

Core capabilities:

- Visible dialogue-side capture entry point.
- Windows system screen clipping for region selection.
- Clipboard image handoff from system screenshots or user-preferred screenshot tools.
- Send selected image to a vision-capable model.
- Optional OCR flow later.
- Optional prompt templates such as explain, summarize, or ask about selected region.

The courseware-learning use case belongs here as an application scenario, not as a separate early-stage module.

Current scope decision:

- Global screenshot shortcuts are out of scope for now.
- A custom fullscreen screenshot overlay was prototyped but is not accepted as the default route because it can trap input on Windows.
- The accepted M4 route is Windows system clipping plus clipboard handoff.

## 3. Recommended Tech Stack

Primary route:

```text
Tauri 2 + React + TypeScript + Rust
```

Rationale:

- Tauri is lighter than Electron for a long-running desktop pet.
- React is suitable for chat UI, settings UI, and pet interaction surfaces.
- Rust is suitable for native window control, screenshots, file access, tray integration, and system APIs.
- Tauri supports transparent windows, always-on-top behavior, tray menus, and native system APIs. Global shortcuts are possible but intentionally not planned for the current scope.

Development environment principle:

- Use isolated project-level environments where applicable.
- Frontend dependencies should be managed inside the app project.
- Rust dependencies should stay within the Tauri project.
- Any Python utilities, if introduced for asset processing or QA, should use a project-local virtual environment.
- Rust/Tauri compile caches are allowed and expected during active development, but they should be treated as disposable build output rather than project source. Prefer placing large Cargo target caches outside the app folder once M1 starts, and clean them after milestone verification or when they grow too large.

## 4. Project Path

Root path:

```text
E:\OurDeskPet
```

Initial layout:

```text
E:\OurDeskPet
  app\
  docs\
  assets\
    rina\
  prompts\
  skills\
  experiments\
```

Planned external build cache:

```text
E:\OurDeskPetBuildCache
```

This folder is for large disposable build caches, especially Rust/Cargo `target` output. It should not be treated as source code or project content.

Directory roles:

- `app`: main application source code.
- `docs`: planning, milestones, feature list, development log, QA checklist.
- `assets`: pet images, animation assets, icons, audio, and later spritesheets.
- `assets\rina`: Rina-related image assets and replacement point for the first pet image.
- `prompts`: system prompts, character prompts, task prompts, and API agent prompts.
- `skills`: future Codex skills or project-specific workflows.
- `experiments`: small technical prototypes before integrating into the main app.

Module-level plans:

```text
E:\OurDeskPet\docs\modules
```

This folder records focused milestone/module plans so small implementation decisions are easy to review without searching the full development log.

Documentation organization:

- Keep project management documentation centralized in `docs`.
- Keep focused milestone/module plans in `docs\modules`.
- Keep artifact-specific notes next to the artifact only when they are directly used there, such as `app\README.md`, `assets\rina\README.md`, or prompt files in `prompts`.
- Do not use dependency package docs under `node_modules` as project documentation.
- Start from `docs\README.md` when re-orienting after a break.

## 5. Existing Rina Asset Source

Known existing image source:

```text
E:\API_test\RinaChanBoard\img
```

Useful files found:

```text
E:\API_test\RinaChanBoard\img\Rina_bot.jpg
E:\API_test\RinaChanBoard\img\Rina_UI.jpeg
E:\API_test\RinaChanBoard\img\Rina_UI.ico
E:\API_test\RinaChanBoard\img\Rina_user.jpg
```

The first runnable pet can use a copied image from this source as a placeholder. Later, the replacement location should be:

```text
E:\OurDeskPet\assets\rina
```

Initial copied project-local assets:

```text
E:\OurDeskPet\assets\rina\Rina_bot.jpg
E:\OurDeskPet\assets\rina\Rina_UI.ico
```

## 6. Current Scope

Completed or initially completed in the early project:

- Build the project skeleton.
- Build a runnable desktop app.
- Build a transparent pet window.
- Build simple pet behavior.
- Build LLM text chat.
- Build screen-region capture and image handoff.

Ongoing scope after M0-M4:

- Improve reliability and long-conversation behavior.
- Add state-specific pet art once assets are ready.
- Improve LLM capability through explicit tools rather than crowded chat controls.
- Polish screenshot/image handoff only where real testing shows friction.
- Keep the project documented after each meaningful change.

Not in current scope:

- Full Rina character system.
- Polished animation set.
- Live2D integration.
- Learning assistant product workflows as a separate module.
- Global screenshot shortcuts or hotkeys.
- Plugin marketplace.
- Auto-update system.

Future work is organized as optimization packages rather than one large milestone:

```text
docs\modules\OPTIMIZATION_PACKAGES.md
```

Current packages:

- R1: Reliability and long-conversation management.
- A1: Art and pet-state presentation.
- L1: LLM capability expansion.
- M4P: Screenshot and image polish.
- S1: Settings and management surface.

## 7. Development Rules

Each implementation step should include:

1. Define the immediate target.
2. Make the smallest coherent code change.
3. Run or build the app when possible.
4. Verify behavior manually or with tooling.
5. Update `DEV_LOG.md`.
6. Update `QA_CHECKLIST.md` when a new check becomes relevant.
7. Report the result, including what was verified and what remains uncertain.

Build cache rule:

- Keep compile caches while actively developing a milestone so repeated checks stay fast.
- Move large Rust target output outside `app` when practical.
- Clean build caches after milestone completion, before long pauses, or when disk usage becomes unreasonable.
- Never mistake generated `target`, `dist`, or cache folders for source artifacts.

Presentation boundary rule:

- Pet state logic should live outside the visual components.
- Character/profile data should define images, messages, and visual tone.
- Default components should be replaceable later by a Rina-specific presentation layer.
- Do not build a character switching UI until the role/profile system is better understood.

Dialogue surface rule:

- The small pet bubble is a symbolic status display and notification/launch surface.
- API chat should live in a separate dialogue workspace window, not inside the compact pet bubble.
- The compact bubble may show short status text and open the dialogue workspace.
- M3 should build the real API-backed chat page inside the dialogue workspace.

LLM configuration rule:

- The default chat surface should not display API keys, token cost, model controls, or provider settings.
- M3 may read API configuration from `.env` or environment variables.
- A later pet management/settings window can provide safer configuration editing and token usage display.

The project should always prefer a small runnable version over a large half-integrated version.

## 8. Review Cadence

At the end of each milestone:

- Review whether the milestone exit criteria were met.
- Update `MILESTONES.md`.
- Update `FEATURES.md` if scope changed.
- Add a dated entry to `DEV_LOG.md`.
- Run the relevant checks from `QA_CHECKLIST.md`.

Before starting a new milestone:

- Confirm the next target.
- Check whether current docs still match the code.
- Avoid carrying outdated assumptions forward.
