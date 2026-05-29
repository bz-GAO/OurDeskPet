# OurDeskPet

OurDeskPet is a Windows desktop intelligent pet prototype built with Tauri 2, React, TypeScript, and Rust.

The current prototype includes:

- a transparent always-on-top desktop pet window
- a simple pet state system
- a separate dialogue workspace
- OpenAI-compatible streaming chat
- image attachments through file selection, clipboard paste, and Windows system screen clipping
- a Rina-style system prompt loaded from a local prompt file

The project is currently past the first functional prototype stage. M0-M4 are initially implemented, and future work is organized as small optimization packages.

## Current Status

Implemented:

- `M0`: project foundation
- `M1`: desktop pet window
- `M2`: pet state system
- `M3`: LLM text chat
- `M4`: screenshot/image handoff through Windows system clipping and clipboard

Next planned work:

- `R1`: reliability and long-conversation management
- `A1`: state-specific pet art
- `L1`: LLM capability expansion
- `M4P`: screenshot/image polish
- `S1`: settings and management surface

See:

```text
docs\modules\OPTIMIZATION_PACKAGES.md
```

## Requirements

- Windows
- Node.js and npm
- Rust toolchain
- Tauri prerequisites for Windows

## Setup

Install frontend dependencies:

```powershell
cd E:\OurDeskPet\app
npm install
```

Create local API configuration from the example:

```powershell
Copy-Item E:\OurDeskPet\.env.example E:\OurDeskPet\.env
```

Then edit:

```text
E:\OurDeskPet\.env
```

At minimum, set:

```text
OURDESKPET_API_KEY
OURDESKPET_BASE_URL
OURDESKPET_MODEL
```

`.env` is intentionally ignored by Git.

## Development

Run from:

```powershell
cd E:\OurDeskPet\app
```

Useful commands:

```powershell
npm run build
npm run tauri dev
npm run tauri build -- --debug --no-bundle
```

The debug executable is expected at:

```text
E:\OurDeskPetBuildCache\cargo-target\debug\our-desk-pet.exe
```

## Documentation

Project documentation starts here:

```text
docs\README.md
```

Important documents:

- `docs\PROJECT_PLAN.md`: product direction and architecture boundaries
- `docs\MILESTONES.md`: milestone status
- `docs\FEATURES.md`: feature inventory
- `docs\QA_CHECKLIST.md`: repeatable checks
- `docs\DEV_LOG.md`: chronological development log
- `docs\modules\*.md`: module plans and optimization packages

## Notes

- The compact pet bubble is a status/launcher surface.
- Real chat happens in the separate dialogue window.
- Screenshot capture uses Windows system clipping plus clipboard handoff.
- Global screenshot shortcuts are intentionally out of scope for now.
- The custom fullscreen capture overlay is experimental and not the default user path.

## Repository Hygiene

Do not commit:

- `.env`
- `node_modules`
- frontend build output
- Rust `target` output
- local logs
- external build caches such as `E:\OurDeskPetBuildCache`
