# Launcher and recovery

Developer reference for acquisition and recovery. Everyday use is covered by [the user guide](user/README.md).

Double-click `Start-RinaYaki.vbs` on Windows. The launcher resolves its tools and
Python environment relative to itself. Users enter the project destination/name
on the second page. New tasks write directly there, with location/name fixed
after Start. Existing cached tasks keep their verified publication workflow.
Recreate the virtual environment if its Python installation no longer exists.

Paste a YouTube/Bilibili URL, a BV identifier, an 11-character YouTube identifier,
or choose a local video with the folder button. Preview fetches metadata and an
optional remote thumbnail, without calling a language model. Local previews use
the filename and an FFmpeg-sampled frame (neutral cover on failure). Continue
opens the required project settings. Preview is separate from Start: only Start
launches the paid ASR/translation preparation. It stops before subtitle/video
export; Continue opens per-speaker style editing and a second Continue exports.
See [Video workflow contract](development/VIDEO-WORKFLOW.md). IDs are candidates, not proof that a
video exists; metadata lookup validates availability. Channels, playlists and
ongoing livestreams are not supported. Other single-video pages are attempted
through yt-dlp, without promising support for every website.

The native launcher previews anonymously until an app-owned login profile is
created. Native and Desk acquisition use Yaki's app-owned session boundary; the
Desk login button delegates to Yaki rather than owning another profile. It lists the non-DRM resolutions reported by the
site and checks the selected format again before download. Generic sites use the video's short edge so a
1080x1920 vertical source is still labelled `1080P`. A site skill
may append a locked choice with `🔒`; hovering it explains the requirement and
clicking it opens a small permission dialog. Its action opens the matching page
inside RinaYaki's login window. Unknown sites show only verified, downloadable
qualities.

Bilibili uses its quality codes and full site labels, such as `1080P 高清` and
`1080P 60帧`, instead of inferring tiers from pixel dimensions. Locked choices
appear only when its extractor reports a declared premium format that is absent
from the current session's formats. YouTube URLs and 11-character
identifiers share one input path, and the launcher enables an installed Node
runtime for yt-dlp automatically. Mellow-Fan has an isolated error/capability
adapter. Its WebView login and playback work, but its current yt-dlp webpage
request can still receive a site-side 404; that path needs an in-page adapter.
The cover preview is independent of the quality choice.
The native `登录` button now opens an app-owned WebView2 window for the detected
site. Each known site, and each hashed unknown hostname, has a persistent profile under
`%LOCALAPPDATA%\RinaYaki\web_sessions`; it is separate from daily browser data,
source code and media projects. One profile is opened at a time, and closing
RinaYaki closes the child login windows. RinaYaki does not inspect daily browser
profiles and does not accept exported cookie files.

Native preview requests only the current origin's cookies from an open login
window and removes its internal snapshot after use. If the window is closed,
yt-dlp reads only RinaYaki's app-owned profile. Project data contains just
`session: app`, never cookie values, signed URLs or account identifiers. See
[Authenticated video design](AUTHENTICATED-VIDEO-DESIGN.md).
Keep ownership and future login changes aligned with [the Desk bridge contract](DESK-BRIDGE.md). The app cannot bypass account permissions or DRM.

Downloads use platform-served media streams, not the creator's upload master.
Automatic quality chooses the best accessible stream; explicit resolution stays
exact. Combining audio/video or changing the container does not re-encode them.
The legacy downloader still caps its default at 720p for old jobs. Member/PPV
availability must be validated by the site; visible metadata or a trial player
does not establish access to the full video.

Workers are detached Windows processes, with launcher output saved inside each
job's `intermediates/launcher.log`. Closing the UI does not stop them. Reopening
the same input and explicitly selecting its pending task on the project page
attaches to a running job or resumes cached work. Persistent stage progress lives
in `intermediates/progress.json`; direct-job control lives in `intermediates/control.local.json`; legacy migration
state remains in cache `.control` records. This is
stage-level progress, not a fabricated percentage. Rebooting Windows still
stops a worker; relaunch the task to resume.

## Reliability changes

- OS-owned file locks replace exclusive file creation. The `.running.lock` file
  intentionally remains; the OS releases ownership on a crash. Do not delete it.
- ASR task IDs are atomically recorded as soon as submission returns. Resume
  polls the existing task rather than uploading/submitting again.
- A pre-submission marker catches the narrow ambiguous interval before the task
  ID is recorded. That case pauses for provider task-history review instead of
  guessing and possibly charging twice. Failed/expired remote tasks similarly
  need explicit review; they are not silently replaced.
- GET operations retry transient transport failures and selected 5xx/408/429
  responses; inference POST operations retry explicit 429 rejection only.
  Maximum four attempts, exponential delay, capped numeric Retry-After support.
  Ambiguous inference timeouts are not blindly retried.
- Existing numbered-cue recovery and content-keyed caches remain in use.

This is not a guarantee of automatic recovery from every provider failure.
Ambiguous paid-provider state still requires explicit review.
