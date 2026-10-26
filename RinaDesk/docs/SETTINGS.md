# Chat and startup settings

Open the pet's small board, then click its smile to open Settings. The Chat tab groups context, search and project-assistant permissions; the General tab contains startup at login and runtime diagnostics.

## Chat

- Lightweight: 8 verbatim turns, compaction threshold 12, summary target/cap 300/500 characters, text budget 12000 characters.
- Balanced: 12 verbatim turns, threshold 20, summary target/cap 600/1000, text budget 24000.
- Custom: edit these values with validation. Threshold must exceed retained turns; summary cap must not be below its target. Character counts are approximate context limits, not token counts.
- Storage: Auto-save / Do not save is also available in the Chat header. The default is the local RinaDesk data folder's `Conversations`; the folder picker changes future saves without moving existing files. This preference is saved immediately, independently of the Chat parameter form. Re-enabling saving includes the current conversation's existing text; disabling it does not delete old saves.
- Search: default Auto/Off/Required mode and service switch. An official DeepSeek profile reuses its model key for DeepSeek Search. Tavily is optional for other providers and as a fallback; a blank field preserves its stored key. The normal UI uses the built-in endpoint; pre-existing advanced endpoint configuration is preserved. Advanced contains the stalled-read timeout.
- Project assistant: the bundled guide is always available. The source-read switch separately grants bounded read-only access to supported files in RinaDesk, RinaYaki and RinaTomo. It does not grant writes, command execution, UI control, or access to local configuration and credentials.

Save explicitly. New requests use saved values; in-progress replies and summary requests keep their original configuration. Existing summarized text cannot recover details merely by increasing a limit. Lower settings are applied on the next compaction/context preparation; full visible chat history is not erased.

Defaults refresh in an open chat until its search selector is manually changed. A manual chat selection is an override for that chat window's lifetime; it does not change the saved default. The existing chat selector remains available.

All dialogue settings share one selected `.env` with API profiles, using the same parser when saving and running. A local project uses its own `.env` even before that file is created; settings from another checkout or the shell's working directory are not mixed in. See [configuration lookup](DEVELOPMENT.md#portable-local-launcher-and-group-layout) for explicit overrides and standalone releases. Saves preserve unrelated fields and use the same write lock, revision conflict checks and temporary-file replacement. Unsaved dialogue drafts survive tab switches and are protected when closing settings. External changes are detected; reload explicitly if a draft conflicts. Keys are never returned to the frontend after storage. Existing process-environment overrides still take precedence over file values during model configuration.

Fields: `OURDESKPET_HISTORY_KEEP`, `OURDESKPET_HISTORY_TRIGGER`, `OURDESKPET_SUMMARY_TARGET`, `OURDESKPET_SUMMARY_CAP`, `OURDESKPET_CONTEXT_CHARS`, `OURDESKPET_SEARCH_MODE`, `OURDESKPET_SEARCH_ENABLED`, `OURDESKPET_TAVILY_BASE_URL`, `TAVILY_API_KEY`, `OURDESKPET_READ_TIMEOUT_SECS`, `OURDESKPET_PROJECT_READ_ENABLED`. Old configurations without history fields preserve the previous 12000-character cap until settings are saved. Project source reading defaults to false when the field is absent.

## Account balances and daily estimates

Settings > API configuration and the Chat header share an account card. Platform names
come from exact configured endpoint hosts: DeepSeek, Alibaba Model Studio (阿里云百炼),
or Qianwen AI Platform (千问AI平台). Unknown/proxy hosts are not guessed from model names.
Identical provider/key fingerprints share one balance and accumulate all three projects'
recorded calls. Distinct keys are kept separate because a host does not prove account ownership.

DeepSeek uses its documented `/user/balance` endpoint. Alibaba uses the fixed read-only
`QueryAccountBalance` operation after connecting a RAM AccessKey in this page. This is a
separate, read-only balance connection: a DashScope model API key cannot query the Alibaba
Cloud account balance. The minimum
documented permission is `bss:DescribeAcccount`; grant balance-query access only. Authorizations
are bound to the selected account fingerprint and encrypted with current-user Windows DPAPI
under local application data; plaintext secrets are never returned to the UI/model. The separate
authorization file is decrypted and compared after each atomic save before success is reported.
Saved authorization survives application restart; blank credential fields are never treated as
disconnecting. A connected account hides the credential form until “更新授权” is selected.
The separate
`maas.qianwenaiapi.com` platform is identified but its management-login adapter is not yet connected.
It displays an unavailable state and a console link instead of trying Alibaba credentials.

