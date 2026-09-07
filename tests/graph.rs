use std::fs;

use codeintel::{graph::GraphIndex, index::CodeIndex, structural::StructuralIndex};

use tempfile::tempdir;

fn build_chain() -> GraphIndex {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/lib.rs"),
        r#"
fn leaf() {}

fn middle() {
    leaf();
}

fn root() {
    middle();
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    GraphIndex::build(&structural)
}

#[test]
fn graph_builds_direct_edges() {
    let graph = build_chain();

    let leaf = graph.impact_symbol("leaf", 4);

    assert_eq!(leaf.direct_callers.len(), 1);

    assert_eq!(leaf.direct_callers[0].name, "middle");
}

#[test]
fn blast_radius_walks_upstream() {
    let graph = build_chain();

    let impact = graph.impact_symbol("leaf", 4);

    assert_eq!(impact.blast_radius, 2);

    assert!(
        impact
            .impacted
            .iter()
            .any(|entry| { entry.symbol.name == "middle" && entry.depth == 1 })
    );

    assert!(
        impact
            .impacted
            .iter()
            .any(|entry| { entry.symbol.name == "root" && entry.depth == 2 })
    );
}

#[test]
fn impact_respects_max_depth() {
    let graph = build_chain();

    let impact = graph.impact_symbol("leaf", 1);

    assert_eq!(impact.blast_radius, 1);

    assert!(impact.impacted.iter().all(|entry| entry.depth <= 1));
}

#[test]
fn pagerank_is_normalized() {
    let graph = build_chain();

    let ranked = graph.ranked_symbols(100);

    let total: f64 = ranked.iter().map(|entry| entry.pagerank).sum();

    assert!((total - 1.0).abs() < 1e-6);
}

#[test]
fn graph_does_not_include_unresolved_method_edges() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/lib.rs"),
        r#"
fn success() {}

fn caller() {
    output.status.success();
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let graph = GraphIndex::build(&structural);

    let impact = graph.impact_symbol("success", 4);

    assert_eq!(impact.blast_radius, 0);

    assert!(impact.direct_callers.is_empty());
}
