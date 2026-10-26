//! App-owned character art. The Rina board and interaction geometry stay built in.
use super::*;
use base64::{engine::general_purpose::STANDARD, Engine};
use chrono::Utc;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
};

const IMAGE_LIMIT: u64 = 5 * 1024 * 1024;
const MANIFEST_LIMIT: u64 = 32 * 1024;
const SLOTS: [&str; 4] = ["idle", "drag", "talk", "sleep"];
static SAVE_LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct Images {
    idle: String,
    drag: String,
    talk: String,
    sleep: String,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SaveRequest {
    id: Option<String>,
    label: String,
    images: Images,
}
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArtPack {
    id: String,
    label: String,
    code: String,
    images: Images,
}
#[derive(Serialize, Deserialize)]
struct Manifest {
    schema: u32,
    id: String,
    label: String,
    files: BTreeMap<String, String>,
}

fn root() -> Result<PathBuf, String> {
    Ok(billing::home("RinaDesk")?.join("art-packs"))
}
fn valid_id(value: &str) -> bool {
    value.starts_with("rina-custom-")
        && value.len() <= 80
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}
fn clean_label(value: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() || value.chars().count() > 40 || value.chars().any(char::is_control) {
        return Err("方案名称需为 1–40 个字符".into());
    }
    Ok(value.into())
}
fn decode(value: &str) -> Result<(&'static str, Vec<u8>), String> {
    let (prefix, encoded) = value.split_once(',').ok_or("人物图片格式无效")?;
    let (mime, ext) = match prefix {
        "data:image/png;base64" => ("image/png", "png"),
        "data:image/jpeg;base64" => ("image/jpeg", "jpg"),
        "data:image/webp;base64" => ("image/webp", "webp"),
        _ => return Err("仅支持 PNG、JPEG 或 WebP 人物图片".into()),
    };
    if encoded.len() as u64 > IMAGE_LIMIT * 4 / 3 + 8 {
        return Err("每张人物图片需小于 5 MB".into());
    }
    let bytes = STANDARD.decode(encoded).map_err(|_| "人物图片格式无效")?;
    if bytes.is_empty() || bytes.len() as u64 > IMAGE_LIMIT {
        return Err("每张人物图片需小于 5 MB".into());
    }
    let magic = match mime {
        "image/png" => bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
        "image/webp" => bytes.len() >= 12 && &bytes[..4] == b"RIFF" && &bytes[8..12] == b"WEBP",
        _ => false,
    };
    if !magic {
        return Err("人物图片内容与格式不一致".into());
    }
    let dimensions = xcap::image::ImageReader::new(Cursor::new(&bytes))
        .with_guessed_format()
        .map_err(|_| "人物图片无效")?
        .into_dimensions()
        .map_err(|_| "人物图片无效")?;
    if dimensions.0 == 0 || dimensions.1 == 0 || dimensions.0 > 4096 || dimensions.1 > 4096 {
        return Err("人物图片尺寸需在 4096 × 4096 以内".into());
    }
    Ok((ext, bytes))
}
fn atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path.parent().ok_or("人物方案目录无效")?;
    fs::create_dir_all(parent).map_err(|_| "无法创建人物方案目录")?;
    billing::no_redirect(parent)?;
    let temporary = parent.join(format!(
        ".art-{}-{}.tmp",
        std::process::id(),
        Utc::now().timestamp_nanos_opt().unwrap_or(0)
    ));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|_| "无法保存人物方案")?;
    if file.write_all(bytes).and_then(|_| file.sync_all()).is_err() {
        drop(file);
        let _ = fs::remove_file(&temporary);
        return Err("无法保存人物方案".into());
    }
    drop(file);
    billing::no_redirect(path)?;
    if !path.exists() {
        return fs::rename(&temporary, path).map_err(|_| {
            let _ = fs::remove_file(&temporary);
            "无法保存人物方案".into()
        });
    }
    let target = fs::symlink_metadata(path).map_err(|_| {
        let _ = fs::remove_file(&temporary);
        "无法检查人物方案原件".to_string()
    })?;
    if !target.file_type().is_file() || target.file_type().is_symlink() {
        let _ = fs::remove_file(&temporary);
        return Err("无法替换人物方案，原方案已保留".into());
    }
    let backup = parent.join(format!(
        ".art-{}-{}.bak",
        std::process::id(),
        Utc::now().timestamp_nanos_opt().unwrap_or(0)
    ));
    fs::rename(path, &backup).map_err(|_| {
        let _ = fs::remove_file(&temporary);
        "无法替换人物方案，原方案已保留".to_string()
    })?;
    match fs::rename(&temporary, path) {
        Ok(()) => {
            let _ = fs::remove_file(backup);
            Ok(())
        }
        Err(_) => {
            let _ = fs::rename(&backup, path);
            let _ = fs::remove_file(&temporary);
            Err("无法替换人物方案，原方案已保留".into())
        }
    }
}
fn data_url(path: &Path) -> Result<String, String> {
    billing::no_redirect(path)?;
    let file = fs::File::open(path).map_err(|_| "人物方案图片缺失")?;
    let metadata = file.metadata().map_err(|_| "人物方案图片不可用")?;
    if !metadata.is_file() || metadata.len() > IMAGE_LIMIT {
        return Err("人物方案图片不可用".into());
    }
    let mut bytes = Vec::new();
    file.take(IMAGE_LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "人物方案图片不可用")?;
    let mime = match path.extension().and_then(|v| v.to_str()) {
        Some("png") => "image/png",
        Some("jpg") => "image/jpeg",
        Some("webp") => "image/webp",
        _ => return Err("人物方案图片格式无效".into()),
    };
    let value = format!("data:{mime};base64,{}", STANDARD.encode(bytes));
    decode(&value)?;
    Ok(value)
}
fn read_manifest(path: &Path) -> Result<Manifest, String> {
    billing::no_redirect(path)?;
    let file = fs::File::open(path).map_err(|_| "人物方案清单不可用")?;
    if file.metadata().map_err(|_| "人物方案清单不可用")?.len() > MANIFEST_LIMIT {
        return Err("人物方案清单过大".into());
    }
    let mut bytes = Vec::new();
    file.take(MANIFEST_LIMIT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "人物方案清单不可用")?;
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| "人物方案清单损坏")?;
    if manifest.schema != 1
        || !valid_id(&manifest.id)
        || clean_label(&manifest.label).is_err()
        || path
            .parent()
            .and_then(Path::file_name)
            .and_then(|v| v.to_str())
            != Some(manifest.id.as_str())
    {
        return Err("人物方案清单无效".into());
    }
    Ok(manifest)
}
fn payload(folder: &Path, manifest: Manifest) -> Result<ArtPack, String> {
    let mut values = BTreeMap::new();
    for slot in SLOTS {
        let name = manifest.files.get(slot).ok_or("人物方案清单不完整")?;
        if name.contains(['/', '\\', ':'])
            || name.starts_with('.')
            || Path::new(name).file_name().and_then(|v| v.to_str()) != Some(name.as_str())
        {
            return Err("人物方案图片路径无效".into());
        }
        values.insert(slot, data_url(&folder.join(name))?);
    }
    Ok(ArtPack {
        id: manifest.id.clone(),
        label: manifest.label,
        code: format!("CUSTOM-{}", manifest.id.rsplit('-').next().unwrap_or("ART")),
        images: Images {
            idle: values.remove("idle").unwrap(),
            drag: values.remove("drag").unwrap(),
            talk: values.remove("talk").unwrap(),
            sleep: values.remove("sleep").unwrap(),
        },
    })
}
fn folder_for(root: &Path, id: &str) -> Result<PathBuf, String> {
    if !valid_id(id) {
        return Err("人物方案编号无效".into());
    }
    billing::no_redirect(root)?;
    let folder = root.join(id);
    billing::no_redirect(&folder)?;
    Ok(folder)
}
fn rename_at(root: &Path, id: &str, label: &str) -> Result<ArtPack, String> {
    let folder = folder_for(root, id)?;
    let mut manifest = read_manifest(&folder.join("manifest.json"))?;
    manifest.label = clean_label(label)?;
    let bytes = serde_json::to_vec_pretty(&manifest).map_err(|_| "无法保存人物方案")?;
    atomic(&folder.join("manifest.json"), &bytes)?;
    payload(&folder, manifest)
}
fn generated_asset(name: &str) -> bool {
    if name == "manifest.json" {
        return true;
    }
    let Some((stem, ext)) = name.rsplit_once('.') else {
        return false;
    };
    if !matches!(ext, "png" | "jpg" | "webp") {
        return false;
    }
    let Some((slot, digest)) = stem.split_once('-') else {
        return false;
    };
    SLOTS.contains(&slot) && digest.len() == 64 && digest.bytes().all(|b| b.is_ascii_hexdigit())
}
fn delete_at(root: &Path, id: &str) -> Result<(), String> {
    let folder = folder_for(root, id)?;
    read_manifest(&folder.join("manifest.json"))?;
    let entries = fs::read_dir(&folder)
        .map_err(|_| "无法读取人物方案")?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "无法读取人物方案")?;
    for entry in &entries {
        let file_type = entry.file_type().map_err(|_| "人物方案目录不可用")?;
        let name = entry.file_name();
        let Some(name) = name.to_str() else {
            return Err("人物方案目录包含未知文件，未删除".into());
        };
        if !file_type.is_file() || file_type.is_symlink() || !generated_asset(name) {
            return Err("人物方案目录包含未知文件，未删除".into());
        }
        billing::no_redirect(&entry.path())?;
    }
    for entry in entries {
        fs::remove_file(entry.path()).map_err(|_| "无法删除人物方案")?;
    }
    fs::remove_dir(folder).map_err(|_| "无法删除人物方案".into())
}

