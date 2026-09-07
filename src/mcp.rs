use std::{
    io::{self, BufRead, Write},
    path::PathBuf,
};

use anyhow::{Context, Result, bail};
use serde_json::{Value, json};

use crate::{
    context::build_context, index::CodeIndex, search::search_index, workspace::resolve_root,
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
                let requested_protocol = request
                    .pointer("/params/protocolVersion")
                    .and_then(Value::as_str)
                    .unwrap_or("2025-06-18");

                success(
                    id,
                    json!({
                        "protocolVersion": requested_protocol,
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
                            "Use code_context before broad repository exploration. Use code_search for repository-wide search."
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
                "description": "Search repository source text using persistent lexical indexing.",
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
                }
            },
            {
                "name": "code_context",
                "description": "Return ranked files relevant to a coding task before broad repository exploration.",
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

    let index = CodeIndex::ensure(&root)?;

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

            let hits = search_index(&index, query, regex, limit)?;

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

            let bundle = build_context(&index, task, limit)?;

            serde_json::to_string_pretty(&bundle)?
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
