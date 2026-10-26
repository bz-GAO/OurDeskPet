# Subtitle fonts

Use static fonts to avoid variable fonts being selected as Thin by some libass
renderers. Noto Sans CJK Medium remains the default. GenSen Rounded JP Medium is
the optional rounded subtitle face. Subtitle fill stays white; the selected
character colour is applied to the outline.

Official upstream (SIL Open Font License, included in LICENSE):
- https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Medium.otf
- https://github.com/notofonts/noto-cjk/blob/main/Sans/OTF/Japanese/NotoSansCJKjp-Medium.otf
- https://github.com/ButTaiwan/gensen-font/blob/master/otf/JP/GenSenRounded2JP-M.otf

Place these files in this directory. The full pipeline embeds the fonts used by
the generated ASS in MKV
and hashes them for cache invalidation. No system font installation is required
for a player that supports ASS and MKV font attachments (e.g. mpv).
Standalone ASS requires these fonts installed or supplied to the renderer;
FFmpeg previews should use the `ass` filter's `fontsdir` option. SRT cannot
preserve this styling. Disabling ASS styling in a player overrides our design.
GenSen Rounded is distributed under SIL Open Font License 1.1; its license is
kept in `GenSenRounded-OFL.txt`.
