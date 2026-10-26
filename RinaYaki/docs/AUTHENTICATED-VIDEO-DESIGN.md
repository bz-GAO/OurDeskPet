# Authenticated video acquisition

Status: Stage 2 is implemented in Yaki and exposed through the Desk bridge.
Persistent WebView2 sessions can be used by one preview/download operation
without touching a daily browser profile. Desk delegates login to Yaki and
does not read session material itself.

## Product boundary

- Login is optional and starts only after an anonymous preview reports that the
  video requires an account or the user explicitly selects Login.
- RinaYaki may use only the current website's session and only for the current
  preview/download. It never asks the user to export or import cookies.
- Project records store quality and a non-secret session reference at most.
  Cookies, authorization headers, signed media URLs and account identifiers do
  not enter projects, logs, command history or cache keys.
- Account permissions remain authoritative. DRM-protected media is rejected.
- The authenticated flow is completed in RinaYaki before Desk exposes it.

## Rejected approaches

### Reading the daily Chromium profile

`yt-dlp --cookies-from-browser` is useful as an expert command-line feature, but
it is not a dependable application boundary on Windows. A running browser can
lock its cookie database, and current Chromium releases protect cookies with
application-bound encryption. Asking users to close their browser is disruptive
and still does not guarantee decryption.

### Cookie-file import

Netscape cookie files expose a security-sensitive implementation detail, are
easy to export too broadly, expire unpredictably and create a new secret-lifecycle
problem. RinaYaki does not expose this workflow.

### Attaching automation to the normal browser profile

Remote debugging of the default Chrome data directory is intentionally restricted
in current Chromium. Launching a daily profile with weakened debugging or locking
features would increase risk and compete with the user's normal browser.

## Candidate A: app-owned login window

Use WebView2 with a RinaYaki-owned user-data folder outside the source tree and
media projects. The user signs in through the real website in this window.
RinaYaki can request cookies for the specific video origin through WebView2's
cookie manager and hand them to the extractor only for one operation.

The first implementation runs pywebview/Edge Chromium in a child process and
uses `%LOCALAPPDATA%/RinaYaki/web_sessions/<site>` as its storage folder. The
native window owns that child process, one process may use a site profile at a
time, and closing Yaki closes its login windows. While the window is open, its
child writes a user-private, short-lived cookie snapshot requested over the
parent/child stdio pipe; the caller validates its path and removes it after the
extractor exits. After restart, yt-dlp may read only this app-owned profile.
Neither path exposes cookie import/export in the UI.

Known site names use stable profile keys. Other HTTPS video pages use a hashed
hostname key and show the hostname in the window title, so adding a site does not
require embedding its identity in the generic session layer.

Advantages:

- no conflict with the user's normal Edge process or profile;
- no browser database copying or OS decryption workaround;
- login, logout and per-site clearing have an understandable UI;
- session access can be restricted to the requested origin.

Limits:

- the user signs in once more inside RinaYaki;
- some sites require browser state beyond cookies, a matching browser
  fingerprint, or in-page playback data and still need a site-specific adapter;
- WebView2 adds a Windows-specific UI/runtime boundary.

## Candidate B: browser extension bridge

If reusing the exact daily Edge session is a hard requirement, use a small
extension with narrowly scoped host permissions and a native-messaging host.
The app opens the target page in the user's browser; after explicit confirmation,
the extension sends only the active site's required session material to the
local RinaYaki host.

Advantages:

- uses the session already open in the user's chosen browser;
- works while the browser is running;
- the browser remains responsible for decrypting its own storage.

Limits:

- requires extension installation, store/release maintenance and visible
  permissions;
- needs a signed, authenticated local protocol with strict origin checks;
- Firefox and Chromium browsers need separate packaging/testing.

## Recommended order

1. Keep anonymous preview and quality selection as the default path.
2. Continue per-site validation behind separate adapters. Bilibili member
   quality discovery works. The tested Mellow-Fan member video can be acquired
   from the app-owned session; this does not imply support for every page/site.
3. Test logout, expiry, trial/full detection and download cleanup for each site.
4. Add Candidate B only if sharing the daily browser session is important enough
   to justify an extension.
5. Keep the existing Desk bridge contract stable while site adapters evolve.

## Primary references

- yt-dlp cookie guidance: https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp
- Chrome remote debugging changes: https://developer.chrome.com/blog/remote-debugging-port
- WebView2 user-data folders: https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder
- WebView2 cookie manager: https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2cookiemanager.getcookiesasync
- Edge native messaging: https://learn.microsoft.com/en-us/microsoft-edge/extensions-chromium/developer-guide/native-messaging
