fn main() {
    println!("cargo:rerun-if-env-changed=RINADESK_BUILD_TIME");
    println!("cargo:rerun-if-env-changed=RINADESK_SOURCE_REVISION");
    tauri_build::build()
}
