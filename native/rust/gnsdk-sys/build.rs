use std::env;
use std::path::PathBuf;

fn main() {
    let header = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap())
        .join("../../sdk/include/gnsdk/gnsdk.h");
    println!("cargo:rerun-if-changed={}", header.display());
    if let Ok(dir) = env::var("GNSDK_LIB_DIR") {
        println!("cargo:rustc-link-search=native={dir}");
        println!("cargo:rustc-link-lib=dylib=gnsdk");
    }
    let bindings = bindgen::Builder::default()
        .header(header.to_string_lossy())
        .allowlist_type("gnsdk_.*")
        .allowlist_function("gnsdk_.*")
        .allowlist_var("GNSDK_.*")
        .derive_default(true)
        .generate()
        .expect("bindgen could not parse frozen gnsdk.h");
    bindings.write_to_file(PathBuf::from(env::var("OUT_DIR").unwrap()).join("bindings.rs"))
        .expect("write gnsdk bindings");
}
