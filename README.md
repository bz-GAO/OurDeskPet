# RinaDesk Agent

A Windows desktop companion built with Tauri 2, React, TypeScript, and Rust. RinaDesk features Rina Tennoji artwork, an interactive Rina-chan Board, and separate chat and settings windows.

- Summer and winter outfits with idle, dragging, talking, and sleeping artwork, plus the original Astromeda single-image pack.
- OpenAI-compatible streaming chat, cancellation, Markdown code highlighting, math rendering, image attachments, and Windows screenshot paste.
- In-process conversation retention, reset/retry, bounded context, and optional Tavily web search with source links. See the [chat guide](docs/CHAT-AND-SEARCH.md).
- API profile management in settings, with support for manual `.env` edits.
- Completion notifications, unread indicators, and taskbar attention. Opening a panel moves the pet only when it overlaps the panel.

## Getting started

Requirements: Windows, Node.js/npm, Rust MSVC, Visual Studio C++ Build Tools with the Windows SDK, and WebView2.

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
cd app
npm ci
npm run tauri dev
```

Copy the example only during initial setup; do not overwrite an existing configuration. API profiles can also be added in settings. Use `npm run dev` for a browser preview; native window features require Tauri.

To build, run `npm run tauri build -- --no-bundle` from `app`. The default executable is `app/src-tauri/target/release/our-desk-pet.exe`; `CARGO_TARGET_DIR` overrides the output directory. See the [development guide](docs/DEVELOPMENT.md).

## Basic controls

| Action | Result |
| --- | --- |
| Click the character | Show or hide the small Rina-chan Board. It also collapses automatically. |
| Drag the character | Move the pet; the board closes while dragging. |
| Right-click the character | Toggle sleep/wake. The board stays closed during sleep. |
| Hover a star on the small board | Preview its action on the board screen. From left to right: chat, minimize the pet, quit the app. |
| Click the smile inside the small board | Open settings. |
| Settings → Character & Art | Select a named pack, drag/scroll its previews, then enable it. |
| Settings → API | Add a URL, key and model, save the profile, then activate it. |
| Close the chat window | Keep the conversation and any pending reply until the pet exits. Use **Reset conversation** to clear it explicitly. |

In the enlarged settings board, the second star minimizes **settings** and the third closes **settings only**; the first is reserved. Drag the board frame to move that window. Restore a minimized window from the Windows taskbar.

A background reply briefly flashes the small board, then leaves an unread dot beside the pet; the pet itself stays visible. Chat supports Markdown, code/math rendering and attachments. Its web-search selector offers Auto, Off and Required; optional Tavily setup is explained in the [chat guide](docs/CHAT-AND-SEARCH.md). UI labels are currently Chinese.

## Repository layout

| Path | Contents |
| --- | --- |
| `app/src`, `app/src-tauri/src` | Frontend and Rust source |
| `app/public/assets/rina` | Final character and board artwork |
| `app/src-tauri/icons` | Desktop application icons |
| `assets` | Asset provenance and SHA-256 manifest |
| `prompts/rina_system_prompt.md` | Active character prompt |
| `docs` | Development notes, roadmap, and prompt research |
| `.local-archive` | Local references, intermediate artwork, and historical notes; excluded from Git |

See the [documentation index](docs/README.md). Repository documentation is in English. The current application interface and active character prompt remain in Chinese. Prompt research drafts are not loaded by the application.

Rina Tennoji and related designs originate from Love Live! Nijigasaki. This is an unofficial personal project. See [asset provenance](assets/README.md); source attribution does not grant rights to the original characters or reference artwork.
