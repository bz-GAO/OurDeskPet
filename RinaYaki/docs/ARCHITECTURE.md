# Architecture

## Process boundary

RinaYaki owns media acquisition, audio processing, model execution, task state and subtitle artifacts. RinaDesk may create jobs and display progress, but must not be required for the pipeline to run.

The current integration uses command-line invocation and JSON state/events through the Desk
bridge. See [Desk bridge](DESK-BRIDGE.md) for the implemented actions. A localhost-only service
can be considered later if queues or multiple clients require it.

## Offline pipeline

New cloud-transcription jobs default to `qwen-audio-3.1-asr-flash-filetrans`.
Existing job snapshots keep their model and submitted task IDs; migration of
the old user default affects only newly created jobs. Fun-ASR is not run as a
second automatic cross-check.

```text
probe -> acquire -> extract_audio -> transcribe -> align
      -> diarize (optional) -> translate -> quality_check -> export
```

Every stage reads immutable upstream artifacts and writes a new artifact. `project.json` records state and provenance. A failed stage can be retried without reacquiring the video.

Planned providers:

- acquisition: local file, yt-dlp, site-specific adapters;
- ASR: Kotoba-Whisper, Whisper, ReazonSpeech, remote APIs;
- alignment: WhisperX or provider-native timestamps;
- diarization: pyannote or provider-native diarization;
- translation: Qwen-MT and configurable compatible APIs;
- export: SRT, ASS, VTT, soft-sub MKV and optional hard-sub MP4.

## Site capability skills

Generic acquisition reports only formats it can actually download. Optional
modules under `src/rinayaki/site_skills/` interpret permission metadata owned by
one site without leaking its strings, quality codes or login behavior into the
pipeline or UI. Bilibili, YouTube and Mellow-Fan already have separate routing
boundaries; only Bilibili currently supplements locked-quality hints.

Every hint is presentation-safe and secret-free: availability, a compact label,
a requirement, a short message and an action kind. Unknown sites never invent
locked formats. The session layer runs one WebView2 child process per site,
using an app-owned profile under local application data. Site skills do not read
profiles, cookies or personal storage. The native acquisition boundary receives
only a validated, short-lived snapshot path for one operation. Desk can ask
Yaki to open the site window, but never receives cookies or browser storage.

The current local Kotoba path provides timestamps, text and confidence, but no
speaker identity. It can also produce plausible-looking errors in low-confidence
segments. Speaker diarization and low-confidence review therefore remain separate
stages; translation and refinement must not guess missing speech.

## Live pipeline

Live processing is a separate runtime rather than a special flag on the offline runner.
The target shape is:

```text
audio capture -> rolling buffer -> VAD -> streaming ASR
              -> incremental translation -> overlay/event sink
```

It may reuse terminology, text normalization and provider interfaces, but it has different requirements:

- bounded latency and backpressure;
- partial and revisable hypotheses;
- audio-device lifecycle and exclusive/shared capture;
- timestamps tied to a monotonic session clock;
- an overlay or widget sink rather than finalized subtitle files.

Recorded live sessions may be converted into normal offline projects for higher-quality retranscription and final export.

The current first phase implements Windows WASAPI loopback capture, server-side
streaming ASR sentence detection, a bounded translation queue with streamed
per-segment translation updates, a rolling desktop subtitle sink and session recording.
ASR and translation advance independently: completed source segments appear immediately,
then the matching translation row is replaced in place as stable chunks arrive. Qwen-MT
Flash/Lite incremental chunks and Plus/Turbo cumulative chunks are normalized to the same
event contract. Local rolling-buffer re-recognition,
local VAD, speaker diarization, direct live-URL capture and conversion into an
offline project remain explicit later stages.

The native settings page now offers **standard (ASR + MT)** (default) and
**LiveTranslate** for new live sessions. The latter is isolated in
`live/livetranslate.py`, using `qwen3.8-livetranslate-flash-realtime` with
`output_modalities=["text"]`; it does not run an additional ASR/MT request,
generate translated speech or submit video frames. The realtime endpoint is
derived from the configured ASR endpoint without changing provider/region.
Source-only display always uses the standard ASR path, regardless of preference.

LiveTranslate source items and translated output items are independent streams,
updated in place by their IDs. Their boundaries are not assumed to match and
they are not FIFO-paired. Source speaker IDs and response token usage are kept
in the event log; usage totals are included in the session record. Pause closes
the current connection; resume offsets timestamps into the same recording and
rejects callbacks from the previous connection. Shutdown sends `session.finish`,
drains the final captions, then closes the socket. A bounded timeout closes a
stalled socket while preserving received captions. No automatic paid fallback.

Selected terminology packs are filtered before LiveTranslate receives them.
Only unambiguous static source/target pairs enter the provider phrase table;
context-sensitive aliases remain in the standard Qwen-MT path. The same setting
and session behavior is available through Yaki's Desk bridge.

## Data ownership

- The job root contains the current hard-subtitled MP4.
- `intermediates/work/` retains imported source, audio, ASR, translations and cache state.
- `intermediates/subtitles/<version>/` contains generated text subtitle formats.
- `intermediates/exports/` contains soft-subtitled MKV and earlier MP4 versions.
- `intermediates/runs/<id>/` contains per-attempt logs, timings, status and text/API artifacts.

See [Video jobs](PIPELINE-JOBS.md) for path bases, cache validity and recovery rules.

SRT and ASS are generated views. The authoritative editable representation will be a versioned JSON schema containing stable segment IDs, timing, speaker, Japanese text, translation, confidence, provenance and review state.

Subtitle export supports canonical JSON, SRT, WebVTT and styled ASS. SRT and VTT
intentionally contain no font or colour policy. ASS carries styles and speaker
metadata when available. The current full-video workflow produces a hard-subtitled
MP4 at the job root; soft-subtitle MKV and versioned subtitle artifacts live under
intermediates. Neither rendering nor muxing replaces the canonical JSON.

## Model and secret policy

Model installers must report download size, expected disk usage and approximate RAM/VRAM requirements before fetching weights. API providers remain disabled until their configuration is present. Secrets belong in an ignored `.env` file or the operating system credential store, never in job manifests or logs.
