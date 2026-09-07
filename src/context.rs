use std::collections::{BTreeSet, HashMap};

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::{
    index::CodeIndex,
    search::{SearchHit, search_index},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextFile {
    pub path: String,
    pub score: usize,
    pub matches: Vec<SearchHit>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextBundle {
    pub task: String,
    pub files: Vec<ContextFile>,
}

pub fn build_context(index: &CodeIndex, task: &str, limit: usize) -> Result<ContextBundle> {
    let terms = extract_terms(task);

    let mut by_file: HashMap<String, ContextFile> = HashMap::new();

    for term in terms {
        let hits = search_index(index, &term, false, 30)?;

        for hit in hits {
            let entry = by_file
                .entry(hit.path.clone())
                .or_insert_with(|| ContextFile {
                    path: hit.path.clone(),
                    score: 0,
                    matches: Vec::new(),
                });

            entry.score += 1 + term.len();

            if entry.matches.len() < 5
                && !entry
                    .matches
                    .iter()
                    .any(|existing| existing.line == hit.line && existing.column == hit.column)
            {
                entry.matches.push(hit);
            }
        }
    }

    let mut files: Vec<ContextFile> = by_file.into_values().collect();

    files.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| left.path.cmp(&right.path))
    });

    files.truncate(limit);

    Ok(ContextBundle {
        task: task.to_string(),
        files,
    })
}

fn extract_terms(task: &str) -> Vec<String> {
    const STOPWORDS: &[&str] = &[
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "into",
        "uma",
        "para",
        "com",
        "como",
        "que",
        "dos",
        "das",
        "por",
        "implementar",
        "implement",
        "adicionar",
        "add",
    ];

    let mut terms = BTreeSet::new();

    for raw in task.split(|character: char| !character.is_alphanumeric() && character != '_') {
        let term = raw.trim().to_lowercase();

        if term.chars().count() < 3 {
            continue;
        }

        if STOPWORDS.contains(&term.as_str()) {
            continue;
        }

        terms.insert(term);
    }

    let mut terms: Vec<String> = terms.into_iter().collect();

    terms.sort_by_key(|term| std::cmp::Reverse(term.len()));

    terms
}
