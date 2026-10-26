use serde::Deserialize;

#[derive(Deserialize)]
pub struct PetRect {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

fn bounds(r: &PetRect, scale: f64) -> Result<[i32; 4], String> {
    if ![r.x, r.y, r.width, r.height, scale]
        .iter()
        .all(|v| v.is_finite())
        || r.width <= 0.0
        || r.height <= 0.0
        || scale <= 0.0
        || [r.x, r.y, r.width, r.height]
            .iter()
            .any(|v| v.abs() > 10000.0)
        || scale > 10.0
    {
        return Err("Invalid pet region".into());
    }
    Ok([
        (r.x * scale).floor() as i32,
        (r.y * scale).floor() as i32,
        ((r.x + r.width) * scale).ceil() as i32,
        ((r.y + r.height) * scale).ceil() as i32,
    ])
}

fn layout_width(_drag_space: bool) -> f64 {
    // Keep one stable native canvas. SetWindowRgn still limits idle input to
    // the visible pet/board, while effects may use the wider drawing area.
    // Avoiding a second HWND resize after mouse-up removes WebView reflow jitter.
    420.0
}

fn rebase_rect(mut rect: PetRect, viewport_width: f64, target_width: f64) -> PetRect {
    // DOM coordinates can still describe the previous viewport while Windows
    // has already resized. Rebase from the measured viewport, not the HWND.
    rect.x += (target_width - viewport_width) / 2.0;
    rect
}

fn centered_origin(x: i32, old_width: u32, new_width: u32) -> i32 {
    (x as i64 + (old_width as i64 - new_width as i64) / 2).clamp(i32::MIN as i64, i32::MAX as i64)
        as i32
}

/// Clip the borderless native window, so hidden popup space cannot intercept clicks.
#[tauri::command]
pub fn set_pet_region(
    window: tauri::WebviewWindow,
    rects: Vec<PetRect>,
    drag_space: Option<bool>,
    viewport_width: Option<f64>,
) -> Result<(), String> {
    if window.label() != "main" || rects.is_empty() || rects.len() > 2 {
        return Err("Only the pet and its visible panel may define this region".into());
    }
    let scale = window.scale_factor().map_err(|e| e.to_string())?;
    let target_width = drag_space.map(layout_width);
    let measured_width = viewport_width.unwrap_or_else(|| target_width.unwrap_or(280.0));
    if !measured_width.is_finite() || !(100.0..=4000.0).contains(&measured_width) {
        return Err("Invalid pet viewport".into());
    }
    let areas = rects
        .into_iter()
        .map(|rect| {
            let rect = rebase_rect(rect, measured_width, target_width.unwrap_or(measured_width));
            bounds(&rect, scale)
        })
        .collect::<Result<Vec<_>, _>>()?;
    #[cfg(target_os = "windows")]
    {
        use std::ffi::c_void;
        #[link(name = "gdi32")]
        extern "system" {
            fn CreateRectRgn(l: i32, t: i32, r: i32, b: i32) -> *mut c_void;
            fn CombineRgn(dest: *mut c_void, a: *mut c_void, b: *mut c_void, mode: i32) -> i32;
            fn DeleteObject(object: *mut c_void) -> i32;
        }
        #[link(name = "user32")]
        extern "system" {
            fn SetWindowRgn(hwnd: *mut c_void, region: *mut c_void, redraw: i32) -> i32;
            fn SetWindowPos(
                hwnd: *mut c_void,
                insert_after: *mut c_void,
                x: i32,
                y: i32,
                width: i32,
                height: i32,
                flags: u32,
            ) -> i32;
        }
        let hwnd = window.hwnd().map_err(|e| e.to_string())?;
        if let Some(width) = target_width {
            if window.is_minimized().map_err(|e| e.to_string())? {
                return Ok(());
            }
            let size = window.outer_size().map_err(|e| e.to_string())?;
            let width = (width * scale).round() as u32;
            if size.width != width {
                let position = window.outer_position().map_err(|e| e.to_string())?;
                let x = centered_origin(position.x, size.width, width);
                // Resize and shift atomically: the character remains at the same
                // desktop coordinate, without focusing or reordering the window.
                if unsafe {
                    SetWindowPos(
                        hwnd.0 as *mut c_void,
                        std::ptr::null_mut(),
                        x,
                        position.y,
                        width as i32,
                        size.height as i32,
                        0x0004 | 0x0010,
                    )
                } == 0
                {
                    return Err("Cannot resize pet effect space".into());
                }
            }
        }
        // SAFETY: sync command uses a live HWND; region handles are checked and owned
        // locally until SetWindowRgn succeeds, which transfers ownership to Windows.
        unsafe {
            let region = CreateRectRgn(0, 0, 0, 0);
            if region.is_null() {
                return Err("Cannot allocate pet region".into());
            }
            for [l, t, r, b] in areas {
                let part = CreateRectRgn(l, t, r, b);
                if part.is_null() {
                    DeleteObject(region);
                    return Err("Cannot allocate pet region".into());
                }
                let result = CombineRgn(region, region, part, 2); // RGN_OR
                DeleteObject(part);
                if result == 0 {
                    DeleteObject(region);
                    return Err("Cannot combine pet region".into());
                }
            }
            if SetWindowRgn(hwnd.0 as *mut c_void, region, 1) == 0 {
                DeleteObject(region);
                return Err("Cannot apply pet region".into());
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn drag_space_preserves_anchor_and_rebases_stale_dom_at_each_dpi() {
        for scale in [1.0, 1.25, 1.5, 2.0] {
            let bootstrap = (280.0 * scale) as u32;
            let wide = (layout_width(true) * scale) as u32;
            let x = centered_origin(-1000, bootstrap, wide);
            // Integer HWND coordinates may place the preserved centre on either
            // side of a half physical pixel at fractional DPI.
            assert!((x * 2 + wide as i32 - (-2000 + bootstrap as i32)).abs() <= 1);
            assert_eq!(centered_origin(x, wide, wide), x);
            let from_old_dom = rebase_rect(
                PetRect {
                    x: -70.0,
                    y: 180.0,
                    width: 420.0,
                    height: 230.0,
                },
                280.0,
                420.0,
            );
            assert_eq!(
                bounds(&from_old_dom, scale).unwrap(),
                [
                    0,
                    (180.0 * scale).floor() as i32,
                    (420.0 * scale).ceil() as i32,
                    (410.0 * scale).ceil() as i32
                ]
            );
            let normal_from_bootstrap = rebase_rect(
                PetRect {
                    x: 50.0,
                    y: 248.0,
                    width: 180.0,
                    height: 162.0,
                },
                280.0,
                420.0,
            );
            assert_eq!(normal_from_bootstrap.x, 120.0);
            let normal_settled = rebase_rect(
                PetRect {
                    x: 120.0,
                    y: 248.0,
                    width: 180.0,
                    height: 162.0,
                },
                420.0,
                420.0,
            );
            assert_eq!(normal_settled.x, 120.0);
        }
    }
    #[test]
    fn dpi_rounds_outward_and_keeps_pet_position() {
        let pet = PetRect {
            x: 50.0,
            y: 248.0,
            width: 180.0,
            height: 162.0,
        };
        assert_eq!(bounds(&pet, 1.5).unwrap(), [75, 372, 345, 615]);
        let fractional = PetRect {
            x: 1.1,
            y: 2.1,
            width: 10.2,
            height: 10.2,
        };
        assert_eq!(bounds(&fractional, 1.25).unwrap(), [1, 2, 15, 16]);
    }
    #[test]
    fn rejects_invalid_regions() {
        assert!(bounds(
            &PetRect {
                x: f64::NAN,
                y: 0.0,
                width: 1.0,
                height: 1.0
            },
            1.0
        )
        .is_err());
        assert!(bounds(
            &PetRect {
                x: 0.0,
                y: 0.0,
                width: 0.0,
                height: 1.0
            },
            1.0
        )
        .is_err());
    }
}
