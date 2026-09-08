use std::fs;

use codeintel::{
    context::build_hybrid_context, graph::GraphIndex, index::CodeIndex, structural::StructuralIndex,
};
use tempfile::{TempDir, tempdir};

fn indexes(files: &[(&str, &str)]) -> (TempDir, CodeIndex, StructuralIndex, GraphIndex) {
    let dir = tempdir().unwrap();

    for (path, content) in files {
        let absolute = dir.path().join(path);

        if let Some(parent) = absolute.parent() {
            fs::create_dir_all(parent).unwrap();
        }

        fs::write(absolute, content).unwrap();
    }

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let graph = GraphIndex::build(&structural);

    (dir, lexical, structural, graph)
}

#[test]
fn lexical_relevance_survives_hybrid_fusion() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/payment.rs", "fn payment_retry() {}\n"),
        ("src/profile.rs", "fn update_profile() {}\n"),
    ]);

    let bundle = build_hybrid_context(&lexical, &structural, &graph, "payment retry", 10).unwrap();

    assert_eq!(bundle.files[0].path, "src/payment.rs");

    assert!(bundle.files[0].lexical_rank.is_some());
}

#[test]
fn structural_exact_match_beats_lexical_noise() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/payment.rs", "fn payment_handler() {}\n"),
        (
            "notes/payment_handler.txt",
            concat!(
                "payment_handler\n",
                "payment_handler\n",
                "payment_handler\n",
                "payment_handler\n",
                "payment_handler\n"
            ),
        ),
    ]);

    let bundle =
        build_hybrid_context(&lexical, &structural, &graph, "payment_handler", 10).unwrap();

    assert_eq!(bundle.files[0].path, "src/payment.rs");

    assert!(bundle.files[0].structural_rank.is_some());
}

#[test]
fn graph_importance_and_proximity_are_exposed() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/core.rs", "pub fn shared_service() {}\n"),
        (
            "src/a.rs",
            r#"
fn caller_a() {
    shared_service();
}
"#,
        ),
        (
            "src/b.rs",
            r#"
fn caller_b() {
    shared_service();
}
"#,
        ),
    ]);

    let bundle = build_hybrid_context(&lexical, &structural, &graph, "shared_service", 10).unwrap();

    let core = bundle
        .files
        .iter()
        .find(|file| file.path == "src/core.rs")
        .unwrap();

    assert!(core.graph_rank.is_some());
    assert!(core.proximity_rank.is_some());

    assert!(
        bundle
            .files
            .iter()
            .any(|file| { file.path == "src/a.rs" && file.proximity_rank.is_some() })
    );
}

#[test]
fn tests_are_penalized_unless_task_targets_tests() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/payment.rs", "fn payment_handler() {}\n"),
        ("tests/payment.rs", "fn payment_handler() {}\n"),
    ]);

    let default_bundle =
        build_hybrid_context(&lexical, &structural, &graph, "payment_handler", 10).unwrap();

    let test_file = default_bundle
        .files
        .iter()
        .find(|file| file.path == "tests/payment.rs")
        .unwrap();

    assert_eq!(test_file.penalty, 0.75);

    let explicit_bundle =
        build_hybrid_context(&lexical, &structural, &graph, "test payment_handler", 10).unwrap();

    let test_file = explicit_bundle
        .files
        .iter()
        .find(|file| file.path == "tests/payment.rs")
        .unwrap();

    assert_eq!(test_file.penalty, 1.0);
}

#[test]
fn docs_are_penalized_unless_task_targets_docs() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/architecture.rs", "fn architecture_guide() {}\n"),
        ("docs/architecture_guide.md", "architecture_guide\n"),
    ]);

    let default_bundle =
        build_hybrid_context(&lexical, &structural, &graph, "architecture_guide", 10).unwrap();

    let docs = default_bundle
        .files
        .iter()
        .find(|file| file.path == "docs/architecture_guide.md")
        .unwrap();

    assert_eq!(docs.penalty, 0.60);

    let explicit_bundle =
        build_hybrid_context(&lexical, &structural, &graph, "docs architecture_guide", 10).unwrap();

    let docs = explicit_bundle
        .files
        .iter()
        .find(|file| file.path == "docs/architecture_guide.md")
        .unwrap();

    assert_eq!(docs.penalty, 1.0);
}

#[test]
fn empty_structural_graph_degrades_to_lexical() {
    let (dir, lexical, _structural, _graph) =
        indexes(&[("src/payment.rs", "fn payment_retry() {}\n")]);

    let empty_structural = StructuralIndex {
        root: dir
            .path()
            .canonicalize()
            .unwrap()
            .to_string_lossy()
            .to_string(),
        definitions: Vec::new(),
        references: Vec::new(),
        file_data: Default::default(),
        indexed_at_unix: 0,
    };

    let empty_graph = GraphIndex::build(&empty_structural);

    let bundle = build_hybrid_context(
        &lexical,
        &empty_structural,
        &empty_graph,
        "payment retry",
        10,
    )
    .unwrap();

    assert_eq!(bundle.files[0].path, "src/payment.rs");
}

#[test]
fn ordering_is_deterministic() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/a.rs", "fn common_handler() {}\n"),
        ("src/b.rs", "fn common_handler() {}\n"),
    ]);

    let first = build_hybrid_context(&lexical, &structural, &graph, "common_handler", 10).unwrap();

    let second = build_hybrid_context(&lexical, &structural, &graph, "common_handler", 10).unwrap();

    let first_paths: Vec<_> = first.files.iter().map(|file| &file.path).collect();

    let second_paths: Vec<_> = second.files.iter().map(|file| &file.path).collect();

    assert_eq!(first_paths, second_paths);
}

#[test]
fn limit_is_respected() {
    let (_dir, lexical, structural, graph) = indexes(&[
        ("src/a.rs", "fn shared() {}\n"),
        ("src/b.rs", "fn shared() {}\n"),
        ("src/c.rs", "fn shared() {}\n"),
    ]);

    let bundle = build_hybrid_context(&lexical, &structural, &graph, "shared", 2).unwrap();

    assert_eq!(bundle.files.len(), 2);
}
