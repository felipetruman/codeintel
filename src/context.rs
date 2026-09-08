use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet, VecDeque},
    path::Path,
};

use anyhow::Result;
use serde::{Deserialize, Serialize};

use crate::{
    graph::GraphIndex,
    index::CodeIndex,
    search::{SearchHit, search_index},
    structural::StructuralIndex,
};

const RRF_K: f64 = 60.0;

const LEXICAL_WEIGHT: f64 = 1.00;
const STRUCTURAL_WEIGHT: f64 = 1.20;
const GRAPH_WEIGHT: f64 = 0.80;
const PROXIMITY_WEIGHT: f64 = 1.00;

const PROXIMITY_DEPTH: usize = 2;

type ScoreMap = BTreeMap<String, f64>;
type RankMap = BTreeMap<String, usize>;
type MatchMap = BTreeMap<String, Vec<SearchHit>>;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextFile {
    pub path: String,
    pub score: f64,

    pub lexical_rank: Option<usize>,

    pub structural_rank: Option<usize>,

    pub graph_rank: Option<usize>,

    pub proximity_rank: Option<usize>,

    pub penalty: f64,

    pub matches: Vec<SearchHit>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextBundle {
    pub task: String,
    pub files: Vec<ContextFile>,
}

pub fn build_context(index: &CodeIndex, task: &str, limit: usize) -> Result<ContextBundle> {
    let terms = extract_terms(task);

    let (lexical_ranks, mut matches) = lexical_ranking(index, &terms)?;

    let mut files: Vec<ContextFile> = lexical_ranks
        .iter()
        .map(|(path, rank)| ContextFile {
            path: path.clone(),

            score: 1.0 / (RRF_K + *rank as f64),

            lexical_rank: Some(*rank),

            structural_rank: None,

            graph_rank: None,

            proximity_rank: None,

            penalty: 1.0,

            matches: matches.remove(path).unwrap_or_default(),
        })
        .collect();

    sort_context_files(&mut files, limit);

    Ok(ContextBundle {
        task: task.to_string(),
        files,
    })
}

pub fn build_hybrid_context(
    lexical: &CodeIndex,
    structural: &StructuralIndex,
    graph: &GraphIndex,
    task: &str,
    limit: usize,
) -> Result<ContextBundle> {
    let terms = extract_terms(task);

    let (lexical_ranks, mut matches) = lexical_ranking(lexical, &terms)?;

    let (structural_ranks, seeds) = structural_ranking(structural, &terms);

    let graph_ranks = graph_ranking(graph);

    let proximity_ranks = proximity_ranking(graph, &seeds);

    let mut candidates = BTreeSet::new();

    candidates.extend(lexical_ranks.keys().cloned());

    candidates.extend(structural_ranks.keys().cloned());

    candidates.extend(proximity_ranks.keys().cloned());

    let mut files = Vec::new();

    for path in candidates {
        let lexical_rank = lexical_ranks.get(&path).copied();

        let structural_rank = structural_ranks.get(&path).copied();

        let graph_rank = graph_ranks.get(&path).copied();

        let proximity_rank = proximity_ranks.get(&path).copied();

        let fused = rrf_score(lexical_rank, LEXICAL_WEIGHT)
            + rrf_score(structural_rank, STRUCTURAL_WEIGHT)
            + rrf_score(graph_rank, GRAPH_WEIGHT)
            + rrf_score(proximity_rank, PROXIMITY_WEIGHT);

        let penalty = path_penalty(&path, task);

        files.push(ContextFile {
            path: path.clone(),
            score: fused * penalty,

            lexical_rank,
            structural_rank,
            graph_rank,
            proximity_rank,

            penalty,

            matches: matches.remove(&path).unwrap_or_default(),
        });
    }

    sort_context_files(&mut files, limit);

    Ok(ContextBundle {
        task: task.to_string(),
        files,
    })
}

pub fn build_repository_context(
    root: &Path,
    lexical: &CodeIndex,
    task: &str,
    limit: usize,
) -> Result<ContextBundle> {
    let structural = match StructuralIndex::ensure(root, &lexical.files) {
        Ok(index) => index,

        Err(_) => {
            return build_context(lexical, task, limit);
        }
    };

    let graph = match GraphIndex::ensure(root, &structural) {
        Ok(index) => index,

        Err(_) => {
            return build_context(lexical, task, limit);
        }
    };

    build_hybrid_context(lexical, &structural, &graph, task, limit)
}

fn lexical_ranking(index: &CodeIndex, terms: &[String]) -> Result<(RankMap, MatchMap)> {
    let mut scores = ScoreMap::new();

    let mut matched_terms: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();

    let mut matches = MatchMap::new();

    for term in terms {
        let hits = search_index(index, term, false, 50)?;

        for (position, hit) in hits.into_iter().enumerate() {
            let path = hit.path.clone();

            let first_term = matched_terms
                .entry(path.clone())
                .or_default()
                .insert(term.clone());

            let score = scores.entry(path.clone()).or_default();

            if first_term {
                *score += 1.0 + term.len() as f64 / 10.0;
            }

            *score += 1.0 / (position as f64 + 1.0);

            let file_matches = matches.entry(path).or_default();

            if file_matches.len() < 5
                && !file_matches
                    .iter()
                    .any(|existing| existing.line == hit.line && existing.column == hit.column)
            {
                file_matches.push(hit);
            }
        }
    }

    Ok((rank_scores(scores), matches))
}

fn structural_ranking(structural: &StructuralIndex, terms: &[String]) -> (RankMap, BTreeSet<u64>) {
    let mut scores = ScoreMap::new();

    let mut seeds = BTreeSet::new();

    for definition in &structural.definitions {
        let name = definition.name.to_lowercase();

        let mut matched = false;

        for term in terms {
            if name == *term {
                *scores.entry(definition.path.clone()).or_default() += 10.0;

                matched = true;
            } else if name.contains(term) {
                *scores.entry(definition.path.clone()).or_default() += 5.0;

                matched = true;
            }
        }

        if matched {
            seeds.insert(definition.id);
        }
    }

    for reference in &structural.references {
        let name = reference.name.to_lowercase();

        let mut matched = false;

        for term in terms {
            if name == *term {
                *scores.entry(reference.path.clone()).or_default() += 3.0;

                matched = true;
            } else if name.contains(term) {
                *scores.entry(reference.path.clone()).or_default() += 1.0;

                matched = true;
            }
        }

        if matched {
            if let Some(owner) = reference.owner {
                seeds.insert(owner);
            }

            if let Some(target) = reference.target {
                seeds.insert(target);
            }
        }
    }

    (rank_scores(scores), seeds)
}

fn graph_ranking(graph: &GraphIndex) -> RankMap {
    let mut aggregate: BTreeMap<String, (f64, f64)> = BTreeMap::new();

    for (id, symbol) in &graph.nodes {
        let rank = graph.pagerank.get(id).copied().unwrap_or(0.0);

        let entry = aggregate
            .entry(symbol.path.clone())
            .or_insert((0.0_f64, 0.0_f64));

        entry.0 = entry.0.max(rank);

        entry.1 += rank;
    }

    let scores = aggregate
        .into_iter()
        .map(|(path, (max_rank, sum_rank))| (path, max_rank + 0.25 * (sum_rank - max_rank)))
        .collect();

    rank_scores(scores)
}

fn proximity_ranking(graph: &GraphIndex, seeds: &BTreeSet<u64>) -> RankMap {
    let mut depths: BTreeMap<u64, usize> = BTreeMap::new();

    let mut queue = VecDeque::new();

    for seed in seeds {
        if graph.nodes.contains_key(seed) {
            depths.insert(*seed, 0);

            queue.push_back(*seed);
        }
    }

    while let Some(id) = queue.pop_front() {
        let depth = depths.get(&id).copied().unwrap_or(0);

        if depth >= PROXIMITY_DEPTH {
            continue;
        }

        let next_depth = depth + 1;

        let mut neighbors = BTreeSet::new();

        if let Some(incoming) = graph.incoming.get(&id) {
            neighbors.extend(incoming.iter().copied());
        }

        if let Some(outgoing) = graph.outgoing.get(&id) {
            neighbors.extend(outgoing.iter().copied());
        }

        for neighbor in neighbors {
            let should_update = match depths.get(&neighbor) {
                None => true,

                Some(existing) => next_depth < *existing,
            };

            if should_update {
                depths.insert(neighbor, next_depth);

                queue.push_back(neighbor);
            }
        }
    }

    let mut scores = ScoreMap::new();

    for (id, depth) in depths {
        let Some(symbol) = graph.nodes.get(&id) else {
            continue;
        };

        let weight = match depth {
            0 => 1.00,
            1 => 0.60,
            2 => 0.30,
            _ => 0.0,
        };

        *scores.entry(symbol.path.clone()).or_default() += weight;
    }

    rank_scores(scores)
}

fn rank_scores(scores: ScoreMap) -> RankMap {
    let mut ranked: Vec<(String, f64)> = scores.into_iter().collect();

    ranked.sort_by(|left, right| {
        right
            .1
            .partial_cmp(&left.1)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.0.cmp(&right.0))
    });

    ranked
        .into_iter()
        .enumerate()
        .map(|(index, (path, _))| (path, index + 1))
        .collect()
}

