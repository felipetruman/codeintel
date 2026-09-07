use std::fs;

use codeintel::{context::build_context, index::CodeIndex, search::search_index};

use tempfile::tempdir;

#[test]
fn index_finds_literal_using_trigram_candidates() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/payment.rs"),
        "fn payment_retry() {\n    println!(\"retry payment\");\n}\n",
    )
    .unwrap();

    fs::write(dir.path().join("src/user.rs"), "fn create_user() {}\n").unwrap();

    let index = CodeIndex::build(dir.path()).unwrap();

    let hits = search_index(&index, "payment_retry", false, 20).unwrap();

    assert_eq!(hits.len(), 1);
    assert_eq!(hits[0].path, "src/payment.rs");
    assert_eq!(hits[0].line, 1);
}

#[test]
fn context_ranks_relevant_files() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/payment.rs"),
        r#"
fn process_payment() {}
fn payment_retry() {
    process_payment();
}
"#,
    )
    .unwrap();

    fs::write(
        dir.path().join("src/profile.rs"),
        "fn update_profile() {}\n",
    )
    .unwrap();

    let index = CodeIndex::build(dir.path()).unwrap();

    let bundle = build_context(&index, "implement payment retry", 10).unwrap();

    assert!(!bundle.files.is_empty());
    assert_eq!(bundle.files[0].path, "src/payment.rs");
}
