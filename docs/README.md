# OurDeskPet Documentation Index

Last updated: 2026-05-28

This folder is the central home for project management documentation.

Use this structure:

- `docs\README.md`: documentation map and maintenance rules.
- `docs\PROJECT_PLAN.md`: stable product direction, architecture boundaries, and development rules.
- `docs\MILESTONES.md`: milestone status and exit criteria.
- `docs\FEATURES.md`: feature inventory and scope status.
- `docs\QA_CHECKLIST.md`: repeatable checks for manual and automated testing.
- `docs\DEV_LOG.md`: chronological development log and important decisions.
- `docs\GITHUB_PREP.md`: checklist for first GitHub publication.
- `docs\modules\*.md`: focused module plans and optimization packages.

Keep implementation-local notes outside this folder only when they are tied to a specific artifact:

- `app\README.md`: app-specific development commands and structure.
- `assets\rina\README.md`: asset replacement and naming notes.
- `prompts\rina_system_prompt.md`: actual prompt content loaded by the app.

Do not store generated dependency documentation, build output notes, or `node_modules` content as project documentation.

## Reading Order

For orientation:

1. `PROJECT_PLAN.md`
2. `MILESTONES.md`
3. `FEATURES.md`
4. `modules\OPTIMIZATION_PACKAGES.md`

For active development:

1. Read the relevant module plan in `docs\modules`.
2. Check `QA_CHECKLIST.md` for verification expectations.
3. After work, update `DEV_LOG.md`.
4. If scope changed, update `MILESTONES.md` and `FEATURES.md`.

For GitHub publishing:

1. Read `GITHUB_PREP.md`.
2. Re-check `.gitignore`.
3. Confirm `.env` and build caches are not staged.

## Current Phase

M0-M4 are initially implemented.

The project is now in an optimization phase:

- `R1`: reliability and long-conversation management
- `A1`: art and pet-state presentation
- `L1`: LLM capability expansion
- `M4P`: screenshot and image polish
- `S1`: settings and management surface

The canonical optimization plan is:

```text
docs\modules\OPTIMIZATION_PACKAGES.md
```
