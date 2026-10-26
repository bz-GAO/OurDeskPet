# Electronic board v6

The electronic board now uses a wider, tapered silhouette. The long side walls, inner screen and side strips narrow together towards the bottom. Three existing star controls and the smile settings entry remain.

References: [multiple anime front views](https://note.com/val_diel/n/n7937d514fb5b), [Bandai animation-based reproduction](https://toy.bandai.co.jp/ja/topics/01_18392/), and the existing season-one episode-six reference. These informed a front-facing UI adaptation, not an assertion of exact official dimensions. The larger stars are deliberately retained for usability.

## Shared geometry

`app/src/components/boardGeometry.ts` defines the 160 48 1216 896 viewBox, screen boundary and three star centers/polygons. Both pet and settings use these coordinates. CSS uses the same 1216:896 aspect ratio. The popup stays 196 px wide; native hit regions are derived from its actual layout. Settings initially fits the artwork ratio and retains a narrower safe content rectangle clear of the tapered corners.

The default asset `electronic-faithful.svg` is now entirely vector, including the frame, stars, grid and pixel expression. There is no embedded raster or extracted alpha edge. Screen-only white overlays support settings, hover action previews and notification pulses. Star highlights use dedicated polygons rather than filtering a surrounding image rectangle. Smile hover draws the shared expression path directly.

## Vector edge design

V5 raster extraction left visible halos and interrupted contours, especially around the upper-right stars. V6 replaces the entire board with native SVG paths: tapered shell, side slots, stars, screen grid and pixel expression. There is no embedded bitmap and no alpha extraction mask. The viewBox, star centers and screen boundary remain unchanged, preserving layout and hit targets. Smile hover now draws the same expression path directly. The screen outline is painted over the grid to prevent grid intersections from interrupting the border.
