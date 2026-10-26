# Project languages

On the project settings page, new jobs default to automatic source detection and
Simplified Chinese subtitles. Source choices are Auto, Chinese, English and
Japanese; targets are Simplified Chinese, English and Japanese. Target Auto is
not offered. Languages are fixed after Start and restored when resuming a task.
Old tasks without language fields retain Japanese to Simplified Chinese.

Settings live with the project's source record in destination.local.json. They
flow into the worker, ASR, translation (including single-cue recovery), refinement,
prepared results and subtitle export. Auto omits ASR language_hints and uses MT
source_lang=auto. No separate language-detection model call is made. Automatic
source subtitle metadata uses und (undetermined), not a guessed detected language.

ASR cache identity includes the source language, not the target. Translation and
refinement cache identities include both; individual requests include the language
options or instructions. Export versions incorporate subtitle language metadata.
Prepared/config language mismatches are rejected rather than silently exporting
stale text. Changing an in-progress project's languages is not exposed in the UI;
create a new project for another pair. Cross-project cache sharing is not implemented.

Provider references:
- https://help.aliyun.com/en/model-studio/fun-asr-recorded-speech-recognition-http-api
- https://help.aliyun.com/en/model-studio/qwen-mt-api

Validation uses mocked cloud calls and local FFmpeg fixtures. Live multilingual
recognition/translation quality still needs user acceptance with actual media.
