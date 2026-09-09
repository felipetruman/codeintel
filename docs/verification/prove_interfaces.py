"""Exercise every CLI command and MCP tool against the real release binary."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
BIN = Path(os.environ.get("CODEINTEL_BINARY", ROOT / "target/release/codeintel"))
VERSION = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]
SOURCE = "def leaf():\n    return 42\n\ndef middle():\n    return leaf()\n\ndef outer():\n    return middle()\n"
TOOLS = {"code_search", "code_context", "code_symbol", "code_impact"}


def request(method, params=None):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


class InterfaceProof(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="codeintel-interfaces-")
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.source = self.repo / "sample.py"
        self.source.write_text(SOURCE)

    def run_cli(self, *args):
        return subprocess.run(
            [str(BIN), *map(str, args)],
            cwd=self.repo,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def cli(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def value(self, *args):
        return json.loads(self.cli(*args))

    def rpc(self, messages):
        result = subprocess.run(
            [str(BIN), "mcp", str(self.repo)],
            input="\n".join(json.dumps(item) for item in messages) + "\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def tool(self, name, arguments):
        response = self.rpc(
            [request("tools/call", {"name": name, "arguments": arguments})]
        )[0]
        self.assertNotIn("error", response)
        self.assertFalse(response["result"]["isError"])
        return json.loads(response["result"]["content"][0]["text"])

    def test_cli_help_and_version(self):
        self.assertEqual(self.cli("--version").strip(), f"codeintel {VERSION}")
        commands = {
            "index",
            "search",
            "context",
            "symbols",
            "symbol",
            "graph",
            "impact",
            "serve",
            "mcp",
            "doctor",
        }
        help_text = self.cli("--help")
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, help_text)
                self.assertIn("Usage:", self.cli(command, "--help"))

    def test_cli_index_reuses_unchanged_source(self):
        self.assertIn("indexed 1 files, 3 definitions", self.cli("index"))
        self.assertIn("reused=1", self.cli("index", self.repo))
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_cli_search_literal_regex_limit_and_empty(self):
        self.assertEqual(len(self.value("search", "leaf")), 2)
        self.assertEqual(len(self.value("search", "leaf", "--limit", "1")), 1)
        self.assertEqual(len(self.value("search", "def (leaf|middle)", "--regex")), 2)
        self.assertEqual(self.value("search", "absent_token"), [])

    def test_cli_context(self):
        files = self.value("context", "change leaf", "--limit", "1")["files"]
        self.assertEqual([item["path"] for item in files], ["sample.py"])

    def test_cli_symbols(self):
        symbols = self.value("symbols", "--query", "leaf", "--limit", "1")
        self.assertEqual([item["name"] for item in symbols], ["leaf"])

    def test_cli_symbol(self):
        value = self.value("symbol", "leaf")
        self.assertEqual([item["name"] for item in value["callers"]], ["middle"])
        self.assertEqual(self.value("symbol", "absent_token")["definitions"], [])

    def test_cli_graph(self):
        graph = self.value("graph", "--limit", "2")
        self.assertEqual(len(graph), 2)
        self.assertEqual(graph[0]["symbol"]["name"], "leaf")
        self.assertGreater(graph[0]["pagerank"], graph[1]["pagerank"])

    def test_cli_impact_depth(self):
        self.assertEqual(self.value("impact", "leaf")["blast_radius"], 2)
        self.assertEqual(
            self.value("impact", "leaf", "--depth", "1")["blast_radius"], 1
        )

    def test_cli_doctor_is_read_only(self):
        missing = {item["name"]: item["status"] for item in self.value("doctor")}
        self.assertEqual(missing["manifest"], "missing")
        self.assertFalse((self.repo / ".codeintel").exists())
        self.cli("index")
        state = self.repo / ".codeintel"
        before = {p.name: p.read_bytes() for p in state.iterdir()}
        fresh = {item["name"]: item["status"] for item in self.value("doctor")}
        self.assertEqual(fresh["index_freshness"], "fresh")
        self.assertEqual(before, {p.name: p.read_bytes() for p in state.iterdir()})

    def wait_for_symbol(self, name):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.persisted_symbol_exists(name):
                return
            time.sleep(0.05)
        self.fail(f"watcher did not persist symbol {name}")

    def persisted_symbol_exists(self, name):
        try:
            data = json.loads((self.repo / ".codeintel/structural.json").read_text())
            return name in {item["name"] for item in data["definitions"]}
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    def test_cli_serve_watches_edits(self):
        child = subprocess.Popen(
            [str(BIN), "serve", str(self.repo)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self.wait_for_symbol("leaf")
            self.source.write_text(SOURCE + "\ndef watched_added():\n    return 7\n")
            self.wait_for_symbol("watched_added")
            self.assertIsNone(child.poll())
        finally:
            child.kill()
            child.wait(timeout=5)

    def test_cli_rejects_bad_input(self):
        for args in [("search",), ("unknown-command",), ("search", "[", "--regex")]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr)

    def test_mcp_protocol_and_discovery(self):
        messages = [
            request("initialize", {"protocolVersion": "2025-06-18"}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request("ping"),
            request("tools/list"),
        ]
        replies = self.rpc(messages)
        self.assertEqual(len(replies), 3)
        self.assertEqual(replies[0]["result"]["serverInfo"]["version"], VERSION)
        self.assertEqual(replies[1]["result"], {})
        self.assertEqual(
            {tool["name"] for tool in replies[2]["result"]["tools"]}, TOOLS
        )

    def test_mcp_code_search(self):
        result = self.tool(
            "code_search", {"query": "leaf", "path": str(self.repo), "limit": 1}
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], "sample.py")
        regex = self.tool("code_search", {"query": "def (leaf|middle)", "regex": True})
        self.assertEqual(len(regex), 2)

    def test_mcp_code_context_refreshes(self):
        self.tool("code_context", {"task": "leaf"})
        (self.repo / "added.py").write_text("def newly_discovered():\n    return 77\n")
        result = self.tool("code_context", {"task": "newly_discovered", "limit": 1})
        self.assertEqual([item["path"] for item in result["files"]], ["added.py"])

    def test_mcp_code_symbol(self):
        result = self.tool("code_symbol", {"name": "middle"})
        self.assertEqual([item["name"] for item in result["definitions"]], ["middle"])
        self.assertEqual([item["name"] for item in result["callers"]], ["outer"])
        self.assertEqual([item["name"] for item in result["callees"]], ["leaf"])

    def test_mcp_code_impact_refreshes(self):
        result = self.tool("code_impact", {"name": "leaf", "max_depth": 1})
        self.assertEqual(result["blast_radius"], 1)
        self.source.write_text(SOURCE + "\ndef extra_caller():\n    return leaf()\n")
        refreshed = self.tool("code_impact", {"name": "leaf"})
        self.assertEqual(refreshed["blast_radius"], 3)

    def test_mcp_errors_do_not_stop_session(self):
        messages = [request("unknown-method")]
        messages.extend(
            request("tools/call", {"name": tool, "arguments": {}})
            for tool in sorted(TOOLS)
        )
        messages.append(request("tools/call", {"name": "unknown-tool"}))
        messages.append(request("ping"))
        replies = self.rpc(messages)
        self.assertEqual(replies[0]["error"]["code"], -32601)
        for reply in replies[1:-1]:
            self.assertEqual(reply["error"]["code"], -32602)
        self.assertEqual(replies[-1]["result"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
