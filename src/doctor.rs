use std::{
    env,
    path::{Path, PathBuf},
};

use anyhow::Result;
use serde::Serialize;

use crate::{index::index_path, structural::structural_path};

#[derive(Debug, Serialize)]
pub struct DoctorCheck {
    pub name: String,
    pub status: String,
    pub detail: String,
}

pub fn run(root: &Path) -> Result<Vec<DoctorCheck>> {
    let mut checks = vec![
        command_check("git"),
        command_check("rg"),
        command_check("claude"),
        command_check("codex"),
    ];

    let lexical = index_path(root);

    checks.push(DoctorCheck {
        name: "lexical_index".into(),
        status: if lexical.exists() {
            "ok".into()
        } else {
            "missing".into()
        },
        detail: lexical.display().to_string(),
    });

    let structural = structural_path(root);

    checks.push(DoctorCheck {
        name: "structural_index".into(),
        status: if structural.exists() {
            "ok".into()
        } else {
            "missing".into()
        },
        detail: structural.display().to_string(),
    });

    checks.push(DoctorCheck {
        name: "workspace".into(),
        status: "ok".into(),
        detail: root.display().to_string(),
    });

    Ok(checks)
}

fn command_check(command: &str) -> DoctorCheck {
    let found = executable_on_path(command);

    DoctorCheck {
        name: command.to_string(),
        status: if found { "ok".into() } else { "missing".into() },
        detail: if found {
            "available on PATH".into()
        } else {
            "not found on PATH".into()
        },
    }
}

fn executable_on_path(name: &str) -> bool {
    let Some(path) = env::var_os("PATH") else {
        return false;
    };

    env::split_paths(&path)
        .map(|directory| directory.join(name))
        .any(|candidate: PathBuf| candidate.is_file())
}
