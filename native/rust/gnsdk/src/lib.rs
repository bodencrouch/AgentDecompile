//! Safe, thread-confined ownership wrapper over the frozen gnsdk C ABI.

use std::ffi::CString;
use std::marker::PhantomData;
use std::ptr::{self, NonNull};

pub use gnsdk_sys as sys;

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct Error(pub u32);
pub type Result<T> = std::result::Result<T, Error>;

fn check(status: u32) -> Result<()> {
    if status == sys::gnsdk_status_GNSDK_OK { Ok(()) } else { Err(Error(status)) }
}

fn output_status(status: u32) -> Result<()> {
    match status {
        sys::gnsdk_status_GNSDK_OK
        | sys::gnsdk_status_GNSDK_OK_WARNINGS
        | sys::gnsdk_status_GNSDK_PARTIAL_UNSUPPORTED => Ok(()),
        _ => Err(Error(status)),
    }
}

/// Process-level initialization. The upstream native runtime is deliberately
/// process-global and has no teardown; call once per process.
pub fn init(sleigh_home: &str) -> Result<()> {
    let path = CString::new(sleigh_home).map_err(|_| Error(sys::gnsdk_status_GNSDK_INVALID_ARGUMENT))?;
    let options = sys::gnsdk_init_options { struct_size: std::mem::size_of::<sys::gnsdk_init_options>() as u32, flags: 0, sleigh_home: path.as_ptr() };
    unsafe { check(sys::gnsdk_init(&options)) }
}

/// A raw-image session. `PhantomData<Rc<()>>` intentionally makes the handle
/// neither Send nor Sync: the native API permits only one calling thread.
pub struct Session {
    raw: NonNull<sys::gnsdk_session>,
    _not_send_sync: PhantomData<std::rc::Rc<()>>,
}

impl Session {
    pub fn new(language: &str) -> Result<Self> {
        let language = CString::new(language).map_err(|_| Error(sys::gnsdk_status_GNSDK_INVALID_ARGUMENT))?;
        let options = sys::gnsdk_session_options { struct_size: std::mem::size_of::<sys::gnsdk_session_options>() as u32, flags: 0, language_id: language.as_ptr() };
        let mut raw = ptr::null_mut();
        unsafe { check(sys::gnsdk_session_create(&options, &mut raw))?; }
        Ok(Self { raw: NonNull::new(raw).ok_or(Error(sys::gnsdk_status_GNSDK_ENGINE_FAILURE))?, _not_send_sync: PhantomData })
    }

    pub fn load_image(&mut self, bytes: &[u8], base: u64) -> Result<()> {
        if bytes.is_empty() { return Err(Error(sys::gnsdk_status_GNSDK_INVALID_ARGUMENT)); }
        let image = sys::gnsdk_image_desc { struct_size: std::mem::size_of::<sys::gnsdk_image_desc>() as u32, flags: 0, bytes: bytes.as_ptr(), len: bytes.len(), base, name: ptr::null() };
        unsafe { check(sys::gnsdk_session_load_image(self.raw.as_ptr(), &image)) }
    }

    pub fn decompile(&mut self, address: u64) -> Result<String> {
        let options = sys::gnsdk_decompile_options { struct_size: std::mem::size_of::<sys::gnsdk_decompile_options>() as u32, flags: 0, deadline_ms: 0, max_instructions: 0, want_tokens: 0, printer: 0, follow_flow_limit: 0, options_xml: ptr::null(), function_name: ptr::null() };
        let mut out: sys::gnsdk_decompile_out = unsafe { std::mem::zeroed() };
        out.struct_size = std::mem::size_of::<sys::gnsdk_decompile_out>() as u32;
        unsafe {
            let status = sys::gnsdk_decompile(self.raw.as_ptr(), address, &options, &mut out);
            let text = if out.c_text.data.is_null() {
                String::new()
            } else {
                String::from_utf8_lossy(std::slice::from_raw_parts(out.c_text.data, out.c_text.len)).into_owned()
            };
            sys::gnsdk_buf_free(&mut out.c_text); sys::gnsdk_buf_free(&mut out.tokens); sys::gnsdk_buf_free(&mut out.warnings);
            output_status(status)?;
            Ok(text)
        }
    }
}

impl Drop for Session {
    fn drop(&mut self) { unsafe { let _ = sys::gnsdk_session_destroy(self.raw.as_ptr()); } }
}

#[cfg(test)]
mod tests {
    use super::{init, Session};

    #[test]
    fn raw_x86_image_decompiles_when_native_home_is_configured() {
        let Ok(home) = std::env::var("GNSDK_SLEIGH_HOME") else {
            eprintln!("skipping native ABI integration: set GNSDK_SLEIGH_HOME");
            return;
        };
        init(&home).expect("native init");
        let mut session = Session::new("x86:LE:64:default").expect("x86 session");
        // push rbp; mov rbp,rsp; xor eax,eax; pop rbp; ret
        session.load_image(&[0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x5d, 0xc3], 0x400000)
            .expect("load image");
        assert!(!session.decompile(0x400000).expect("decompile").trim().is_empty());
    }
}