#[tauri::command]
pub fn art_custom_list() -> Result<Vec<ArtPack>, String> {
    let root = root()?;
    billing::no_redirect(&root)?;
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut entries = fs::read_dir(&root)
        .map_err(|_| "无法读取人物方案")?
        .filter_map(Result::ok)
        .collect::<Vec<_>>();
    entries.sort_by_key(|entry| entry.file_name());
    let mut packs = Vec::new();
    for entry in entries.into_iter().take(20) {
        if !entry.file_type().map(|v| v.is_dir()).unwrap_or(false) {
            continue;
        }
        let folder = entry.path();
        if let Ok(manifest) = read_manifest(&folder.join("manifest.json")) {
            if let Ok(pack) = payload(&folder, manifest) {
                packs.push(pack);
            }
        }
    }
    Ok(packs)
}

#[tauri::command]
pub fn art_custom_save(window: tauri::Window, request: SaveRequest) -> Result<ArtPack, String> {
    if window.label() != "settings" {
        return Err("请在人物与美术设置中保存方案".into());
    }
    let _lock = SAVE_LOCK.lock().map_err(|_| "人物方案正在保存")?;
    let label = clean_label(&request.label)?;
    let decoded = [
        ("idle", decode(&request.images.idle)?),
        ("drag", decode(&request.images.drag)?),
        ("talk", decode(&request.images.talk)?),
        ("sleep", decode(&request.images.sleep)?),
    ];
    let updating = request.id.is_some();
    let id = match request.id {
        Some(id) if valid_id(&id) => id,
        Some(_) => return Err("人物方案编号无效".into()),
        None => {
            let digest = Sha256::digest(&decoded[0].1 .1);
            format!(
                "rina-custom-{}-{:02x}{:02x}{:02x}{:02x}",
                Utc::now().timestamp_millis(),
                digest[0],
                digest[1],
                digest[2],
                digest[3]
            )
        }
    };
    let root = root()?;
    billing::no_redirect(&root)?;
    fs::create_dir_all(&root).map_err(|_| "无法创建人物方案目录")?;
    if !updating && fs::read_dir(&root).map_err(|_| "无法读取人物方案")?.count() >= 20 {
        return Err("最多保存 20 个自定义方案".into());
    }
    let folder = root.join(&id);
    billing::no_redirect(&folder)?;
    if updating {
        read_manifest(&folder.join("manifest.json"))?;
    }
    fs::create_dir_all(&folder).map_err(|_| "无法创建人物方案目录")?;
    let mut files = BTreeMap::new();
    for (slot, (ext, bytes)) in decoded {
        let digest = Sha256::digest(&bytes);
        let name = format!("{slot}-{digest:x}.{ext}");
        let path = folder.join(&name);
        if !path.exists() {
            atomic(&path, &bytes)?;
        }
        files.insert(slot.into(), name);
    }
    let manifest = Manifest {
        schema: 1,
        id: id.clone(),
        label,
        files,
    };
    let bytes = serde_json::to_vec_pretty(&manifest).map_err(|_| "无法保存人物方案")?;
    atomic(&folder.join("manifest.json"), &bytes)?;
    let result = payload(&folder, manifest)?;
    let _ = window.app_handle().emit("deskpet-art-packs-change", ());
    Ok(result)
}

