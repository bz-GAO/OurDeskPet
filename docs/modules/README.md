# Module Plans

Last updated: 2026-05-28

This folder holds focused plans for a milestone, module, or optimization package.

Module documents should answer:

- What is the goal?
- What is in scope?
- What is out of scope?
- What decisions have already been made?
- What checks prove the work is good enough?

## Current Documents

| File | Purpose | Status |
| --- | --- | --- |
| `M3_LLM_CHAT.md` | API-backed dialogue and OpenAI-compatible chat plan | Implemented; useful for config/context reference |
| `M4_REGION_CAPTURE.md` | Screenshot and image handoff plan | Initially complete; system clipper route accepted |
| `OPTIMIZATION_PACKAGES.md` | Post-M4 optimization queue | Active planning source |

## Maintenance Rules

- Keep module plans short enough to scan before implementation.
- Move broad product decisions back into `docs\PROJECT_PLAN.md`.
- Move feature status changes into `docs\FEATURES.md`.
- Move chronological implementation notes into `docs\DEV_LOG.md`.
- Do not duplicate long chat transcripts or temporary debugging output here.
