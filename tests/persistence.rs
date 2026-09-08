use std::{fs, path::Path};

use codeintel::{
    graph::GraphIndex,
    index::CodeIndex,
    manifest::{IndexManifest, scan_manifest},
    persistence::atomic_write_json,
    structural::StructuralIndex,
};

use serde::{Serialize, Serializer, ser::Error as _};

use serde_json::Value;
use tempfile::tempdir;

struct FailingSerialize;

impl Serialize for FailingSerialize {
    fn serialize<S>(&self, _serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        Err(S::Error::custom("intentional serialization failure"))
    }
}

fn assert_valid_json(path: &Path) {
    let bytes = fs::read(path).unwrap();

    serde_json::from_slice::<Value>(&bytes).unwrap();
}

fn assert_no_atomic_temps(dir: &Path) {
    let leftovers: Vec<_> = fs::read_dir(dir)
        .unwrap()
        .filter_map(Result::ok)
        .map(|entry| entry.file_name().to_string_lossy().to_string())
        .filter(|name| name.contains(".tmp-"))
        .collect();

    assert!(
        leftovers.is_empty(),
        "temporary files left behind: {leftovers:?}"
    );
}

#[test]
fn atomic_write_replaces_existing_json() {
    let dir = tempdir().unwrap();

    let path = dir.path().join("state.json");

    fs::write(&path, r#"{"version":1}"#).unwrap();

    atomic_write_json(
        &path,
        &serde_json::json!({
            "version": 2,
            "fresh": true
        }),
    )
    .unwrap();

    let value: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();

    assert_eq!(value["version"], 2);

    assert_eq!(value["fresh"], true);

    assert_no_atomic_temps(dir.path());
}

#[test]
fn failed_atomic_write_preserves_previous_file() {
    let dir = tempdir().unwrap();

    let path = dir.path().join("state.json");

    let original = br#"{"stable":true}"#;

    fs::write(&path, original).unwrap();

    let result = atomic_write_json(&path, &FailingSerialize);

    assert!(result.is_err());

    assert_eq!(fs::read(&path).unwrap(), original);

    assert_no_atomic_temps(dir.path());
}

#[test]
fn all_persistent_indexes_are_decodable() {
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

    let lexical = CodeIndex::build(dir.path()).unwrap();

    lexical.save().unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    structural.save().unwrap();

    let graph = GraphIndex::build(&structural);

    graph.save(dir.path()).unwrap();

    let manifest = scan_manifest(dir.path()).unwrap();

    manifest.save(dir.path()).unwrap();

    let index_dir = dir.path().join(".codeintel");

    for filename in [
        "index.json",
        "structural.json",
        "graph.json",
        "manifest.json",
    ] {
        assert_valid_json(&index_dir.join(filename));
    }

    CodeIndex::load(dir.path()).unwrap();

    StructuralIndex::load(dir.path()).unwrap();

    GraphIndex::load(dir.path()).unwrap();

    IndexManifest::load(dir.path()).unwrap();

    assert_no_atomic_temps(&index_dir);
}
