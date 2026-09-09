from benchmarks.agent.process import ProcessOptions
from dataclasses import dataclass

"""Linux filesystem isolation shared by both real-agent A/B arms."""

from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile

from benchmarks.agent.process import run_process


@dataclass(frozen=True)
class AgentProcessOptions:
    codeintel_binary: str | None = None
    agent: str | None = None


SYSTEM_PATHS = (
    "/usr",
    "/bin",
    "/lib",
    "/lib64",
    "/etc/ssl",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
)
AUTH_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def _mount(source: Path, target: Path) -> list[str]:
    return ["--ro-bind", str(source), str(target)] if source.exists() else []


def _executable(value: str) -> Path:
    resolved = shutil.which(value)
    if resolved is None:
        raise ValueError(f"agent executable not available: {value}")
    return Path(resolved).resolve()


def _credentials(agent: str | None) -> list[str]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    sources = {
        "codex": (codex_home / "auth.json", Path("/home/benchmark/.codex/auth.json")),
        "claude": (
            home / ".claude" / ".credentials.json",
            Path("/home/benchmark/.claude/.credentials.json"),
        ),
    }
    return _mount(*sources[agent]) if agent in sources else []


def _project_config_masks(repo: Path) -> list[str]:
    return [
        arg
        for name in (".codex", ".claude")
        if (repo / name).is_dir()
        for arg in ("--tmpfs", str(repo / name))
    ]


def _agent_mounts(executable: Path) -> list[str]:
    args = _mount(executable, executable)
    if executable.name == "codex":
        helper = executable.parent / "codex-code-mode-host"
        args += _mount(helper, helper)
    return args


def _extra_inputs(argv: list[str]) -> list[str]:
    if "--output-schema" not in argv:
        return []
    schema = Path(argv[argv.index("--output-schema") + 1]).resolve()
    return _mount(schema, schema)


def _codeintel_mount(binary: str | None) -> list[str]:
    installed = shutil.which("codeintel")
    args = []
    if installed and str(Path(installed).resolve()).startswith("/usr/"):
        args += ["--ro-bind", "/dev/null", str(Path(installed).resolve())]
    if binary is not None:
        executable = _executable(binary)
        args += _mount(executable, executable)
    return args


def _environment(agent: str | None) -> dict[str, str]:
    keys = {"claude": ("ANTHROPIC_API_KEY",), "codex": ("OPENAI_API_KEY",)}
    auth = {key: os.environ[key] for key in keys.get(agent, ()) if key in os.environ}
    return {
        **auth,
        "HOME": "/home/benchmark",
        "CODEX_HOME": "/home/benchmark/.codex",
        "CLAUDE_CONFIG_DIR": "/home/benchmark/.claude",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "TMPDIR": "/tmp",
    }


@contextmanager
def agent_sandbox(
    argv: list[str], repo: Path, codeintel_binary: str | None, agent: str | None = None
):
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise ValueError("real agents require Linux bubblewrap filesystem isolation")
    executable = _executable(argv[0])
    repo = repo.resolve()
    # Both arms get the same empty, writable index mount. Source stays read-only.
    (repo / ".codeintel").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codeintel-agent-state-") as state:
        prefix = [
            bwrap,
            "--die-with-parent",
            "--new-session",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/home/benchmark/.codex",
            "--dir",
            "/home/benchmark/.claude",
        ]
        for path in SYSTEM_PATHS:
            prefix += _mount(Path(path), Path(path))
        prefix += _agent_mounts(executable)
        prefix += _mount(repo, repo)
        prefix += _project_config_masks(repo)
        prefix += ["--bind", state, str(repo / ".codeintel"), "--chdir", str(repo)]
        prefix += (
            _credentials(agent)
            + _extra_inputs(argv)
            + _codeintel_mount(codeintel_binary)
        )
        yield prefix + ["--", str(executable), *argv[1:]], _environment(agent)


def run_agent_process(
    argv, cwd, timeout_seconds, options: AgentProcessOptions | None = None
):
    options = options or AgentProcessOptions()
    codeintel_binary, agent = options.codeintel_binary, options.agent
    with agent_sandbox(argv, cwd, codeintel_binary, agent) as (isolated_argv, env):
        return run_process(
            isolated_argv,
            cwd,
            timeout_seconds,
            options=ProcessOptions(env=env, inherit_env=False),
        )
