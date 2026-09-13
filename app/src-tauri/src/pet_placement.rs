use serde::Serialize;
use tauri::Manager;

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Rect {
    x: f64,
    y: f64,
    w: f64,
    h: f64,
}
impl Rect {
    fn right(self) -> f64 {
        self.x + self.w
    }
    fn bottom(self) -> f64 {
        self.y + self.h
    }
    fn overlap(self, other: Self) -> f64 {
        (self.right().min(other.right()) - self.x.max(other.x)).max(0.)
            * (self.bottom().min(other.bottom()) - self.y.max(other.y)).max(0.)
    }
}
#[derive(Debug, Serialize)]
pub struct Placement {
    x: i32,
    y: i32,
    side: &'static str,
    overlaps: bool,
    work: Rect,
    panel: Rect,
    pet: Rect,
}

fn choose(
    work: Rect,
    panel: Rect,
    obstacles: &[Rect],
    width: f64,
    height: f64,
    scale: f64,
) -> Placement {
    // Reserve the full horizontal extent of the popup, but only the visible pet's
    // vertical footprint. The board is collapsed before opening another window.
    let visible_w = 196. * scale;
    let visible_h = 162. * scale;
    let left = (width - visible_w) / 2.;
    let top = height - visible_h;
    let gap = 16. * scale;
    let low = panel.bottom() - height - gap;
    let right = panel.right() + gap - left;
    let left_side = panel.x - gap - visible_w - left;
    let align_right = panel.right() - visible_w - left;
    let candidates = [
        (right, low, "right"),
        (left_side, low, "left"),
        (align_right, panel.bottom() + gap - top, "below"),
        (align_right, panel.y - gap - height, "above"),
        (
            work.right() - width,
            work.bottom() - height,
            "screen-right-bottom",
        ),
        (work.x, work.bottom() - height, "screen-left-bottom"),
        (work.right() - width, work.y, "screen-right-top"),
        (work.x, work.y, "screen-left-top"),
    ];
    let mut best = None;
    for (x, y, side) in candidates {
        let x = x.clamp(work.x, (work.right() - width).max(work.x)).round();
        let y = y
            .clamp(work.y, (work.bottom() - height).max(work.y))
            .round();
        let pet = Rect {
            x: x + left,
            y: y + top,
            w: visible_w,
            h: visible_h,
        };
        let cost: f64 = obstacles.iter().map(|r| pet.overlap(*r)).sum();
        if best.as_ref().is_none_or(|(score, _)| cost < *score) {
            best = Some((
                cost,
                Placement {
                    x: x as i32,
                    y: y as i32,
                    side,
                    overlaps: cost > 0.,
                    work,
                    panel,
                    pet,
                },
            ));
        }
        if cost == 0. {
            break;
        }
    }
    best.unwrap().1
}

fn bounds(window: &tauri::WebviewWindow) -> Result<Rect, String> {
    let p = window.outer_position().map_err(|e| e.to_string())?;
    let s = window.outer_size().map_err(|e| e.to_string())?;
    Ok(Rect {
        x: p.x as f64,
        y: p.y as f64,
        w: s.width as f64,
        h: s.height as f64,
    })
}

// Match the collapsed pet button, not the transparent 280 x 410 host window.
// Use its own monitor scale: an unobstructed pet on another monitor stays there.
fn visible_pet(host: Rect, scale: f64) -> Rect {
    Rect { x: host.x + (host.w - 180. * scale) / 2.,
        y: host.bottom() - 162. * scale, w: 180. * scale, h: 162. * scale }
}

fn needs_parking(host: Rect, scale: f64, obstacles: &[Rect]) -> bool {
    let pet = visible_pet(host, scale);
    obstacles.iter().any(|obstacle| pet.overlap(*obstacle) > 0.)
}