Balance refresh queries the cloud on startup and every ten minutes while Desk is running;
manual refresh bypasses the cache. Failed queries are eligible for retry after thirty seconds
instead of occupying the ten-minute success cache. Error labels distinguish authorization,
rate limiting, network/timeout and invalid responses without exposing upstream response bodies.
Successful balances are saved separately as `balance-<provider>-<key-hash>.json` in Desk's local
data directory (amount, currency and timestamp only, never a key). On a transient outage the
last successful result can survive restart and is marked stale; authorization errors never
fall back to a cached amount. Restart always tries the cloud before reading this fallback.
Usage updates received during a balance query schedule a follow-up read instead of being dropped.
Failed refreshes retain a marked stale result. Local daily totals refresh when
Chat calls complete and are reread every fifteen seconds in visible account cards. System-local
date changes start a new recording day; closing Chat or restarting does not erase totals. The
Settings card can expand a seven-day chart assembled from the three local ledgers, with missing
days shown as zero. Each project owns its own atomic `billing.json` under its configured local-data
directory and retains at most 31 daily totals. Legacy one-day ledgers migrate on their next write.
Tool writers use a cross-process file lock. Corrupt files are not overwritten with zero.
No keys, prompts, media or conversation bodies are persisted in the daily ledger.
Successful non-empty DeepSeek Search requests are included at the documented CNY list rate;
failed, timed-out and empty searches are not recorded as spend. Temporary launch waivers are
treated like other promotions and are not deducted from the local reference estimate.

Amounts are **CNY reference-price estimates**, starting when recording is enabled, not the
whole account's authoritative bill. Chat rounds, summaries/titles, Tomo responses, Yaki translation,
refinement and completed ASR results are recorded. Missing/unsupported usage and unsupported
live audio pricing mark totals incomplete (`*` or unavailable), never falsely zero. Estimates do
not deduct free quotas, gifts or promotions. Reviewed pricing: 2026-10-17; DeepSeek Flash uses
the peak-rate reference. International-region/Qianwen pricing and unlisted models must not be
assumed equivalent. See [DeepSeek prices](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/),
[Alibaba prices](https://help.aliyun.com/zh/model-studio/model-pricing), and
[Alibaba balance API](https://help.aliyun.com/zh/user-center/developer-reference/api-bssopenapi-2017-12-14-queryaccountbalance).

The online balance and local ledgers are intentionally separate. Online balance is the provider's
authoritative remaining account amount. Each project's local ledger records only calls made through
that project and is what the combined today/history view reads. A unified price catalog means that
Desk, Yaki and Tomo use the same provider/model aliases, currency and billing units, plus identical
input/output/cache golden examples; it does not copy an online bill into local files or merge their
runtime ledgers.

Changing an API key does not erase the former fingerprint's local totals. Desk lists unmatched
fingerprints as separate “本机记录” accounts without a balance query or authorization controls;
it never merges two keys merely because they use the same provider. Yaki also treats saved project
response/task IDs as a durable receipt set: after a successful prepare run it reconciles those
receipts into the central ledger, so a transient ledger-write failure can be repaired without
charging again or double-counting. Filetrans estimates use recorded audio duration rather than LLM
token rates.

## Project assistant approval

Project-assistant setting proposals have a separate default-off flag,
`OURDESKPET_PROJECT_SETTINGS_ENABLED`. Enable “允许助手提出安全设置修改” and save.
The assistant may propose safe Chat parameters or the General page's Windows startup
toggle; a centered before/after confirmation dialog is required for each save. Startup is confirmed
separately from Chat file changes. It cannot change permissions, paths, keys or other projects.
See [confirmed setting changes](CHAT.md#confirmed-setting-changes) for boundaries.

## Startup at login

Windows only, opt-in. The toggle writes or removes the current user's `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` value named `RinaDesk`, pointing to the current executable with a quoted path. It does not change machine-wide startup or require administrator privileges. No chat/settings window is opened automatically. If the executable moves, turn the option off and on to refresh its location. Windows may independently disable startup entries in system settings. A second shortcut launch focuses the existing pet; installation and updater/uninstaller integration remain separate work.

The test run does not enable startup for the developer's real login. Native tests check that the control is available; actual next-login behavior is not exercised by those tests.

## Runtime diagnostics

General shows the running executable, configuration file, build time/source revision and the
resolved RinaYaki/RinaTomo locations with protocol state. Copy this block when a rebuilt source tree
and the launched application disagree. Build metadata is embedded by `scripts/Build-Local.ps1`;
paths and tool availability are resolved again from the running process.
Display/copy removes Windows verbatim path prefixes (`\\?\` / `\\?\UNC\`) only for readability;
filesystem access still uses the original resolved path. Both account cards have a compact
official-console link; the Alibaba connection form additionally links to RAM and the authorization
guide. Opening a console does not automatically grant API authorization.

Balance queries use independent account locks and coalesce concurrent refreshes. The UI
loads local usage first, then updates each cloud balance as it arrives. Success caches last
ten minutes; transient failures retry after thirty seconds. Cached offline values retain
their original timestamp. Replacing billing authorization invalidates active cache slots.
Draft discard, history/file removal, new conversation, extension disconnect and assistant
setting proposals use the shared modal component, not expanded conversation bubbles.

Local regression suites cover preset saves, secret preservation, conflict rejection, project-path confinement, approval expiry, date rollover and billing refresh races. The opt-in `billing::live_test::three_paid_requests` smoke test is ignored by default and requires `RINADESK_PAID_SMOKE=three-requests`. It makes at most three completion requests, never retries, uses synthetic reference text only and records actual usage. Run it only with explicit paid-test authorization. It does not test an entire UI turn or transfer local source files.
