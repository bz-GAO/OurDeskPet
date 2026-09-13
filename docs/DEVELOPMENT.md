# Development, builds, and local startup

From the repository root, enter `app`, then run `npm ci` and `npm run tauri dev`. Visual Studio C++ tools and the Windows SDK are required. If RC.EXE is missing, use a developer terminal or add the installed SDK's x64 binary directory to the current process PATH.

## Build and test

```powershell
cd app
npm run build
node tests/art.test.mjs
node tests/markdown.test.mjs
node tests/notifications.test.mjs
cd src-tauri
cargo test
cd ..
npm run tauri build -- --no-bundle
```

Browser UI tests require Playwright and Edge. Start Vite, then run `node tests/settings-ui.test.cjs` with Playwright available. Rust tests cover native placement calculations; browser screenshots do not replace native Windows interaction checks.

Machine-specific Cargo output paths are not committed. Cargo uses its default target directory unless overridden. To keep updating the existing maintainer shortcut, set this before building:

```powershell
$env:CARGO_TARGET_DIR='E:\OurDeskPetBuildCache\cargo-target'
```

The maintainer's `E:\OurDeskPet\RinaDesk.lnk` points to the release executable in that cache, with `E:\OurDeskPet` as its working directory. The shortcut remains local and ignored because it contains absolute paths. The unused Start-Rina.cmd and Develop-Rina.cmd scripts have been archived. To launch that local build from PowerShell:

```powershell
Set-Location E:\OurDeskPet
& E:\OurDeskPetBuildCache\cargo-target\release\our-desk-pet.exe
```

## API profiles and prompts

Settings supports adding, editing, saving, and activating OpenAI-compatible API profiles. Switching profiles affects the next request. Named `.env` entries use `OURDESKPET_PROFILE_<UPPERCASE_ID>_{NAME,BASE_URL,API_KEY,MODEL}` and `OURDESKPET_ACTIVE_PROFILE=<lowercase_id>`. Legacy single-profile configuration remains supported. Leaving the key field empty while editing preserves the existing key.

Settings detects file changes through polling and focus events. Conflicting disk edits do not overwrite an unsaved draft. Do not commit `.env`. The default character prompt is `prompts/rina_system_prompt.md`, with optional `OURDESKPET_PROMPT_FILE` or inline overrides. Research drafts are not loaded automatically.

## Before committing

Review `git status --short` and `git diff --stat`. Final artwork is listed in `assets/manifest.json`. Reference images, rejected drafts, review screenshots, local shortcuts, and historical notes remain archived or ignored. Do not force-add them. Run `python scripts/check_repository.py` to check the final asset inventory and submission candidates.

Removing obsolete files from the working tree does not remove them from existing Git history. The cleanup did not rewrite history.
