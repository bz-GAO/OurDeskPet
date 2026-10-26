# Implementation references

External projects are references, not runtime dependencies. Record what was adopted and what was deliberately left out.

## DeepSeek Harness

- Upstream: [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness), MIT license.
- Reviewed subsystem: [session-title README](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-title/README.md) and [session-title design](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session-title.md).
- Adopted boundary: create a usable fallback from the first human message immediately; never let title work block the reply; explicit user renames remain authoritative.
- RinaDesk choice (2026-10-20): local cleanup supplies an immediate temporary title; after the first complete nonempty answer, one asynchronous model request refines it. Explicit renames take priority; failure retains the fallback. Restored conversations are not retitled. This adopts lifecycle boundaries without importing Harness code or providers.

The extra title request uses bounded conversation text and records usage in the existing ledger. No search or tools are included. The current conversation contract is documented in [CHAT.md](CHAT.md).
