use std::fs;

use anyhow::{Context, Result, bail};
use regex::Regex;
use serde::{Deserialize, Serialize};

use crate::index::CodeIndex;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SearchHit {
    pub path: String,
    pub line: usize,
    pub column: usize,
    pub text: String,
}

pub fn search_index(
    index: &CodeIndex,
    query: &str,
    regex_mode: bool,
    limit: usize,
) -> Result<Vec<SearchHit>> {
    if query.is_empty() {
        bail!("search query cannot be empty");
    }

    let regex = if regex_mode {
        Some(Regex::new(query).with_context(|| format!("invalid regex: {query}"))?)
    } else {
        None
    };

    let file_ids = if regex_mode {
        (0..index.files.len() as u32).collect()
    } else {
        index.candidate_file_ids(query)
    };

    let mut hits = Vec::new();

    for file_id in file_ids {
        if hits.len() >= limit {
            break;
        }

        let Some(path) = index.absolute_file_path(file_id) else {
            continue;
        };

        let Ok(bytes) = fs::read(&path) else {
            continue;
        };

        let content = String::from_utf8_lossy(&bytes);

        for (line_index, line) in content.lines().enumerate() {
            if hits.len() >= limit {
                break;
            }

            let column = if let Some(regex) = &regex {
                regex.find(line).map(|found| found.start() + 1)
            } else {
                line.find(query).map(|position| position + 1)
            };

            let Some(column) = column else {
                continue;
            };

            let relative = index
                .files
                .get(file_id as usize)
                .cloned()
                .unwrap_or_else(|| path.display().to_string());

            hits.push(SearchHit {
                path: relative,
                line: line_index + 1,
                column,
                text: line.trim().to_string(),
            });
        }
    }

    Ok(hits)
}
