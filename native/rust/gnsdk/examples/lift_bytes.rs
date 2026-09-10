use gnsdk::{init, Session};

fn main() {
    let home = std::env::var("GNSDK_SLEIGH_HOME").expect("set GNSDK_SLEIGH_HOME");
    init(&home).expect("init");
    let mut session = Session::new("x86:LE:64:default").expect("session");
    session.load_image(&[0x55, 0x48, 0x89, 0xe5, 0x5d, 0xc3], 0x400000).expect("image");
    println!("{}", session.decompile(0x400000).expect("decompile"));
}
