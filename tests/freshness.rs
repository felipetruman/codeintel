use std::fs;

use codeintel::manifest::{
    IndexManifest, MANIFEST_SCHEMA_VERSION, compare_manifests, scan_manifest,
};

use tempfile::tempdir;

#[test]
fn manifest_round_trip() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/main.rs"), "fn main() {}\n").unwrap();

    let manifest = scan_manifest(dir.path()).unwrap();

    manifest.save(dir.path()).unwrap();

    let loaded = IndexManifest::load(dir.path()).unwrap();

    assert_eq!(loaded.schema_version, MANIFEST_SCHEMA_VERSION,);

    assert_eq!(loaded.root, manifest.root,);

    assert_eq!(loaded.files, manifest.files,);
}

#[test]
fn unchanged_files_are_classified_unchanged() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "pub fn stable() {}\n").unwrap();

    let first = scan_manifest(dir.path()).unwrap();

    let second = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&first, &second);

    assert_eq!(changes.unchanged, vec!["src/lib.rs"],);

    assert!(changes.added.is_empty());
    assert!(changes.modified.is_empty());
    assert!(changes.deleted.is_empty());
}

#[test]
fn new_file_is_classified_added() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn a() {}\n").unwrap();

    let before = scan_manifest(dir.path()).unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn b() {}\n").unwrap();

    let after = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&before, &after);

    assert_eq!(changes.added, vec!["src/b.rs"],);
}

#[test]
fn edited_file_is_classified_modified() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "fn old_name() {}\n").unwrap();

    let before = scan_manifest(dir.path()).unwrap();

    // Same-length content deliberately verifies that
    // content identity is not based only on file size.
    fs::write(&file, "fn new_name() {}\n").unwrap();

    let after = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&before, &after);

    assert_eq!(changes.modified, vec!["src/lib.rs"],);

    assert!(changes.unchanged.is_empty());
}

#[test]
fn removed_file_is_classified_deleted() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/old.rs");

    fs::write(&file, "fn old() {}\n").unwrap();

    let before = scan_manifest(dir.path()).unwrap();

    fs::remove_file(file).unwrap();

    let after = scan_manifest(dir.path()).unwrap();

    let changes = compare_manifests(&before, &after);

    assert_eq!(changes.deleted, vec!["src/old.rs"],);
}

#[test]
fn manifest_ignores_codeintel_internal_files() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::create_dir_all(dir.path().join(".codeintel")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn visible() {}\n").unwrap();

    fs::write(dir.path().join(".codeintel/internal.json"), "{}").unwrap();

    let manifest = scan_manifest(dir.path()).unwrap();

    assert!(manifest.files.contains_key("src/lib.rs"));

    assert!(!manifest.files.contains_key(".codeintel/internal.json"));
}
