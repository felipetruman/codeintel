use std::{
    cmp::Ordering,
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs::File,
    io::BufReader,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use crate::structural::{StructuralIndex, SymbolDefinition};

pub const GRAPH_FILE: &str = "graph.json";

const DAMPING: f64 = 0.85;
const MAX_ITERATIONS: usize = 100;
const TOLERANCE: f64 = 1e-10;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphIndex {
    pub root: String,

    pub nodes: BTreeMap<u64, SymbolDefinition>,

    pub outgoing: BTreeMap<u64, BTreeSet<u64>>,

    pub incoming: BTreeMap<u64, BTreeSet<u64>>,

    pub pagerank: BTreeMap<u64, f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RankedSymbol {
    pub symbol: SymbolDefinition,
    pub pagerank: f64,
    pub incoming: usize,
    pub outgoing: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactSymbol {
    pub symbol: SymbolDefinition,
    pub depth: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImpactView {
    pub query: String,
    pub definitions: Vec<SymbolDefinition>,
    pub direct_callers: Vec<SymbolDefinition>,
    pub impacted: Vec<ImpactSymbol>,
    pub blast_radius: usize,
    pub max_depth: usize,
    pub pagerank: f64,
}

impl GraphIndex {
    pub fn build(structural: &StructuralIndex) -> Self {
        let nodes: BTreeMap<u64, SymbolDefinition> = structural
            .definitions
            .iter()
            .map(|symbol| (symbol.id, symbol.clone()))
            .collect();

        let mut outgoing: BTreeMap<u64, BTreeSet<u64>> = BTreeMap::new();

        let mut incoming: BTreeMap<u64, BTreeSet<u64>> = BTreeMap::new();

        for id in nodes.keys() {
            outgoing.entry(*id).or_default();

            incoming.entry(*id).or_default();
        }

        for reference in &structural.references {
            let (Some(owner), Some(target)) = (reference.owner, reference.target) else {
                continue;
            };

            if !nodes.contains_key(&owner) || !nodes.contains_key(&target) {
                continue;
            }

            outgoing.entry(owner).or_default().insert(target);

            incoming.entry(target).or_default().insert(owner);
        }

        let pagerank = calculate_pagerank(&nodes, &outgoing, &incoming);

        Self {
            root: structural.root.clone(),
            nodes,
            outgoing,
            incoming,
            pagerank,
        }
    }

    pub fn rebuild(root: &Path, structural: &StructuralIndex) -> Result<Self> {
        let graph = Self::build(structural);

        graph.save(root)?;

        Ok(graph)
    }

    pub fn ensure(root: &Path, structural: &StructuralIndex) -> Result<Self> {
        let path = graph_path(root);

        if path.exists() {
            return Self::load(root);
        }

        Self::rebuild(root, structural)
    }

    pub fn save(&self, root: &Path) -> Result<()> {
        let path = graph_path(root);

        crate::persistence::atomic_write_json(&path, self)
    }

    pub fn load(root: &Path) -> Result<Self> {
        let path = graph_path(root);

        let file = File::open(&path).with_context(|| format!("cannot open {}", path.display()))?;

        serde_json::from_reader(BufReader::new(file))
            .with_context(|| format!("cannot decode {}", path.display()))
    }

    pub fn ranked_symbols(&self, limit: usize) -> Vec<RankedSymbol> {
        let mut result: Vec<RankedSymbol> = self
            .nodes
            .values()
            .map(|symbol| RankedSymbol {
                symbol: symbol.clone(),

                pagerank: self.pagerank.get(&symbol.id).copied().unwrap_or(0.0),

                incoming: self
                    .incoming
                    .get(&symbol.id)
                    .map(BTreeSet::len)
                    .unwrap_or(0),

                outgoing: self
                    .outgoing
                    .get(&symbol.id)
                    .map(BTreeSet::len)
                    .unwrap_or(0),
            })
            .collect();

        result.sort_by(|left, right| {
            right
                .pagerank
                .partial_cmp(&left.pagerank)
                .unwrap_or(Ordering::Equal)
                .then_with(|| left.symbol.name.cmp(&right.symbol.name))
        });

        result.truncate(limit);

        result
    }

    pub fn impact_symbol(&self, name: &str, max_depth: usize) -> ImpactView {
        let definitions: Vec<SymbolDefinition> = self
            .nodes
            .values()
            .filter(|symbol| symbol.name == name || symbol.name.eq_ignore_ascii_case(name))
            .cloned()
            .collect();

        let target_ids: BTreeSet<u64> = definitions.iter().map(|symbol| symbol.id).collect();

        let mut direct_ids = BTreeSet::new();

        for target in &target_ids {
            if let Some(callers) = self.incoming.get(target) {
                direct_ids.extend(callers.iter().copied());
            }
        }

        for target in &target_ids {
            direct_ids.remove(target);
        }

        let direct_callers: Vec<SymbolDefinition> = direct_ids
            .iter()
            .filter_map(|id| self.nodes.get(id).cloned())
            .collect();

        let mut visited = target_ids.clone();

        let mut queue = VecDeque::new();

        for id in &direct_ids {
            queue.push_back((*id, 1_usize));
        }

        let mut impacted = Vec::new();

        while let Some((id, depth)) = queue.pop_front() {
            if depth > max_depth {
                continue;
            }

            if !visited.insert(id) {
                continue;
            }

            if let Some(symbol) = self.nodes.get(&id) {
                impacted.push(ImpactSymbol {
                    symbol: symbol.clone(),
                    depth,
                });
            }

            if depth == max_depth {
                continue;
            }

            if let Some(callers) = self.incoming.get(&id) {
                for caller in callers {
                    queue.push_back((*caller, depth + 1));
                }
            }
        }

        impacted.sort_by(|left, right| {
            left.depth
                .cmp(&right.depth)
                .then_with(|| left.symbol.name.cmp(&right.symbol.name))
        });

        let pagerank = target_ids
            .iter()
            .filter_map(|id| self.pagerank.get(id).copied())
            .fold(0.0_f64, f64::max);

        ImpactView {
            query: name.to_string(),

            definitions,

            direct_callers,

            blast_radius: impacted.len(),

            impacted,

            max_depth,

            pagerank,
        }
    }
}

pub fn graph_path(root: &Path) -> PathBuf {
    root.join(".codeintel").join(GRAPH_FILE)
}

fn calculate_pagerank(
    nodes: &BTreeMap<u64, SymbolDefinition>,

    outgoing: &BTreeMap<u64, BTreeSet<u64>>,

    incoming: &BTreeMap<u64, BTreeSet<u64>>,
) -> BTreeMap<u64, f64> {
    let count = nodes.len();

    if count == 0 {
        return BTreeMap::new();
    }

    let n = count as f64;

    let initial = 1.0 / n;

    let mut rank: BTreeMap<u64, f64> = nodes.keys().map(|id| (*id, initial)).collect();

    for _ in 0..MAX_ITERATIONS {
        let sink_mass: f64 = nodes
            .keys()
            .filter(|id| outgoing.get(id).is_none_or(BTreeSet::is_empty))
            .map(|id| rank.get(id).copied().unwrap_or(0.0))
            .sum();

        let base = (1.0 - DAMPING) / n;

        let sink_share = DAMPING * sink_mass / n;

        let mut next = BTreeMap::new();

        for id in nodes.keys() {
            let mut score = base + sink_share;

            if let Some(sources) = incoming.get(id) {
                for source in sources {
                    let out_degree = outgoing.get(source).map(BTreeSet::len).unwrap_or(0);

                    if out_degree == 0 {
                        continue;
                    }

                    score += DAMPING * rank.get(source).copied().unwrap_or(0.0) / out_degree as f64;
                }
            }

            next.insert(*id, score);
        }

        let delta: f64 = nodes
            .keys()
            .map(|id| {
                (next.get(id).copied().unwrap_or(0.0) - rank.get(id).copied().unwrap_or(0.0)).abs()
            })
            .sum();

        rank = next;

        if delta < TOLERANCE {
            break;
        }
    }

    let total: f64 = rank.values().sum();

    if total > 0.0 {
        for value in rank.values_mut() {
            *value /= total;
        }
    }

    rank
}
