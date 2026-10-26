# Development, builds, and local startup

From the repository root, enter `app`, then run `npm ci` and `npm run tauri dev`. Visual Studio C++ tools and the Windows SDK are required. If RC.EXE is missing, use a developer terminal or add the installed SDK's x64 binary directory to the current process PATH.

## Build and test

### Restart persistence

Restart hardening (2026-10-18): an existing broken installation anchor blocks implicit
configuration fallback instead of selecting another profile directory. An explicit absolute
`OURDESKPET_ENV_FILE` remains an intentional override. Invalid non-comment `.env` lines are
reported without echoing their values; saving does not silently replace malformed files.
Launcher repair flushes a temporary anchor before atomically replacing the old one. Interrupted
config replacement is tested with a locked destination: old contents survive and only the
operation's own temporary file is cleaned up. These checks do not guarantee recovery from disk
hardware failure and do not create plaintext credential backups.

### Verified Git checkpoints

After a working update has passed its relevant tests, production build and launch smoke test,
record a local Git checkpoint for each changed repository. In this project, “Git checkpoint”,
“archive” and “save the current state” mean a local commit only. Do not push commits, tags or
branches, create a pull request/release, or otherwise update a remote unless the user explicitly
asks to push or publish that particular change. Permission to edit, build, test or create a local
checkpoint does not imply permission to push.

Record the tested commit(s), test results,
tool protocol compatibility and known limitations in the commit message or release notes.
Desk/Yaki/Tomo are separate repositories: list the compatible revisions together for cross-project
updates, rather than assuming one commit snapshots the entire workspace.

Only commit reviewed source and documentation. Never include `.env`, AccessKeys, login profiles,
runtime settings, account ledgers, media, build caches or installed executables. Keep dependency
lockfiles and build instructions so the checkpoint can be rebuilt. A source checkpoint is not a
backup of personal data or a guarantee that an old executable can read newer runtime data.
The standing project instruction authorizes local checkpoints after reviewed work without a separate
round-by-round push request. Remote writes always require a new, explicit user request. Record an unverified
or partially tested update as such; do not label it a known-good checkpoint. Revert through reviewed
commits/branches, never a destructive reset of a dirty checkout.

### External implementation references

RinaDesk may use an open-source project as a design reference without making it a runtime dependency.
The current title-lifecycle reference is DeepSeek Harness: use a synchronous first-user-message fallback,
keep optional enrichment off the response-critical path, and let an explicit user rename win. RinaDesk
now uses a local fallback plus one asynchronous model title request after the first complete reply, as approved on 2026-10-20. Record
the exact upstream page, license and the adopted boundary in [IMPLEMENTATION-REFERENCES.md](IMPLEMENTATION-REFERENCES.md);
do not copy an entire subsystem or silently inherit its plugin/security model.

### Documentation authority

`docs/STATUS.md` is the single current-status and active-priority entry point. Feature documents such as `CHAT.md`, `ATTACHMENTS.md`, `SETTINGS.md`, `EXTENSIONS.md` and `MOTION-EFFECTS.md` describe present behavior and safety boundaries. Dated roadmap, iteration and acceptance files are historical records only. Update the relevant feature document with an implementation change, then update `STATUS.md` only when completion, acceptance state or priority changes. Do not keep the same active task in several dated files.

### Verification commands

For documentation-only changes, check links, factual consistency and `git diff --check`; a native rebuild or application replacement is not needed. Record that scope in the checkpoint. For implementation changes, run the relevant tests and builds below.

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

