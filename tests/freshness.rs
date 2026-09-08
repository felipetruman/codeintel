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

#[test]
fn freshness_pipeline_creates_persistent_state() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/lib.rs"),
        r#"
pub fn service() {}

pub fn caller() {
    service();
}
"#,
    )
    .unwrap();

    let fresh = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(fresh.stats.scanned, 1);

    assert_eq!(fresh.stats.added, 1);

    assert_eq!(fresh.stats.reused, 0);

    assert_eq!(fresh.stats.reparsed, 1);

    for filename in [
        "manifest.json",
        "index.json",
        "structural.json",
        "graph.json",
    ] {
        assert!(
            dir.path().join(".codeintel").join(filename).is_file(),
            "missing {filename}",
        );
    }
}

#[test]
fn second_freshness_pass_reparses_zero_files() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn alpha() {}\n").unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn beta() {}\n").unwrap();

    codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    let second = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(second.stats.scanned, 2);

    assert_eq!(second.stats.reused, 2);

    assert_eq!(second.stats.added, 0);

    assert_eq!(second.stats.modified, 0);

    assert_eq!(second.stats.deleted, 0);

    assert_eq!(second.stats.reparsed, 0);
}

#[test]
fn freshness_pipeline_refreshes_changed_source() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let service = dir.path().join("src/service.rs");

    fs::write(&service, "pub fn shared_service() {}\n").unwrap();

    fs::write(
        dir.path().join("src/caller.rs"),
        r#"
fn caller() {
    shared_service();
}
"#,
    )
    .unwrap();

    codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    fs::write(&service, "pub fn renamed_service_with_new_size() {}\n").unwrap();

    let refreshed = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(refreshed.stats.modified, 1);

    assert_eq!(refreshed.stats.reparsed, 1);

    let hits = codeintel::search::search_index(
        &refreshed.lexical,
        "renamed_service_with_new_size",
        false,
        20,
    )
    .unwrap();

    assert_eq!(hits.len(), 1);

    let old_symbol_hits =
        codeintel::search::search_index(&refreshed.lexical, "shared_service", false, 20).unwrap();

    // "shared_service" ainda existe textualmente em caller.rs.
    // O que deve desaparecer é a definição antiga em service.rs.
    assert!(
        old_symbol_hits
            .iter()
            .all(|hit| { hit.path != "src/service.rs" })
    );

    assert!(
        old_symbol_hits
            .iter()
            .any(|hit| { hit.path == "src/caller.rs" })
    );

    assert!(
        refreshed
            .structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "renamed_service_with_new_size" })
    );

    assert!(
        !refreshed
            .structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "shared_service" })
    );

    let stale_reference = refreshed
        .structural
        .references
        .iter()
        .find(|reference| reference.path == "src/caller.rs" && reference.name == "shared_service")
        .unwrap();

    assert_eq!(stale_reference.target, None);

    let total_rank: f64 = refreshed.graph.pagerank.values().sum();

    assert!((total_rank - 1.0).abs() < 1e-6);
}

#[test]
fn corrupted_manifest_triggers_safe_rebuild() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn recoverable() {}\n").unwrap();

    codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    fs::write(dir.path().join(".codeintel/manifest.json"), "{broken").unwrap();

    let rebuilt = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(rebuilt.stats.reused, 0);

    assert_eq!(rebuilt.stats.added, 1);

    assert_eq!(rebuilt.stats.reparsed, 1);

    IndexManifest::load(dir.path()).unwrap();
}

#[test]
fn manifest_schema_mismatch_triggers_safe_rebuild() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn schema_test() {}\n").unwrap();

    codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    let mut manifest = IndexManifest::load(dir.path()).unwrap();

    manifest.schema_version = MANIFEST_SCHEMA_VERSION + 1;

    manifest.save(dir.path()).unwrap();

    let rebuilt = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(rebuilt.stats.reused, 0);

    assert_eq!(rebuilt.stats.reparsed, 1);

    let manifest = IndexManifest::load(dir.path()).unwrap();

    assert_eq!(manifest.schema_version, MANIFEST_SCHEMA_VERSION,);
}

#[test]
fn missing_graph_index_triggers_safe_rebuild() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn graph_recovery() {}\n").unwrap();

    codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    fs::remove_file(dir.path().join(".codeintel/graph.json")).unwrap();

    let rebuilt = codeintel::freshness::ensure_fresh_indexes(dir.path()).unwrap();

    assert_eq!(rebuilt.stats.reused, 0);

    assert_eq!(rebuilt.stats.reparsed, 1);

    assert!(dir.path().join(".codeintel/graph.json").is_file());
}
