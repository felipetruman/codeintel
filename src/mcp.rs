use std::{
    io::{self, BufRead, Write},
    path::PathBuf,
};

use anyhow::{Context, Result, bail};
use serde_json::{Value, json};

use crate::{
    context::build_repository_context, graph::GraphIndex, index::CodeIndex, search::search_index,
    structural::StructuralIndex, workspace::resolve_root,
};

pub fn serve(default_path: Option<PathBuf>) -> Result<()> {
    let stdin = io::stdin();
    let mut stdout = io::stdout();

    for line in stdin.lock().lines() {
        let line = line.context("failed reading MCP stdin")?;

        if line.trim().is_empty() {
            continue;
        }

        let request: Value = serde_json::from_str(&line).context("invalid JSON-RPC request")?;

        let method = request
            .get("method")
            .and_then(Value::as_str)
            .unwrap_or_default();

        if method.starts_with("notifications/") {
            continue;
        }

        let id = request.get("id").cloned().unwrap_or(Value::Null);

        let response = match method {
            "initialize" => {
                let protocol = request
                    .pointer("/params/protocolVersion")
                    .and_then(Value::as_str)
                    .unwrap_or("2025-06-18");

                success(
                    id,
                    json!({
                        "protocolVersion": protocol,
                        "capabilities": {
                            "tools": {
                                "listChanged": false
                            }
                        },
                        "serverInfo": {
                            "name": "codeintel",
                            "version": env!("CARGO_PKG_VERSION")
                        },
                        "instructions":
                            "Use code_context for repository discovery, \
                             code_search for lexical lookup, \
                             code_symbol for structural inspection, \
                             and code_impact before modifying important shared symbols."
                    }),
                )
            }

            "ping" => success(id, json!({})),

            "tools/list" => success(id, tools_list()),

            "tools/call" => {
                let params = request.get("params").cloned().unwrap_or_else(|| json!({}));

                match call_tool(&params, default_path.clone()) {
                    Ok(result) => success(id, result),

                    Err(error) => failure(id, -32602, &format!("{error:#}")),
                }
            }

            _ => failure(id, -32601, &format!("method not found: {method}")),
        };

        writeln!(stdout, "{}", serde_json::to_string(&response)?)?;

        stdout.flush()?;
    }

    Ok(())
}

fn tools_list() -> Value {
    json!({
        "tools": [
            {
                "name": "code_search",
                "description":
                    "Search repository source text using the persistent lexical/trigram index.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string"
                        },
                        "path": {
                            "type": "string"
                        },
                        "regex": {
                            "type": "boolean",
                            "default": false
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": 50
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": false
                },
                "annotations": {
                    "readOnlyHint": true,
                    "destructiveHint": false
                }
            },
            {
                "name": "code_context",
                "description":
                    "Return hybrid-ranked repository files using lexical, structural, graph and proximity signals.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string"
                        },
                        "path": {
                            "type": "string"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 10
                        }
                    },
                    "required": ["task"],
                    "additionalProperties": false
                },
                "annotations": {
                    "readOnlyHint": true,
                    "destructiveHint": false
                }
            },
            {
                "name": "code_symbol",
                "description":
                    "Inspect a Tree-sitter structural symbol. Returns definitions, callers, callees and references.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string"
                        },
                        "path": {
                            "type": "string"
                        }
                    },
                    "required": ["name"],
                    "additionalProperties": false
                },
                "annotations": {
                    "readOnlyHint": true,
                    "destructiveHint": false
                }
            },
            {
                "name": "code_impact",
                "description":
                    "Analyze graph impact for a symbol. Returns PageRank, direct callers, transitive callers and blast radius.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string"
                        },
                        "path": {
                            "type": "string"
                        },
                        "max_depth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 20,
                            "default": 4
                        }
                    },
                    "required": ["name"],
                    "additionalProperties": false
                },
                "annotations": {
                    "readOnlyHint": true,
                    "destructiveHint": false
                }
            }
        ]
    })
}

fn call_tool(params: &Value, default_path: Option<PathBuf>) -> Result<Value> {
    let name = params
        .get("name")
        .and_then(Value::as_str)
        .context("tools/call missing tool name")?;

    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!({}));

    let requested_path = arguments
        .get("path")
        .and_then(Value::as_str)
        .map(PathBuf::from)
        .or(default_path);

    let root = resolve_root(requested_path)?;

    let lexical = CodeIndex::ensure(&root)?;

    let text = match name {
        "code_search" => {
            let query = arguments
                .get("query")
                .and_then(Value::as_str)
                .context("code_search requires query")?;

            let regex = arguments
                .get("regex")
                .and_then(Value::as_bool)
                .unwrap_or(false);

            let limit = arguments
                .get("limit")
                .and_then(Value::as_u64)
                .unwrap_or(50)
                .clamp(1, 200) as usize;

            let hits = search_index(&lexical, query, regex, limit)?;

            serde_json::to_string_pretty(&hits)?
        }

        "code_context" => {
            let task = arguments
                .get("task")
                .and_then(Value::as_str)
                .context("code_context requires task")?;

            let limit = arguments
                .get("limit")
                .and_then(Value::as_u64)
                .unwrap_or(10)
                .clamp(1, 50) as usize;

            let bundle = build_repository_context(&root, &lexical, task, limit)?;

            serde_json::to_string_pretty(&bundle)?
        }

        "code_symbol" => {
            let symbol_name = arguments
                .get("name")
                .and_then(Value::as_str)
                .context("code_symbol requires name")?;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let view = structural.lookup_symbol(symbol_name);

            serde_json::to_string_pretty(&view)?
        }

        "code_impact" => {
            let symbol_name = arguments
                .get("name")
                .and_then(Value::as_str)
                .context("code_impact requires name")?;

            let max_depth = arguments
                .get("max_depth")
                .and_then(Value::as_u64)
                .unwrap_or(4)
                .clamp(1, 20) as usize;

            let structural = StructuralIndex::ensure(&root, &lexical.files)?;

            let graph = GraphIndex::ensure(&root, &structural)?;

            let impact = graph.impact_symbol(symbol_name, max_depth);

            serde_json::to_string_pretty(&impact)?
        }

        _ => {
            bail!("unknown CodeIntel tool: {name}")
        }
    };

    Ok(json!({
        "content": [
            {
                "type": "text",
                "text": text
            }
        ],
        "isError": false
    }))
}

fn success(id: Value, result: Value) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "result": result
    })
}

fn failure(id: Value, code: i64, message: &str) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "error": {
            "code": code,
            "message": message
        }
    })
}
