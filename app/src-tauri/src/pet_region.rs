use serde::Deserialize;

#[derive(Deserialize)]
pub struct PetRect { x: f64, y: f64, width: f64, height: f64 }

fn bounds(r: &PetRect, scale: f64) -> Result<[i32; 4], String> {
    if ![r.x,r.y,r.width,r.height,scale].iter().all(|v| v.is_finite())
        || r.width <= 0.0 || r.height <= 0.0 || scale <= 0.0
        || [r.x,r.y,r.width,r.height].iter().any(|v| v.abs() > 10000.0) || scale > 10.0 {
        return Err("Invalid pet region".into());
    }
    Ok([(r.x*scale).floor() as i32,(r.y*scale).floor() as i32,
        ((r.x+r.width)*scale).ceil() as i32,((r.y+r.height)*scale).ceil() as i32])
}

/// Clip the borderless native window, so hidden popup space cannot intercept clicks.
#[tauri::command]
pub fn set_pet_region(window: tauri::WebviewWindow, rects: Vec<PetRect>) -> Result<(), String> {
    if window.label() != "main" || rects.is_empty() || rects.len() > 2 {
        return Err("Only the pet and its visible panel may define this region".into());
    }
    let scale=window.scale_factor().map_err(|e|e.to_string())?;
    let areas=rects.iter().map(|r|bounds(r,scale)).collect::<Result<Vec<_>,_>>()?;
    #[cfg(target_os="windows")]
    {
        use std::ffi::c_void;
        #[link(name="gdi32")]
        extern "system" {
            fn CreateRectRgn(l:i32,t:i32,r:i32,b:i32)->*mut c_void;
            fn CombineRgn(dest:*mut c_void,a:*mut c_void,b:*mut c_void,mode:i32)->i32;
            fn DeleteObject(object:*mut c_void)->i32;
        }
        #[link(name="user32")]
        extern "system" { fn SetWindowRgn(hwnd:*mut c_void,region:*mut c_void,redraw:i32)->i32; }
        let hwnd=window.hwnd().map_err(|e|e.to_string())?;
        // SAFETY: sync command uses a live HWND; region handles are checked and owned
        // locally until SetWindowRgn succeeds, which transfers ownership to Windows.
        unsafe {
            let region=CreateRectRgn(0,0,0,0);
            if region.is_null(){return Err("Cannot allocate pet region".into());}
            for [l,t,r,b] in areas {
                let part=CreateRectRgn(l,t,r,b);
                if part.is_null(){DeleteObject(region);return Err("Cannot allocate pet region".into());}
                let result=CombineRgn(region,region,part,2); // RGN_OR
                DeleteObject(part);
                if result==0 {DeleteObject(region);return Err("Cannot combine pet region".into());}
            }
            if SetWindowRgn(hwnd.0 as *mut c_void,region,1)==0 {
                DeleteObject(region);return Err("Cannot apply pet region".into());
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn dpi_rounds_outward_and_keeps_pet_position() {
        let pet=PetRect{x:50.0,y:248.0,width:180.0,height:162.0};
        assert_eq!(bounds(&pet,1.5).unwrap(),[75,372,345,615]);
        let fractional=PetRect{x:1.1,y:2.1,width:10.2,height:10.2};
        assert_eq!(bounds(&fractional,1.25).unwrap(),[1,2,15,16]);
    }
    #[test] fn rejects_invalid_regions() {
        assert!(bounds(&PetRect{x:f64::NAN,y:0.0,width:1.0,height:1.0},1.0).is_err());
        assert!(bounds(&PetRect{x:0.0,y:0.0,width:0.0,height:1.0},1.0).is_err());
    }
}