#[tauri::command]
pub async fn park_pet_beside_window(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    target_label: String,
) -> Result<Placement, String> {
    if window.label() != "main" || !matches!(target_label.as_str(), "dialogue" | "settings") {
        return Err("Only the pet may park beside dialogue or settings".into());
    }
    let target = app
        .get_webview_window(&target_label)
        .ok_or("Target window unavailable")?;
    let panel = bounds(&target)?;
    let monitor = target
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("Monitor unavailable")?;
    let a = monitor.work_area();
    let work = Rect {
        x: a.position.x as f64,
        y: a.position.y as f64,
        w: a.size.width as f64,
        h: a.size.height as f64,
    };
    let scale = monitor.scale_factor();
    let old_scale = window.scale_factor().map_err(|e| e.to_string())?;
    let old_size = window.outer_size().map_err(|e| e.to_string())?;
    let width = old_size.width as f64 / old_scale * scale;
    let height = old_size.height as f64 / old_scale * scale;
    let mut obstacles = vec![panel];
    for label in ["dialogue", "settings"] {
        if label == target_label {
            continue;
        }
        if let Some(other) = app.get_webview_window(label) {
            if other.is_visible().unwrap_or(false) && !other.is_minimized().unwrap_or(true) {
                if let Ok(rect) = bounds(&other) {
                    obstacles.push(rect);
                }
            }
        }
    }
    let current = bounds(&window)?;
    if !needs_parking(current, old_scale, &obstacles) {
        return Ok(Placement { x: current.x as i32, y: current.y as i32,
            side: "unchanged", overlaps: false, work, panel,
            pet: visible_pet(current, old_scale) });
    }
    let result = choose(work, panel, &obstacles, width, height, scale);
    window
        .set_position(tauri::PhysicalPosition::new(result.x, result.y))
        .map_err(|e| e.to_string())?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_visible_pet_overlap_triggers_parking() {
        let host = Rect { x: 100., y: 100., w: 280., h: 410. };
        let empty_top = Rect { x: 100., y: 100., w: 280., h: 240. };
        assert!(!needs_parking(host, 1., &[empty_top]));
        let touching = Rect { x: 330., y: 350., w: 100., h: 100. };
        assert!(!needs_parking(host, 1., &[touching]));
        let overlap = Rect { x: 329., ..touching };
        assert!(needs_parking(host, 1., &[empty_top, overlap]));
        let other_monitor = Rect { x: -1900., y: 100., w: 900., h: 800. };
        assert!(!needs_parking(host, 1., &[other_monitor]));
    }
    #[test]
    fn overlap_uses_current_monitor_dpi() {
        let host = Rect { x: -2000., y: -200., w: 420., h: 615. };
        let pet = visible_pet(host, 1.5);
        assert_eq!(pet.w, 270.);
        assert_eq!(pet.h, 243.);
        assert!(needs_parking(host, 1.5, &[Rect { x: pet.x, y: pet.y, w: 1., h: 1. }]));
    }
    #[test]
    fn right_lower_on_actual_desktop() {
        let work = Rect {
            x: 0.,
            y: 0.,
            w: 1920.,
            h: 1032.,
        };
        for panel in [
            Rect {
                x: 500.,
                y: 150.,
                w: 920.,
                h: 719.,
            },
            Rect {
                x: 480.,
                y: 112.,
                w: 960.,
                h: 808.,
            },
        ] {
            let p = choose(work, panel, &[panel], 280., 410., 1.);
            assert_eq!(p.side, "right");
            assert!(!p.overlaps);
            assert!(p.pet.x >= panel.right() + 15.);
            assert!((p.pet.bottom() - (panel.bottom() - 16.)).abs() < 1.);
        }
    }
    #[test]
    fn near_right_edge_uses_left() {
        let work = Rect {
            x: 0.,
            y: 0.,
            w: 1920.,
            h: 1032.,
        };
        let panel = Rect {
            x: 950.,
            y: 150.,
            w: 950.,
            h: 719.,
        };
        let p = choose(work, panel, &[panel], 280., 410., 1.);
        assert_eq!(p.side, "left");
        assert!(!p.overlaps);
    }
    #[test]
    fn negative_monitor_and_scaled_pet_stay_visible() {
        let work = Rect {
            x: -2560.,
            y: -300.,
            w: 2560.,
            h: 1400.,
        };
        let panel = Rect {
            x: -2100.,
            y: -100.,
            w: 1380.,
            h: 1050.,
        };
        let p = choose(work, panel, &[panel], 420., 615., 1.5);
        assert!(!p.overlaps);
        assert!(p.x as f64 >= work.x);
        assert!(p.y as f64 >= work.y);
        assert!(p.x as f64 + 420. <= work.right());
        assert!(p.y as f64 + 615. <= work.bottom());
    }
    #[test]
    fn avoids_other_open_window() {
        let work = Rect {
            x: 0.,
            y: 0.,
            w: 1920.,
            h: 1032.,
        };
        let panel = Rect {
            x: 500.,
            y: 150.,
            w: 920.,
            h: 719.,
        };
        let other = Rect {
            x: 1430.,
            y: 200.,
            w: 480.,
            h: 800.,
        };
        let p = choose(work, panel, &[panel, other], 280., 410., 1.);
        assert_eq!(p.side, "left");
        assert!(!p.overlaps);
    }
    #[test]
    fn full_screen_cannot_avoid_but_remains_on_screen() {
        let work = Rect {
            x: 0.,
            y: 0.,
            w: 1366.,
            h: 728.,
        };
        let p = choose(work, work, &[work], 280., 410., 1.);
        assert!(p.overlaps);
        assert!(p.x >= 0 && p.y >= 0);
        assert!(p.x as f64 + 280. <= work.right());
        assert!(p.y as f64 + 410. <= work.bottom());
    }
}