fn rrf_score(rank: Option<usize>, weight: f64) -> f64 {
    rank.map_or(0.0, |value| weight / (RRF_K + value as f64))
}

fn path_penalty(path: &str, task: &str) -> f64 {
    let path = path.replace('\\', "/").to_lowercase();

    let segments: Vec<&str> = path.split('/').collect();

    let tokens = task_tokens(task);

    let test_intent = contains_any(
        &tokens,
        &[
            "test", "tests", "testing", "spec", "fixture", "snapshot", "pytest", "vitest", "jest",
        ],
    );

    let docs_intent = contains_any(&tokens, &["docs", "documentation", "readme", "guide"]);

    let mut penalty = 1.0_f64;

    if contains_any_segment(&segments, &["generated", "dist", "build", "vendor"]) {
        penalty = penalty.min(0.35);
    }

    if contains_any_segment(&segments, &["fixtures", "snapshots"]) {
        penalty = penalty.min(0.50);
    }

    if !docs_intent && contains_any_segment(&segments, &["docs", "examples"]) {
        penalty = penalty.min(0.60);
    }

    if !test_intent && contains_any_segment(&segments, &["test", "tests", "__tests__"]) {
        penalty = penalty.min(0.75);
    }

    penalty
}

fn contains_any(values: &[String], needles: &[&str]) -> bool {
    values.iter().any(|value| needles.contains(&value.as_str()))
}

fn contains_any_segment(values: &[&str], needles: &[&str]) -> bool {
    values.iter().any(|value| needles.contains(value))
}

fn sort_context_files(files: &mut Vec<ContextFile>, limit: usize) {
    files.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.path.cmp(&right.path))
    });

    files.truncate(limit);
}

fn task_tokens(task: &str) -> Vec<String> {
    task.split(|character: char| !character.is_alphanumeric() && character != '_')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_lowercase)
        .collect()
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

    for term in task_tokens(task) {
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
