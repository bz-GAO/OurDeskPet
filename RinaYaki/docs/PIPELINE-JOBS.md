# Video jobs and playback

The full pipeline accepts a URL or a local video. It produces a hard-subtitled H.264/AAC MP4 at the job root. Chinese and Japanese subtitles are burned into the picture, so playback does not depend on subtitle-track support. The soft-subtitled MKV and standalone subtitles remain available for editing and comparison.

```text
workspaces/episode/
  episode.<content-version>.mp4
  intermediates/
    project.json
    pipeline.json
    work/                    # source, audio, ASR, translation, refinement, cache state
    subtitles/<version>/     # canonical JSON, source/Chinese/bilingual SRT, bilingual ASS
    exports/                 # soft-subtitled MKV with embedded fonts
      previous/              # earlier hard-subtitled versions
    runs/<time-id>/
      run.json
      timings.json
      logs/
      artifacts/             # ASR/translation/refinement/export records for this attempt
```

Manifest paths are relative to the job root (`path_base: job_root`), including the manifests inside run folders. Source media is retained once, while each attempt snapshots its text and API results. Reused results are retained in the snapshot; an attempt does not imply another paid request. The top-level MP4 is the file to open or upload to players that only process video. Subtitle versions use separate directories, and changed source/subtitle/style/font content changes the final video filename. Earlier MP4 versions move under `exports/previous` only after the replacement validates successfully.

## Run from the repository root

```powershell
.\.venv\Scripts\python.exe scripts/full_video_pipeline.py --input .\clip.mp4 --project-dir .\workspaces\episode --stem episode --ffmpeg .\.tools\ffmpeg\ffmpeg.exe
```

For online acquisition, replace `--input .\clip.mp4` with `--url <video-url>`. The default downloader is `.tools/yt-dlp.exe` on Windows; `--yt-dlp` overrides it. These full-pipeline commands explicitly use the configured cloud ASR and translation APIs and may incur provider charges. Ordinary tests use mocks.

Each job is bound to its URL or local source content digest. Use a new job directory for another source; a mismatched source fails before it can reuse old results. Resume with the same arguments. Local input is copied into the job. ASR and translation caches are validated against their upstream input; matching individual batch requests can still be reused. Replaced audio/subtitle intermediates are written atomically. Failed refinement retains the draft and records its fallback; it is not silently retried on every resume. To explicitly retry a cached failed refinement batch, remove its batch JSON and `refined.cache.json` under `work/05_refinement` before rerunning (this can issue paid requests).

One process may write a job at a time. Current lifecycle locks are OS-owned: a crash releases ownership even though `.running.lock` remains on disk. Do not manually remove the file to bypass worker exclusion; see [recovery semantics](UI-AND-RECOVERY.md). Legacy flat workspaces require a new job directory; they are not silently rearranged.

## Subtitle size

ASS uses a 1920 x 1080 layout with Chinese size 68 and Japanese size 48 (previously 56 and 40), bottom margin 55. The style scales with video resolution. SRT has no reliable embedded font-size control; use the MP4 for consistent appearance.

## Verification and remaining work

The supervised Liella! Radio #291 run found a numbered translation response that merged cues. Invalid or truncated numbered batches now recover using one request per input cue. Original responses and repair requests are retained and cached; repeated resumes reuse them. A malformed single-cue response stops the job rather than retrying without a bound. This can issue additional provider requests for the failed batch.

The suite covers changed-input cache invalidation, request reuse, duplicate IDs, concurrent job rejection, subtitle serialization and real FFmpeg exports. Enable the optional local media test with `RINAYAKI_TEST_FFMPEG` pointing at FFmpeg, then run `python -m unittest discover -s tests -v`. No downloaded videos or API credentials are required. A separate end-to-end local check used simulated cloud responses and verified two attempt folders and cache reuse.

Reading-speed-aware segmentation, offline translation terminology controls and broader provider-specific retry policies remain future work. Realtime controls and job status are exposed through the RinaDesk bridge. Old development downloads, transcripts and API test records have been removed; source tests and tools remain.
