# RinaDesk bridge

`scripts/desk_bridge.py` is the RinaDesk integration endpoint. It keeps video
inspection and live-runtime ownership inside RinaYaki while the board UI stays
in RinaDesk. `live_options` advertises `translationStreaming`; both the native
setup page and Desk launch the same incremental translation runtime.

Call it with the project's Python environment:

```text
.venv/Scripts/python.exe -X utf8 scripts/desk_bridge.py preview <URL, ID or local path>
```

It prints one JSON result with `protocol_version: 1`, source kind, normalized
source, title, duration (seconds), and an optional thumbnail. Both local and
online thumbnails are bounded JPEG data URLs. On failure it
prints `{"error": "..."}` and exits nonzero. Preview neither creates a project
nor calls paid ASR/translation APIs. RinaDesk runs this interface only after the
user has selected and connected a valid RinaYaki folder.

The bridge also provides project, task, style, export and live-session actions.
RinaDesk calls these actions; RinaYaki owns their execution and runtime data.
For live translation, original-text events and translated snapshots are delivered
independently to the shared subtitle window. Translation begins after each ASR
segment is finalized; this is not speculative translation of unfinished speech.
Desk's model settings include the same live engine choice as the native UI.
The live setup receives bundled font names and outline color presets from
RinaYaki. `live_style_preview` renders the selected bundled font as a bounded
PNG in Yaki, so Desk need not duplicate large font assets. Both launch paths
use the same runtime settings and term packs.

Offline subtitles follow the same rule: `style_options` supplies font names and
outline presets; `style_preview` accepts at most 120 text characters, a bundled
font name and a hexadecimal outline color, and returns a 720×96 PNG data URL.
It shares the native window's preview renderer and does not create a job, write
settings or call a paid API. Desk debounces requests and ignores stale results.
This aligns both preview UIs, not every layout detail of the final ASS renderer.
Desk also displays the existing download progress counters, using an indeterminate
bar when the total is unknown.

## Video quality

Protocol 2 action `video_preview` returns the existing preview fields plus an
acquisition policy and `qualities: [{id, label}]`. Local videos have no
acquisition policy or quality choices. `create.video` includes the chosen
quality and whether the isolated app session was used. The legacy `preview`
command remains compatible.

The standalone Yaki UI may also display unavailable qualities reported by a
site skill. Until Desk implements the matching hover and permission dialog,
the bridge omits those locked choices and exposes downloadable qualities only.

`web_session_open` launches RinaYaki's WebView2 child for the selected video
page. Desk never inspects a daily browser profile and never receives cookies;
the per-site profile remains under RinaYaki's config directory. Close the login
window before previewing again so yt-dlp can read that isolated profile.
`video_preview` automatically uses the persisted app session when one exists.

Quality options come from non-DRM video formats; they are candidates, not a
claim that every CDN URL has already been tested. Download re-extracts metadata
and checks the selected format. Explicit resolutions never fall back to a lower
resolution. Cache keys separate source and quality; completed downloads have an
atomic receipt. Raw downloader output, headers and signed format URLs are not
written to logs or exported metadata.
