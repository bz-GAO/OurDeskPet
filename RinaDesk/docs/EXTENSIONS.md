# Extension integration

The Add tool page lists both RinaYaki and RinaTomo. Each card links to its
GitHub repository; this is a source/download entry, not an automatic installer.
RinaYaki keeps its explicit local folder connection action. RinaTomo is part of
the Desk integration and opens its embedded control page directly. Repository
visibility and release packaging are independent of this UI contract.

The first supported provider is RinaYaki. The board's Add tool page accepts a local
folder chosen by the user. RinaDesk verifies `pyproject.toml` package identity,
the RinaYaki launcher, UI script, package directory, and local Python environment.
It stores the resolved path in the Windows app configuration directory as
`extensions.json`. The path is revalidated before opening the tool. Choosing a
new valid folder replaces the old record; a failed or canceled selection keeps
the previous one.

Assistant reads, live guides, discovery, native launch and bridge actions share the same
registration and project identity validation. Only absolute registered roots are accepted;
relative paths cannot silently depend on Desk's working directory. Identity is parsed from
the TOML project table and required entry files are checked inside the resolved project;
linked entry files/directories are rejected. A missing selected checkout never falls back
to another installation. Source reading does not require a usable Python environment.
Tomo's native launch and assistant lookup share its validated sibling-project resolver.

Registration is bounded and saved using a synced temporary file and replacement, retaining
the old destination on failure. A fresh valid folder selection or disconnect can repair a
corrupt registration without first parsing it. All Yaki child commands explicitly put the
selected project's src on PYTHONPATH and suppress bytecode writes; they do not inherit a
different checkout's PYTHONPATH. Reopening the extension page refreshes status. Changing
the selected root remounts the video/live UI so old previews and task selections are not
silently reused for another installation. Existing background jobs remain owned by Yaki.

Once connected, RinaDesk asks `scripts/desk_bridge.py describe` which tools that
installation exposes. One registered path currently produces separate Video
Translation and Live Translation tabs; relocation, version and uninstall state
remain shared. Older RinaYaki installations without discovery retain the legacy
video-only tab instead of becoming unusable.

The video page can preview
online video URLs/IDs and local files through `scripts/desk_bridge.py` without
starting paid processing. It can also launch the existing standalone UI. The
board's Uninstall extension action only removes
the RinaDesk registration. It does not delete the tool, adapter files, settings,
or video projects. The provider cards link to their source repositories; local
registration and embedded controls remain separate actions.

The embedded pages live in `app/src/extensions/rinayaki` and load only when
their tabs open. They are included in the current RinaDesk build; no separate
UI bundle is downloaded. The Tkinter interface is not embedded directly into
the Tauri board. Instead, the versioned bridge owns validation and starts the
existing RinaYaki workers. The live page mirrors the standalone two-step setup,
reads loopback devices and terminology packs through that bridge, and launches
the final subtitle window as an independent RinaYaki process. Its setup content
scrolls while Continue and Start stay in a fixed action bar. Source-only display
does not submit translation or terminology options. The provider discovery
bridge uses protocol version 1. The preview bridge uses protocol version 1 and returns metadata
and an optional cover image. Older installations without the bridge can still
open their standalone window.
This first slice intentionally does not claim API compatibility based on the
package version alone.

The General settings diagnostics block reports the exact registered Yaki root,
discovered version and bridge protocols. It is the preferred first check when
the standalone tool has changed but the embedded page still behaves like an
older build or checkout.

The embedded page also exposes RinaYaki's shared API, model, request-spacing,
and default-project-directory settings. Secrets are stored by RinaYaki under the
current Windows user's local application-data directory; the bridge reports only
whether a key exists and never returns its value. Standalone and embedded UIs
therefore edit the same current configuration without duplicating credentials in
RinaDesk.

## RinaTomo

The QQ Bot tab mirrors the standalone RinaTomo control panel. It talks only to
RinaTomo's loopback control endpoint (`127.0.0.1:37641`, protocol version 1) and
can read runtime state, start or pause replies, stop the managed chain, restore
the standalone panel, and update the shared feature, permission and auto-start
settings. The bridge never returns the OneBot or NapCat tokens.

The same panel also mirrors notification and night-sleep settings: admin-only notification
master switch, translation/chat/login event switches, and a 24-hour start/end range. Subordinate
event inputs disable when notifications are off; time inputs disable when night sleep is off.
Applying the group sends one `notifications` update through Tomo's v1 control protocol—Desk does
not write Tomo configuration files. Agent translation terminal phases use the protocol's `notify`
command on a best-effort, per-task/per-phase deduplicated path. Chat-reply and login-failure event
sources are still pending even though their switches and protocol fields exist.

When the controller is not running, the tab remains available and can launch the
sibling `RinaTomo/Start-RinaTomo.vbs`. Closing either settings surface does not
stop the bot; explicit shutdown remains the only UI action that ends the managed
Tomo/NapCat process chain. The standalone and embedded pages must keep the same
labels, fields and apply semantics as this contract evolves.

## Subtitle preview synchronization (2026-10-18)

The offline editor reads `style_options` (font labels, font IDs, outline presets, default font)
from the registered Yaki provider. `style_preview` accepts at most 120 characters plus a supported
font ID and six-digit outline color, returning an in-memory PNG. It uses the same bundled-font
Pillow renderer as the native Yaki editor; no system font installation, network, project write,
translation or export is triggered. This aligns the two previews; it is not a claim that Pillow
and the final ASS/libass renderer have identical layout in every video resolution.

Desk debounces preview requests, hides stale images immediately, and ignores late responses after
changing speaker/style or leaving the editor. Missing renderers/fonts produce an explicit preview
failure, not an unrelated browser-font substitute. Download progress is displayed in both UIs;
unknown totals remain indeterminate. Long-video acceptance remains a separate user-run test.
