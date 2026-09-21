//! Consume one JSONL stream produced by `gnsdk-batch` without a shared ABI.

use std::io::{self, BufRead};

fn main() {
    for line in io::stdin().lock().lines() {
        let line = line.expect("read batch JSONL");
        if !line.trim().is_empty() {
            // Keep this dependency-free: applications may deserialize with
            // serde_json, but the wire artifact remains ordinary JSONL.
            println!("{line}");
        }
    }
}
