from benchmarks.agent.process import ProcessOptions


from benchmarks.agent.runners.agent_sandbox import agent_sandbox
from benchmarks.agent.process import run_process


def test_sandbox_blocks_host_reads_and_repository_writes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source").write_text("original")
    secret = tmp_path / "outside"
    secret.write_text("host-only")
    script = (
        "from pathlib import Path; "
        f"assert not Path({str(secret)!r}).exists(); "
        f'p=Path({str(repo / "source")!r}); '
        'assert p.read_text()=="original"; '
        'p.write_text("modified")'
    )
    with agent_sandbox(["/usr/bin/python3", "-c", script], repo, None) as (argv, env):
        result = run_process(
            argv, repo, 5, options=ProcessOptions(env=env, inherit_env=False)
        )
    assert result.exit_code != 0
    assert "Read-only file system" in result.stderr
    assert (repo / "source").read_text() == "original"


def test_sandbox_does_not_inherit_user_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("BENCHMARK_SECRET_TEST", "do-not-inherit")
    with agent_sandbox(["/usr/bin/python3", "-c", "print(1)"], tmp_path, None) as (
        argv,
        env,
    ):
        assert "BENCHMARK_SECRET_TEST" not in env
        assert env["HOME"] == "/home/benchmark"
        assert "--unshare-pid" in argv
        assert "--die-with-parent" in argv


def test_only_enhanced_arm_can_reach_codeintel(tmp_path):
    from pathlib import Path

    binary = Path(__file__).resolve().parents[3] / "target/release/codeintel"
    assert binary.is_file()
    (tmp_path / "payment.py").write_text("def payment():\n    return True\n")
    baseline = [
        "/usr/bin/python3",
        "-c",
        f"from pathlib import Path; assert not Path({str(binary)!r}).exists()",
    ]
    with agent_sandbox(baseline, tmp_path, None) as (argv, env):
        result = run_process(
            argv, tmp_path, 5, options=ProcessOptions(env=env, inherit_env=False)
        )
    assert result.exit_code == 0, result.stderr
    enhanced = [
        "/usr/bin/python3",
        "-c",
        f'import subprocess; subprocess.run([{str(binary)!r},"index",{str(tmp_path)!r}],check=True)',
    ]
    with agent_sandbox(enhanced, tmp_path, str(binary)) as (argv, env):
        result = run_process(
            argv, tmp_path, 5, options=ProcessOptions(env=env, inherit_env=False)
        )
    assert result.exit_code == 0, result.stderr
    assert "indexed 1 files" in result.stdout
    assert (tmp_path / "payment.py").read_text() == "def payment():\n    return True\n"


def test_auth_environment_is_provider_specific(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-value")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-value")
    with agent_sandbox(["/usr/bin/python3"], tmp_path, None, "codex") as (_, env):
        assert "ANTHROPIC_API_KEY" not in env
        assert env["OPENAI_API_KEY"] == "test-openai-value"
