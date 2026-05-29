# GitHub Preparation Checklist

Last updated: 2026-05-29

This checklist is for publishing `E:\OurDeskPet` to GitHub.

## Current Recommendation

The project is ready for an initial GitHub repository after one final local review.

Selected repository visibility:

- Private for the initial upload.
- Public should wait until image assets and private notes are reviewed.

## Before First Commit

- [x] Confirm the repository root is `E:\OurDeskPet`.
- [x] Initialize local Git repository.
- [x] Rename default local branch to `main`.
- [x] Confirm `.env` exists locally but is ignored.
- [x] Confirm `.env.example` is safe to publish.
- [x] Confirm `app\node_modules` is ignored.
- [x] Confirm `app\dist` is ignored.
- [x] Confirm Rust `target` output is ignored.
- [x] Confirm `logs` are ignored.
- [x] Confirm `E:\OurDeskPetBuildCache` is outside the repository.
- [x] Review image assets under `assets\rina` and `app\public\assets\rina` for current private upload.
- [x] Decide whether the Rina images are acceptable for the chosen repo visibility. Private only for now.
- [x] Review `README.md` for public-facing clarity.

## Suggested First Commit

```text
Initial OurDeskPet prototype through M4
```

Suggested commit scope:

- app source
- prompt file
- assets needed for the current prototype
- docs
- `.env.example`
- `.gitignore`
- root `README.md`

## Suggested First Tags Later

Only tag after a clean run:

```text
v0.1.0-prototype
```

## Useful Commands

Run from `E:\OurDeskPet`.

Initialize repository:

```powershell
git init
git status --short
```

Review ignored files:

```powershell
git status --ignored --short
```

Stage and commit:

```powershell
git add .
git status --short
git commit -m "Initial OurDeskPet prototype through M4"
```

Add a GitHub remote after creating the repository on GitHub:

```powershell
git remote add origin <repo-url>
git branch -M main
git push -u origin main
```

Current note:

- GitHub CLI is not installed on this machine, so remote creation/push needs either a repository URL or GitHub CLI setup later.

## Notes

- Do not commit `.env`.
- Do not commit build caches.
- Do not commit API keys or provider credentials.
- If publishing publicly, asset rights need a separate review.
