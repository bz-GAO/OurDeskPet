# Repository cleanup and validation — September 13, 2026

## Placement fix

Before calculating a destination, `pet_placement.rs` checks whether the bottom 180 by 162 logical-pixel character area intersects visible chat or settings windows. It uses the pet's current monitor DPI; the transparent upper portion of its host window does not trigger movement. With no intersection, it returns `side: unchanged` without calling `set_position`. Otherwise, the existing lower-right preference and multi-window avoidance remain in effect.

All 18 Rust tests passed, including transparent space, touching edges, one-pixel overlap, separate monitors, and scaling. An isolated native Windows instance passed six scenarios: unobstructed first chat open, overlapping chat open, repeated open, unobstructed first settings open, overlapping settings open, and a pet positioned beside the panel. No real API was used.

## File organization

- 277 intermediate images, old packs, references, screenshots, historical documents, and unused scripts were moved individually into `.local-archive/2026-09-13/project`. Originals remain intact; the parent `moved-files.json` records original paths, sizes, and SHA-256 hashes.
- The Vite icon was archived only after its `index.html` reference was replaced with the approved Rina SVG.
- 20 final images/icons remain, approximately 7.44 MiB. Runtime artwork lives in `app/public/assets/rina`; required desktop icons and the icon master are retained.
- Start-Rina.cmd and Develop-Rina.cmd were archived. RinaDesk.lnk remains at the local root with its target unchanged, but is ignored by Git. Terminal commands are documented in DEVELOPMENT.md.
- README, DEVELOPMENT, and ROADMAP replace the overlapping historical documentation. Prompt research and its original draft are separate from the active prompt.
- The machine-specific Cargo output path was removed from configuration. The maintainer's release build uses `CARGO_TARGET_DIR` to retain the existing shortcut target; new clones can use Cargo defaults.

## Git and validation

The cleanup initially prepared the working tree without staging or publishing. The owner subsequently requested publication, and the changes were committed as `bbac270` on `main`. That commit includes work accumulated over several sessions. No history was rewritten.

`python scripts/check_repository.py` validates asset hashes, the final-image allowlist, and exclusion of `.env`, shortcuts, and local archives. It does not read real secret values and does not replace commit review.

The complete historical development log remains at `.local-archive/2026-09-13/project/docs/DEV_LOG.md`; other archived documents retain their relative structure. Old images already present in earlier commits remain in Git history.

Final checks passed: artwork, Markdown, and notification tests; release build; current documentation links; and hashes for all 277 archived originals. The existing RinaDesk.lnk points to the updated executable.
