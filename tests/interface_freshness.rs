use std::{
    fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
};

use serde_json::{Value, json};

use tempfile::tempdir;

fn codeintel() -> &'static str {
    env!("CARGO_BIN_EXE_codeintel")
}

fn run_cli(args: &[&str]) -> String {
    let output = Command::new(codeintel()).args(args).output().unwrap();

    assert!(
        output.status.success(),
        "CLI failed:\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr),
    );

    String::from_utf8(output.stdout).unwrap()
}

fn mcp_call(root: &Path, tool: &str, arguments: Value) -> Value {
    let mut child = Command::new(codeintel())
        .arg("mcp")
        .arg(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();

    let request = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": arguments
        }
    });

    {
        let mut stdin = child.stdin.take().unwrap();

        writeln!(stdin, "{}", request).unwrap();
    }

    let output = child.wait_with_output().unwrap();

    assert!(
        output.status.success(),
        "MCP failed:\nstdout={}\nstderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr),
    );

    let line = String::from_utf8(output.stdout).unwrap();

    let response: Value = serde_json::from_str(line.trim()).unwrap();

    assert!(
        response.get("error").is_none(),
        "MCP returned error: {response:#}"
    );

    response
}

fn mcp_text(response: &Value) -> &str {
    response
        .pointer("/result/content/0/text")
        .and_then(Value::as_str)
        .unwrap()
}

#[test]
fn cli_search_refreshes_after_source_edit_without_manual_index() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "pub fn old_cli_symbol() {}\n").unwrap();

    let root = dir.path().to_str().unwrap();

    let first = run_cli(&["search", "old_cli_symbol", root]);

    assert!(first.contains("src/lib.rs"));

    fs::write(
        &file,
        "pub fn brand_new_cli_symbol_with_changed_size() {}\n",
    )
    .unwrap();

    let fresh = run_cli(&["search", "brand_new_cli_symbol_with_changed_size", root]);

    assert!(fresh.contains("src/lib.rs"));

    let stale = run_cli(&["search", "old_cli_symbol", root]);

    let stale: Value = serde_json::from_str(&stale).unwrap();

    assert_eq!(stale, json!([]),);
}

#[test]
fn cli_symbol_refreshes_after_source_edit_without_manual_index() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "pub fn first_structural_symbol() {}\n").unwrap();

    let root = dir.path().to_str().unwrap();

    let first = run_cli(&["symbol", "first_structural_symbol", root]);

    assert!(first.contains("first_structural_symbol"));

    fs::write(&file, "pub fn second_structural_symbol_changed_size() {}\n").unwrap();

    let second = run_cli(&["symbol", "second_structural_symbol_changed_size", root]);

    assert!(second.contains("second_structural_symbol_changed_size"));

    let stale = run_cli(&["symbol", "first_structural_symbol", root]);

    let stale: Value = serde_json::from_str(&stale).unwrap();

    assert_eq!(stale["definitions"], json!([]),);
}

#[test]
fn mcp_code_search_refreshes_without_manual_index() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "pub fn mcp_old_symbol() {}\n").unwrap();

    let first = mcp_call(
        dir.path(),
        "code_search",
        json!({
            "query":
                "mcp_old_symbol"
        }),
    );

    assert!(mcp_text(&first).contains("src/lib.rs"));

    fs::write(&file, "pub fn mcp_new_symbol_with_changed_size() {}\n").unwrap();

    let fresh = mcp_call(
        dir.path(),
        "code_search",
        json!({
            "query":
                "mcp_new_symbol_with_changed_size"
        }),
    );

    assert!(mcp_text(&fresh).contains("src/lib.rs"));

    let stale = mcp_call(
        dir.path(),
        "code_search",
        json!({
            "query":
                "mcp_old_symbol"
        }),
    );

    let stale_text: Value = serde_json::from_str(mcp_text(&stale)).unwrap();

    assert_eq!(stale_text, json!([]),);
}

#[test]
fn mcp_code_symbol_refreshes_without_manual_index() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "pub fn initial_mcp_structure() {}\n").unwrap();

    mcp_call(
        dir.path(),
        "code_symbol",
        json!({
            "name":
                "initial_mcp_structure"
        }),
    );

    fs::write(&file, "pub fn refreshed_mcp_structure_changed_size() {}\n").unwrap();

    let refreshed = mcp_call(
        dir.path(),
        "code_symbol",
        json!({
            "name":
                "refreshed_mcp_structure_changed_size"
        }),
    );

    let result: Value = serde_json::from_str(mcp_text(&refreshed)).unwrap();

    assert_eq!(
        result["definitions"][0]["name"],
        "refreshed_mcp_structure_changed_size",
    );
}
