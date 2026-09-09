from benchmarks.agent.models import BenchmarkResult, TokenUsage


def test_result_serializes_missing_tokens_as_null():
    result = BenchmarkResult(
        runner="rg",
        task_id="x",
        success=True,
        duration_ms=1.5,
        files=["src/a.rs"],
        symbols=[],
        tool_calls=[],
        tokens=TokenUsage(),
        stdout="",
        stderr="",
        exit_code=0,
        metadata={},
    )

    assert result.to_dict()["tokens"] == {
        "input": None,
        "output": None,
        "total": None,
    }


def test_token_total():
    assert (
        TokenUsage(
            input=100,
            output=20,
        ).total
        == 120
    )
