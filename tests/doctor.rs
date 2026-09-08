use std::{fs, path::Path};

use codeintel::{
    doctor::{self, DoctorCheck},
    freshness::ensure_fresh_indexes,
    manifest::{IndexManifest, MANIFEST_SCHEMA_VERSION},
};

use tempfile::tempdir;

fn check<'a>(checks: &'a [DoctorCheck], name: &str) -> &'a DoctorCheck {
    checks
        .iter()
        .find(|check| check.name == name)
        .unwrap_or_else(|| panic!("missing doctor check: {name}"))
}

fn snapshot_indexes(root: &Path) -> Vec<(String, Vec<u8>)> {
    [
        "manifest.json",
        "index.json",
        "structural.json",
        "graph.json",
    ]
    .into_iter()
    .map(|name| {
        (
            name.to_string(),
            fs::read(root.join(".codeintel").join(name)).unwrap(),
        )
    })
    .collect()
}

#[test]
fn doctor_missing_state_is_read_only() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn source_exists() {}\n").unwrap();

    assert!(!dir.path().join(".codeintel").exists());

    let checks = doctor::run(dir.path()).unwrap();

    assert_eq!(check(&checks, "manifest",).status, "missing",);

    assert_eq!(check(&checks, "lexical_index",).status, "missing",);

    assert_eq!(check(&checks, "structural_index",).status, "missing",);

    assert_eq!(check(&checks, "graph_index",).status, "missing",);

    assert_eq!(check(&checks, "index_freshness",).status, "missing",);

    assert!(
        !dir.path().join(".codeintel").exists(),
        "doctor must not create index state",
    );
}

#[test]
fn doctor_reports_fresh_coherent_state() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/lib.rs"),
        r#"
fn service() {}

fn caller() {
    service();
}
"#,
    )
    .unwrap();

    ensure_fresh_indexes(dir.path()).unwrap();

    let before = snapshot_indexes(dir.path());

    let checks = doctor::run(dir.path()).unwrap();

    assert_eq!(check(&checks, "manifest",).status, "ok",);

    assert_eq!(check(&checks, "lexical_index",).status, "ok",);

    assert_eq!(check(&checks, "structural_index",).status, "ok",);

    assert_eq!(check(&checks, "graph_index",).status, "ok",);

    assert_eq!(check(&checks, "index_freshness",).status, "fresh",);

    assert_eq!(
        snapshot_indexes(dir.path(),),
        before,
        "doctor mutated fresh indexes",
    );
}

#[test]
fn doctor_reports_stale_source_without_refreshing_indexes() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "fn before_doctor() {}\n").unwrap();

    ensure_fresh_indexes(dir.path()).unwrap();

    let persisted_before = snapshot_indexes(dir.path());

    fs::write(&file, "fn after_doctor_changed_size() {}\n").unwrap();

    let checks = doctor::run(dir.path()).unwrap();

    let freshness = check(&checks, "index_freshness");

    assert_eq!(freshness.status, "stale",);

    assert!(
        freshness.detail.contains("modified=1"),
        "{}",
        freshness.detail,
    );

    assert_eq!(
        snapshot_indexes(dir.path(),),
        persisted_before,
        "doctor refreshed indexes even though it must be read-only",
    );

    let structural = codeintel::structural::StructuralIndex::load(dir.path()).unwrap();

    assert!(
        structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "before_doctor" })
    );

    assert!(
        !structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "after_doctor_changed_size" })
    );
}

#[test]
fn doctor_reports_corrupt_manifest_without_repairing_it() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn corrupt_test() {}\n").unwrap();

    ensure_fresh_indexes(dir.path()).unwrap();

    let manifest = dir.path().join(".codeintel/manifest.json");

    fs::write(&manifest, "{broken").unwrap();

    let before = fs::read(&manifest).unwrap();

    let checks = doctor::run(dir.path()).unwrap();

    assert_eq!(check(&checks, "manifest",).status, "corrupt",);

    assert_eq!(check(&checks, "index_freshness",).status, "invalid",);

    assert_eq!(
        fs::read(&manifest,).unwrap(),
        before,
        "doctor repaired corrupt manifest",
    );
}

#[test]
fn doctor_reports_incompatible_manifest_schema_without_rewriting() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/lib.rs"), "fn schema_test() {}\n").unwrap();

    ensure_fresh_indexes(dir.path()).unwrap();

    let mut manifest = IndexManifest::load(dir.path()).unwrap();

    manifest.schema_version = MANIFEST_SCHEMA_VERSION + 1;

    manifest.save(dir.path()).unwrap();

    let before = fs::read(dir.path().join(".codeintel/manifest.json")).unwrap();

    let checks = doctor::run(dir.path()).unwrap();

    assert_eq!(check(&checks, "manifest",).status, "incompatible",);

    assert_eq!(check(&checks, "index_freshness",).status, "invalid",);

    assert_eq!(
        fs::read(dir.path().join(".codeintel/manifest.json",),).unwrap(),
        before,
    );
}