#[tauri::command]
pub fn art_custom_rename(
    window: tauri::Window,
    id: String,
    label: String,
) -> Result<ArtPack, String> {
    if window.label() != "settings" {
        return Err("请在人物与美术设置中重命名方案".into());
    }
    let _lock = SAVE_LOCK.lock().map_err(|_| "人物方案正在保存")?;
    let result = rename_at(&root()?, &id, &label)?;
    let _ = window.app_handle().emit("deskpet-art-packs-change", ());
    Ok(result)
}

#[tauri::command]
pub fn art_custom_delete(window: tauri::Window, id: String) -> Result<(), String> {
    if window.label() != "settings" {
        return Err("请在人物与美术设置中删除方案".into());
    }
    let _lock = SAVE_LOCK.lock().map_err(|_| "人物方案正在保存")?;
    delete_at(&root()?, &id)?;
    let _ = window.app_handle().emit("deskpet-art-packs-change", ());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_png_and_rejects_mismatched_data() {
        let mut png = Cursor::new(Vec::new());
        DynamicImage::new_rgba8(2, 2)
            .write_to(&mut png, ImageFormat::Png)
            .unwrap();
        let value = format!(
            "data:image/png;base64,{}",
            STANDARD.encode(png.into_inner())
        );
        assert!(decode(&value).is_ok());
        let wrong = format!("data:image/png;base64,{}", STANDARD.encode(b"not png"));
        assert!(decode(&wrong).is_err());
    }
    #[test]
    fn validates_custom_ids_and_labels() {
        assert!(valid_id("rina-custom-1-abcd"));
        assert!(!valid_id("../custom"));
        assert!(clean_label("  我的方案  ").is_ok());
        assert!(clean_label("").is_err());
    }
    #[test]
    fn manifest_replace_preserves_original_when_commit_fails() {
        let folder = env::temp_dir().join(format!(
            "art-atomic-{}-{}",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap()
        ));
        fs::create_dir_all(&folder).unwrap();
        let path = folder.join("manifest.json");
        atomic(&path, b"first").unwrap();
        atomic(&path, b"second").unwrap();
        assert_eq!(fs::read(&path).unwrap(), b"second");
        let directory = folder.join("occupied");
        fs::create_dir(&directory).unwrap();
        assert!(atomic(&directory, b"replacement").is_err());
        assert!(directory.is_dir());
        assert_eq!(fs::read(&path).unwrap(), b"second");
        fs::remove_dir_all(folder).unwrap();
    }
    #[test]
    fn custom_pack_can_be_renamed_and_only_known_files_deleted() {
        let root = env::temp_dir().join(format!(
            "art-manage-{}-{}",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap()
        ));
        let id = "rina-custom-1-abcd";
        let folder = root.join(id);
        fs::create_dir_all(&folder).unwrap();
        let mut files = BTreeMap::new();
        let mut png = Cursor::new(Vec::new());
        DynamicImage::new_rgba8(2, 2)
            .write_to(&mut png, ImageFormat::Png)
            .unwrap();
        let bytes = png.into_inner();
        let digest = format!("{:x}", Sha256::digest(&bytes));
        for slot in SLOTS {
            let name = format!("{slot}-{digest}.png");
            fs::write(folder.join(&name), &bytes).unwrap();
            files.insert(slot.into(), name);
        }
        let manifest = Manifest {
            schema: 1,
            id: id.into(),
            label: "旧名称".into(),
            files,
        };
        fs::write(
            folder.join("manifest.json"),
            serde_json::to_vec(&manifest).unwrap(),
        )
        .unwrap();
        assert_eq!(rename_at(&root, id, "新名称").unwrap().label, "新名称");
        fs::write(folder.join("notes.txt"), b"keep").unwrap();
        assert!(delete_at(&root, id).is_err());
        assert!(folder.exists());
        fs::remove_file(folder.join("notes.txt")).unwrap();
        delete_at(&root, id).unwrap();
        assert!(!folder.exists());
        fs::remove_dir(root).unwrap();
    }
}
