use std::fs;

use codeintel::{
    index::CodeIndex,
    manifest::{compare_manifests, scan_manifest},
    search::search_index,
};

use tempfile::tempdir;

#[test]
fn incremental_lexical_adds_new_file() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn existing_symbol() {}\n").unwrap();

    let old_manifest = scan_manifest(dir.path()).unwrap();

    let previous = CodeIndex::build(dir.path()).unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn brand_new_symbol() {}\n").unwrap();

    let new_manifest = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&old_manifest, &new_manifest);

    let (refreshed, stats) =
        CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    let hits = search_index(&refreshed, "brand_new_symbol", false, 20).unwrap();

    assert_eq!(hits.len(), 1);

    assert_eq!(hits[0].path, "src/b.rs");

    assert_eq!(stats.reindexed, 1);
    assert_eq!(stats.reused, 1);
}

#[test]
fn incremental_lexical_removes_deleted_file() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/keep.rs"), "fn keep_symbol() {}\n").unwrap();

    let removed = dir.path().join("src/remove.rs");

    fs::write(&removed, "fn deleted_symbol() {}\n").unwrap();

    let old_manifest = scan_manifest(dir.path()).unwrap();

    let previous = CodeIndex::build(dir.path()).unwrap();

    fs::remove_file(&removed).unwrap();

    let new_manifest = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&old_manifest, &new_manifest);

    let (refreshed, stats) =
        CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    assert!(
        !refreshed
            .files
            .iter()
            .any(|path| { path == "src/remove.rs" })
    );

    assert!(refreshed.candidate_file_ids("deleted_symbol",).is_empty());

    assert_eq!(stats.removed, 1);
    assert_eq!(stats.reused, 1);
}

#[test]
fn incremental_lexical_replaces_modified_content() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "fn legacy_handler() {}\n").unwrap();

    let old_manifest = scan_manifest(dir.path()).unwrap();

    let previous = CodeIndex::build(dir.path()).unwrap();

    fs::write(&file, "fn modern_handler() {}\n").unwrap();

    let new_manifest = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&old_manifest, &new_manifest);

    let (refreshed, stats) =
        CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    assert!(refreshed.candidate_file_ids("legacy_handler",).is_empty());

    let hits = search_index(&refreshed, "modern_handler", false, 20).unwrap();

    assert_eq!(hits.len(), 1);

    assert_eq!(hits[0].path, "src/lib.rs");

    assert_eq!(stats.reindexed, 1);
    assert_eq!(stats.reused, 0);
}

#[test]
fn incremental_lexical_reuses_unchanged_file_data() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn alpha_symbol() {}\n").unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn beta_symbol() {}\n").unwrap();

    let old_manifest = scan_manifest(dir.path()).unwrap();

    let previous = CodeIndex::build(dir.path()).unwrap();

    let alpha_before = previous.file_trigrams.get("src/a.rs").unwrap().clone();

    fs::write(dir.path().join("src/b.rs"), "fn gamma_symbol() {}\n").unwrap();

    let new_manifest = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&old_manifest, &new_manifest);

    let (refreshed, stats) =
        CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    assert_eq!(stats.reused, 1);
    assert_eq!(stats.reindexed, 1);

    assert_eq!(
        refreshed.file_trigrams.get("src/a.rs").unwrap(),
        &alpha_before
    );
}

#[test]
fn incremental_lexical_is_deterministic() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn shared_symbol() {}\n").unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn shared_symbol() {}\n").unwrap();

    let manifest = scan_manifest(dir.path()).unwrap();

    let previous = CodeIndex::build(dir.path()).unwrap();

    let changes = compare_manifests(&manifest, &manifest);

    let (first, _) = CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    let (second, _) = CodeIndex::refresh_incremental(dir.path(), &previous, &changes).unwrap();

    assert_eq!(first.files, second.files);

    assert_eq!(first.postings, second.postings);

    assert_eq!(first.file_trigrams, second.file_trigrams);
}
