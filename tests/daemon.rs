use std::{
    fs,
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use codeintel::{daemon, structural::StructuralIndex};

use tempfile::tempdir;

struct ChildGuard {
    child: Child,
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.child.kill();

        let _ = self.child.wait();
    }
}

fn wait_until<F>(timeout: Duration, mut condition: F) -> bool
where
    F: FnMut() -> bool,
{
    let deadline = Instant::now() + timeout;

    while Instant::now() < deadline {
        if condition() {
            return true;
        }

        thread::sleep(Duration::from_millis(50));
    }

    false
}

#[test]
fn daemon_refresh_once_uses_incremental_pipeline() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let a = dir.path().join("src/a.rs");

    let b = dir.path().join("src/b.rs");

    fs::write(&a, "fn alpha() {}\n").unwrap();

    fs::write(&b, "fn beta() {}\n").unwrap();

    let first = daemon::refresh_once(dir.path()).unwrap();

    assert_eq!(first.stats.added, 2);

    assert_eq!(first.stats.reparsed, 2);

    let second = daemon::refresh_once(dir.path()).unwrap();

    assert_eq!(second.stats.reused, 2);

    assert_eq!(second.stats.reparsed, 0);

    fs::write(&b, "fn gamma_changed_size() {}\n").unwrap();

    let third = daemon::refresh_once(dir.path()).unwrap();

    assert_eq!(third.stats.modified, 1);

    assert_eq!(third.stats.reused, 1);

    assert_eq!(third.stats.reparsed, 1);

    assert!(
        third
            .structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "gamma_changed_size" })
    );

    assert!(
        !third
            .structural
            .definitions
            .iter()
            .any(|symbol| { symbol.name == "beta" })
    );
}

#[test]
fn serve_watcher_refreshes_persisted_indexes() {
    let dir = tempdir().unwrap();

    fs::create_dir_all(dir.path().join("src")).unwrap();

    let file = dir.path().join("src/lib.rs");

    fs::write(&file, "pub fn watcher_before() {}\n").unwrap();

    let child = Command::new(env!("CARGO_BIN_EXE_codeintel"))
        .arg("serve")
        .arg(dir.path())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();

    let _guard = ChildGuard { child };

    let initialized = wait_until(Duration::from_secs(5), || {
        StructuralIndex::load(dir.path()).is_ok_and(|index| {
            index
                .definitions
                .iter()
                .any(|symbol| symbol.name == "watcher_before")
        })
    });

    assert!(
        initialized,
        "daemon did not create initial structural index"
    );

    fs::write(&file, "pub fn watcher_after_changed_size() {}\n").unwrap();

    let refreshed = wait_until(Duration::from_secs(5), || {
        StructuralIndex::load(dir.path()).is_ok_and(|index| {
            let new_exists = index
                .definitions
                .iter()
                .any(|symbol| symbol.name == "watcher_after_changed_size");

            let old_exists = index
                .definitions
                .iter()
                .any(|symbol| symbol.name == "watcher_before");

            new_exists && !old_exists
        })
    });

    assert!(
        refreshed,
        "daemon did not persist refreshed structural index"
    );
}
