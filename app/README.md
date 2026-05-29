# RinaDesk Agent App

This is the Tauri 2 + React + TypeScript application for RinaDesk Agent.

Project-level planning lives in:

```text
E:\OurDeskPet\docs
```

This file is only for app-local development notes.

## Commands

Run from `E:\OurDeskPet\app`:

```powershell
npm run build
npm run tauri dev
npm run tauri build -- --debug --no-bundle
```

The debug executable is built at:

```text
E:\OurDeskPetBuildCache\cargo-target\debug\our-desk-pet.exe
```

## Source Layout

```text
app\src
  components\      React UI components
  llm\             frontend LLM/chat types and hooks
  pet\             pet state/profile logic
  App.tsx          route selection for pet/dialogue/capture views
  App.css          shared UI styles

app\src-tauri
  src\lib.rs       Tauri commands, LLM request handling, screenshot/clipboard commands
  Cargo.toml       Rust dependencies
  tauri.conf.json  app/window configuration
```

## Notes

- The compact pet bubble is a status/launcher surface.
- Real chat happens in the separate dialogue window.
- Screenshot capture uses Windows system clipping plus clipboard handoff.
- The custom capture overlay is experimental and not the default user path.
