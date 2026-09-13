# Final assets and provenance

Final artwork lives in `app/public/assets/rina`; Tauri icons live in `app/src-tauri/icons`. [manifest.json](manifest.json) records paths, byte sizes, SHA-256 hashes, and source groups. Update it when artwork changes, then run `python scripts/check_repository.py`.

| Asset | Origin and processing |
| --- | --- |
| `summer-v1/{idle,drag,talk,sleep}.png` | Chibi cardigan outfit based on first-season promotional artwork. Idle/drag received clothing corrections; talk/sleep use the approved two-pose sheet. Local background removal, edge cleanup, and canvas normalization |
| `winter-v1/{idle,drag,talk,sleep}.png` | Jacket outfit based on second-season promotional artwork. Talk/sleep adapt the summer poses. Pack names distinguish designs, not an assertion that each season contains only one uniform |
| `rina-idle-v1.png` | Astromeda merchandise-inspired redraw with the display base and background removed; shared across states |
| `boards/paper-v3.png` | Anime paper-board reference redraw, cropped into a pale chat backdrop |
| `boards/electronic-v3.png`, `electronic-blank-v3.png` | Expression and blank-screen board images used for masks and indicators |
| `boards/electronic-faithful.svg` | Display asset embedding the expression image and clipping its exterior background; retains raster pixels |
| `icon.svg` and Tauri icons | Approved redraw of Rina's character symbol and exported sizes; SVG also serves as the browser icon |

The manifest links to SPICE and Comic Natalie uniform promotional images, the Astromeda product page, Animate Times paper-board references, and episode-six electronic-board images. The icon was based on previously collected character references. The former SIF2 character page returned 404 during the latest check; it is retained as a historical source, not a currently accessible license statement.

Reference originals, generation prompts, rejected drafts, extraction scripts, and review screenshots remain in `.local-archive/2026-09-13/project`, preserving relative paths. `moved-files.json` records archived file hashes. These process files are excluded from Git.

These are unofficial derivative character assets. Attribution and AI-assisted redrawing do not change ownership of the original characters, merchandise designs, or reference images. This repository does not grant permission on behalf of their rights holders.