Machine-specific Cargo output paths are not committed. Direct Cargo/Tauri commands use ignored `app/src-tauri/target` unless `CARGO_TARGET_DIR` overrides it. The recommended local build helper instead reuses `%LOCALAPPDATA%\RinaDesk\build-cache\cargo-target`, avoiding a second default cache in the project. It copies the verified executable to `%LOCALAPPDATA%\RinaDesk\bin\RinaDesk.exe`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/Build-Local.ps1
```

The helper refreshes `RinaDesk.lnk` in the repository root and an existing desktop shortcut. The shortcut points to the installed copy, not the Cargo cache. The cache is disposable: removing it only makes the next build slower. The shortcut remains local and ignored because Windows shortcuts contain machine-specific absolute paths. To launch the local shortcut from PowerShell:

Use the Tauri CLI or `scripts/Build-Local.ps1` for launchable builds. `cargo build --release` alone can produce an executable that points at the development `localhost:1420` URL; the helper checks that the production frontend asset is embedded before updating the shortcut.

```powershell
& .\RinaDesk.lnk
```

## API profiles and prompts

Settings supports adding, editing, saving, and activating OpenAI-compatible API profiles. Switching profiles affects the next request. Named `.env` entries use `OURDESKPET_PROFILE_<UPPERCASE_ID>_{NAME,BASE_URL,API_KEY,MODEL}` and `OURDESKPET_ACTIVE_PROFILE=<lowercase_id>`. Legacy single-profile configuration remains supported. Leaving the key field empty while editing preserves the existing key.

Settings detects file changes through polling and focus events. Conflicting disk edits do not overwrite an unsaved draft. Do not commit `.env`. The default character prompt is `prompts/rina_system_prompt.md`, with optional `OURDESKPET_PROMPT_FILE` or inline overrides. Research drafts are not loaded automatically.

## Before committing

Review `git status --short` and `git diff --stat`. Final artwork is listed in `assets/manifest.json`. Reference images, rejected drafts, review screenshots, local shortcuts, and historical notes remain archived or ignored. Do not force-add them. Run `python scripts/check_repository.py` to check the final asset inventory and submission candidates.

Removing obsolete files from the working tree does not remove them from existing Git history. The cleanup did not rewrite history.

## Portable local launcher and group layout

The desktop project lives in `RinaDesk`; sibling tools such as `RinaYaki` are independent projects. `Build-Local.ps1` keeps one shared incremental Cargo cache under `%LOCALAPPDATA%\RinaDesk\build-cache\cargo-target`, outside the E-drive project. It is not a runtime or launcher dependency. Pass `-CacheRoot` only when another cache location is intentionally required.

From the repository root, run `powershell -ExecutionPolicy Bypass -File scripts/Build-Local.ps1` to build with Windows SDK discovery, reuse the single LocalAppData compiler cache, install the verified executable under LocalAppData and refresh the shortcut. `-CacheRoot` overrides compiler storage; `-InstallRoot` changes the stable local install directory. To repair a shortcut after moving folders without rebuilding, run `powershell -ExecutionPolicy Bypass -File scripts/Repair-Launcher.ps1`. Pass `-ExecutablePath` only for a custom install location.

The launcher repair updates target, working directory and icon. It updates an existing startup-at-login entry without enabling one that was disabled. A `rinadesk-root.txt` companion next to the installed executable points to the project by a relative path on the same drive or an absolute path across drives. Runtime config, project-assistant source reads and the sibling Tomo lookup use that anchor, including when Windows starts the app with an unrelated working directory. Keep the companion file with the installed executable. Direct `tauri build` output under `app/src-tauri/target/release` can also locate the project through the executable's ancestors when no anchor exists. Only debug/test builds may finally use their compilation source directory; an invalid existing anchor never falls back to another checkout.

Configuration comes from one file: an explicit `OURDESKPET_ENV_FILE`, otherwise the anchored project's `.env`. A missing project `.env` stays the destination for the settings UI to create; the application does not search unrelated working directories or older builds. Without a project anchor, release builds use the application configuration directory's `.env` (`config.env` remains a legacy alternative). An explicit relative env path is based on the project root, or on the application configuration directory for a standalone release. Relative `OURDESKPET_PROMPT_FILE` paths are based on the selected env file's directory. Configuration values are not merged across these locations.

Windows shortcuts themselves contain absolute paths: rerun the repair script after moving the group. Cargo caches also contain absolute build metadata; do not assume moving them preserves a valid build cache. Delete/recreate obsolete compiler caches before building at a new location. Older sibling `RinaDeskBuildCache` directories are no longer used by default. Preserve the installed executable until the replacement build is verified.

`app/src-tauri/target` and any older sibling compiler cache can be removed after a verified local install. The LocalAppData `build-cache` can also be removed when disk space matters, but the next Rust build will be a full rebuild. Keep the installed executable, its `rinadesk-root.txt`, `.env`, artwork and source. Cache cleanup frees disk storage, not the running application's RAM.

Migration was verified with a release build and frontend tests. Native checks launched from an unrelated working directory and from a simulated renamed group; both resolved the expected configuration and prompt and opened Settings. Local cleanup records and pre-migration executables remain outside version control.
