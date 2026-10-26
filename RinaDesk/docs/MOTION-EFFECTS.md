# Pet motion effects

## Drag trail (2026-10-21)

The drag overlay is independent from teleport visibility and placement. Native `onMoved` events supply physical displacement; conversion uses the window scale factor. DPI changes clear old particles. Browser preview uses pointer screen coordinates instead. The existing drag/release controller is unchanged; Windows drawing-region expansion during dragging is described below.

- Emit only for actual displacement, not while holding still.
- Switchable cyan/lavender and forest-green palettes, independent of character clothing.
- Sharp 4/5/7px fragments, no blur, up to 84 active particles. The 2026-10-22 visibility pass modestly increases width, lifetime and emission while keeping the trail under the lower body. Teleport's exact cyan/lavender fills retain a darker same-hue rim and 95% opacity for the first quarter of each particle's life.
- Existing particles compensate for window displacement to form a short trailing wake.
- Lower-body revision: seed within y=160..184 of the 240x200 overlay, use a narrow 18px band, bias behind normalized travel direction and distribute along the last displacement. Extra drift is small; old particles carry most of the tail through position compensation. Left/right and spawn-height regression assertions cover this contract.
- Release after motion creates a small upward/outward foot-level splash. It is not a second teleport.
- Teleport, hidden-document state, unmount and reduced-motion preference stop/clear the effect.
- Very large displacement is treated as a layout jump and clears the trail.
- Rendering is bounded to the pet overlay; this does not create desktop-wide trails or new click-blocking windows.

`motionParticles.ts` is a presentation-only simulation for manual dragging. It does not own window placement or emit while the pet is stationary.

## Art direction

The user selected the second/coarser pixel A.L.A.N concept on 2026-10-21. It is an optional built-in pack, not a forced selection. The standing image serves idle, drag and talk. Sleep now uses the approved isolated fox mask. Other generated stage concepts are not candidates.

Sleep has priority over drag: pointer movement cannot start native dragging while asleep, and the art resolver refuses to replace a sleep asset with a drag asset as a second line of defence. Wake with the context menu before repositioning the pet.

Sleep entry/wake uses a bounded 820 ms strip-displacement transition on the pixel pack, with 18 small 3/5/7px fragments and cleanup at 860 ms. It swaps the standing image and fox mask without owning controller state, window position, dragging or teleport. Reduced-motion preference bypasses it. Further enlargement of the particle treatment remains deferred until requested.

### A.L.A.N speech and drag accessories (2026-10-23)

The approved pixel pack now adds two code-authored overlays without replacing or redrawing the standing character. While a model response is streaming, the visor uses a fixed irregular magenta pixel outline and cycles through dim, bright, segmented-scan and short accent frames. It does not invent mouth shapes, blur the whole helmet or sample audio. Reduced-motion mode keeps one dim frame instead of flashing.

Dragging summons two theatre-inspired cat-ear drones outside the character silhouette. Their green eyes remain at low brightness during motion so the units stay identifiable, with a brief brighter lift-off and release response. The drones are deliberately farther from the body than the first preview and use small independent green pixel wakes. The overlays have no pointer handlers. Releasing the pet plays a short overshoot/fade; sleep and teleport continue to take priority.

### Native drag envelope (2026-10-24)

`SetWindowRgn` clips pixels as well as mouse input on Windows. The former 180x162 character-button region cut off drones even when their DOM bounds were inside the transparent window. The native pet canvas settles at 420 logical pixels wide and stays stable across mouse-up; the visible layout remains a centered 280-pixel shell. While dragging, the native drawing/input region now uses the complete 420x230 lower canvas instead of a calculated tight envelope. It stays expanded for 360 ms after release to cover the 290 ms drone exit, then returns to the original 180x162 character region (plus the board only if open). The temporary transparent margin is deliberately accepted during drag so SVG animation, filter shadows, DPI rounding and WebView rendering cannot clip the drones. Avoiding a second HWND resize prevents one-frame WebView reflow jitter after a drag.

Drone escort width is 340; 50px drones sit 18px from each side, with 2px hover and 1.04 release scaling. Each drone is 10px nearer the character than the earlier 360px formation. The corresponding DOM viewport width accompanies every region request, so coordinates remain correct while the initial 280-pixel bootstrap frame settles into the stable canvas. Windows performs that one centered `SetWindowPos` transition and preserves the pet centre to the nearest physical pixel at 100/125/150/200% DPI. Art-state and advanced-effect previews share a 380px stage; art preview cards reserve at least 276px horizontally so the full escort remains visible instead of being compressed against the card edges.

Normal app exit shares only the disappearance half of the quantum teleport effect. Conversation storage flush and the 600 ms dissolve run together, then the native process exits. Main-window close requests use the same path; crashes, force-kill and OS teardown remain immediate fallbacks.

## Advanced effects

Cards use two compact columns instead of a 240px minimum that forced stacking at the actual board width. The preview scales as a whole, including its particle canvas, with an additional small-container rule.

## Review-only work (2026-10-21)

- Rest: pixel strip-displacement transition to the isolated fox mask is deployed only for A.L.A.N. No loop or whole-screen flash; explicit sleep/wake controls and reduced-motion bypass.
- Paper fidelity: user rejected generated paper variants. The hand-authored SVG traced against the final classroom board in season 1 episode 6 is stored only as `assets/library/paper-episode06.svg`, with left binding, sparse unfilled hair contours, thick eyes and thin mouth. No stars or filled bangs. Only hand-occluded paper corners are reconstructed. Source: https://www.hidamarie.net/entry/2020/11/09/180023 . It is not in `app/public`, is not packaged, and does not replace either uniform sleep state until its animation is approved.
- Settings labels: `联网搜索` and `对话保存位置`.

Art settings has a third disclosure, Advanced Effects, with two unnamed animated radio cards. Accessible labels distinguish cyan/lavender and forest green. Both use the actual drag, landing and quantum teleport renderers. Selection is stored in `rinadesk.effect-preset`, propagated across windows and reconciled on focus; invalid values fall back to cyan/lavender and failed writes show an error. Art selection and effect selection are independent.

Previews stop when collapsed, outside the visible area, backgrounded or reduced-motion is enabled. The legacy scanline implementation remains in source, but is not an exposed selection.

## Checks

`npm test` includes the deterministic particle simulation regression. It checks stationary suppression, opposite-direction velocity, window-motion compensation, particle cap, invalid/large movement rejection, landing spread and expiration. TypeScript/build checks validate native event API integration. Native Windows dragging remains a separate visual acceptance check (slow/fast drag, stationary hold, release, edge/DPI crossing and minimize/restore).
