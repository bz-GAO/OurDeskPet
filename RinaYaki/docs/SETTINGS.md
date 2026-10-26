# Settings and local state

The native RinaYaki window and the RinaDesk extension use the same settings
service. On Windows, user changes are stored under `%LOCALAPPDATA%\RinaYaki`:

New projects default to `output` under the resolved RinaYaki project root;
`RINAYAKI_CONFIG_HOME` selects settings storage, not that implicit output root. Native and Desk UIs share the
same setting; either can change the default project directory. The default output
is created only when preparing a destination, never by merely reading settings.
Existing jobs and media retain their original locations; installing or updating
the application does not move them. Missing custom directories remain errors.

- `settings.json` contains endpoints, model names, request spacing, and the
  optional default project directory;
- `credentials.env` contains the DashScope API key and is never returned to a UI;
- the repository `.env` remains a read-only compatibility fallback.

The repository ignores `.env`, `.local/`, virtual environments, tools, models,
and workspaces. If a legacy cached job creates the sibling `RinaYakiCache`
runtime directory, it also creates a catch-all `.gitignore`. These files are
local state and must not be committed.

## Runtime separation

Creating or resuming preparation writes `intermediates/config.snapshot.json`
inside the video project. It contains no credential. The snapshot fixes the API
endpoints, model names, and minimum request interval for that project so changing
global user settings cannot silently change a resumed job. The current user API
key is read only when a cloud client is constructed.

Project media, ASR, translation, refinement caches, progress, and run records
remain under each project's `intermediates/` directory. `RinaYakiCache` is kept
only for legacy cached jobs and process-control state.

The production video pipeline currently uses Alibaba Cloud Filetrans ASR.
Kotoba Whisper remains an available provider implementation but is not exposed
as a production setting until it is integrated into the resumable workflow.
