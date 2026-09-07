use std::fs;

use codeintel::{
    index::CodeIndex,
    structural::{ReferenceResolution, StructuralIndex, SymbolKind},
};

use tempfile::tempdir;

#[test]
fn rust_extracts_definitions_and_resolves_calls() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/lib.rs"),
        r#"
fn caller() {
    callee();
}

fn callee() {
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    assert!(
        structural
            .definitions
            .iter()
            .any(|symbol| symbol.name == "caller")
    );

    assert!(
        structural
            .definitions
            .iter()
            .any(|symbol| symbol.name == "callee")
    );

    let call = structural
        .references
        .iter()
        .find(|reference| reference.name == "callee")
        .unwrap();

    assert!(call.owner.is_some());
    assert!(call.target.is_some());

    assert_eq!(call.resolution, ReferenceResolution::SameFile);

    let view = structural.lookup_symbol("callee");

    assert_eq!(view.definitions.len(), 1);

    assert!(view.callers.iter().any(|symbol| symbol.name == "caller"));
}

#[test]
fn python_extracts_function_relationships() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("app")).unwrap();

    fs::write(
        dir.path().join("app/service.py"),
        r#"
def helper():
    return 1

def main():
    return helper()
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let view = structural.lookup_symbol("helper");

    assert_eq!(view.definitions.len(), 1);

    assert!(view.callers.iter().any(|symbol| symbol.name == "main"));
}

#[test]
fn typescript_extracts_arrow_functions_and_calls() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/payment.ts"),
        r#"
const retryPayment = () => {
    return true;
};

function processPayment() {
    return retryPayment();
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let retry = structural
        .definitions
        .iter()
        .find(|symbol| symbol.name == "retryPayment")
        .unwrap();

    assert_eq!(retry.kind, SymbolKind::Function);

    let view = structural.lookup_symbol("retryPayment");

    assert!(
        view.callers
            .iter()
            .any(|symbol| symbol.name == "processPayment")
    );
}

#[test]
fn duplicate_global_definitions_remain_ambiguous() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(dir.path().join("src/a.rs"), "fn duplicate() {}\n").unwrap();

    fs::write(dir.path().join("src/b.rs"), "fn duplicate() {}\n").unwrap();

    fs::write(
        dir.path().join("src/c.rs"),
        "fn caller() { duplicate(); }\n",
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let reference = structural
        .references
        .iter()
        .find(|reference| reference.path == "src/c.rs" && reference.name == "duplicate")
        .unwrap();

    assert_eq!(reference.resolution, ReferenceResolution::Ambiguous);

    assert!(reference.target.is_none());
}

#[test]
fn javascript_extracts_functions_and_calls() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/service.js"),
        r#"
const helper = () => {
    return true;
};

function main() {
    return helper();
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let view = structural.lookup_symbol("helper");

    assert_eq!(view.definitions.len(), 1);

    assert!(view.callers.iter().any(|symbol| { symbol.name == "main" }));
}

#[test]
fn tsx_extracts_arrow_functions_and_calls() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    fs::write(
        dir.path().join("src/app.tsx"),
        r#"
const renderItem = () => {
    return <div>Hello</div>;
};

function App() {
    return renderItem();
}
"#,
    )
    .unwrap();

    let lexical = CodeIndex::build(dir.path()).unwrap();

    let structural = StructuralIndex::build(dir.path(), &lexical.files).unwrap();

    let view = structural.lookup_symbol("renderItem");

    assert_eq!(view.definitions.len(), 1);

    assert!(view.callers.iter().any(|symbol| { symbol.name == "App" }));
}
