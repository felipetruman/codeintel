from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Literal

from benchmarks.agent.manifests import (
    BenchmarkTask,
)
from benchmarks.agent.models import (
    BenchmarkResult,
    TokenUsage,
)
from benchmarks.agent.process import (
    ProcessResult,
    run_process,
)


Operation = Literal[
    "search",
    "context",
    "symbol",
    "impact",
]


def _dedupe(
    values: list[str],
) -> list[str]:
    return list(dict.fromkeys(values))


def _normalize_path(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]

    return path


def _symbol_name(
    value: Any,
) -> str | None:
    if not isinstance(value, dict):
        return None

    name = value.get("name")

    if isinstance(name, str):
        return name

    return None


def _symbol_path(
    value: Any,
) -> str | None:
    if not isinstance(value, dict):
        return None

    path = value.get("path")

    if isinstance(path, str):
        return _normalize_path(path)

    return None


class CodeIntelRunner:
    name = "codeintel"

    def __init__(
        self,
        binary: str = "codeintel",
        mode: Literal[
            "cold",
            "warm",
        ] = "warm",
        timeout_seconds: float = 30,
    ) -> None:
        if mode not in {
            "cold",
            "warm",
        }:
            raise ValueError(
                f"unsupported CodeIntel mode: {mode}"
            )

        self.binary = binary
        self.mode = mode
        self.timeout_seconds = (
            timeout_seconds
        )

    def _prepare(
        self,
        repo: Path,
    ) -> ProcessResult | None:
        state = repo / ".codeintel"

        if self.mode == "cold":
            shutil.rmtree(
                state,
                ignore_errors=True,
            )
            return None

        return run_process(
            [
                self.binary,
                "index",
                str(repo),
            ],
            cwd=repo,
            timeout_seconds=self.timeout_seconds,
        )

    def _argv(
        self,
        operation: Operation,
        text: str,
        repo: Path,
    ) -> list[str]:
        if operation == "search":
            return [
                self.binary,
                "search",
                text,
                str(repo),
                "--limit",
                "50",
            ]

        if operation == "context":
            return [
                self.binary,
                "context",
                text,
                str(repo),
                "--limit",
                "20",
            ]

        if operation == "symbol":
            return [
                self.binary,
                "symbol",
                text,
                str(repo),
            ]

        if operation == "impact":
            return [
                self.binary,
                "impact",
                text,
                str(repo),
                "--depth",
                "8",
            ]

        raise ValueError(
            f"unsupported operation: {operation}"
        )

    def _failed_prepare(
        self,
        task_id: str,
        preparation: ProcessResult,
        operation: Operation,
    ) -> BenchmarkResult:
        return BenchmarkResult(
            runner=self.name,
            task_id=task_id,
            success=False,
            duration_ms=preparation.duration_ms,
            tokens=TokenUsage(),
            stdout=preparation.stdout,
            stderr=preparation.stderr,
            exit_code=preparation.exit_code,
            metadata={
                "operation": operation,
                "mode": self.mode,
                "stage": "index",
            },
        )

    def run_operation(
        self,
        operation: Operation,
        text: str,
        repo: Path,
        task_id: str,
    ) -> BenchmarkResult:
        repo = Path(repo)

        preparation = self._prepare(
            repo
        )

        if (
            preparation is not None
            and (
                preparation.timed_out
                or preparation.exit_code != 0
            )
        ):
            return self._failed_prepare(
                task_id,
                preparation,
                operation,
            )

        process = run_process(
            self._argv(
                operation,
                text,
                repo,
            ),
            cwd=repo,
            timeout_seconds=self.timeout_seconds,
        )

        metadata: dict[str, Any] = {
            "operation": operation,
            "mode": self.mode,
        }

        if preparation is not None:
            metadata[
                "index_duration_ms"
            ] = preparation.duration_ms

        if (
            process.timed_out
            or process.exit_code != 0
        ):
            return BenchmarkResult(
                runner=self.name,
                task_id=task_id,
                success=False,
                duration_ms=process.duration_ms,
                tokens=TokenUsage(),
                stdout=process.stdout,
                stderr=process.stderr,
                exit_code=process.exit_code,
                metadata=metadata,
            )

        try:
            payload = json.loads(
                process.stdout
            )
        except json.JSONDecodeError as error:
            metadata["parse_error"] = str(
                error
            )

            return BenchmarkResult(
                runner=self.name,
                task_id=task_id,
                success=False,
                duration_ms=process.duration_ms,
                tokens=TokenUsage(),
                stdout=process.stdout,
                stderr=process.stderr,
                exit_code=process.exit_code,
                metadata=metadata,
            )

        files: list[str] = []
        symbols: list[str] = []

        if operation == "search":
            if not isinstance(
                payload,
                list,
            ):
                metadata[
                    "parse_error"
                ] = "search payload must be a list"
            else:
                for hit in payload:
                    if not isinstance(
                        hit,
                        dict,
                    ):
                        continue

                    path = hit.get(
                        "path"
                    )

                    if isinstance(
                        path,
                        str,
                    ):
                        files.append(
                            _normalize_path(
                                path
                            )
                        )

                metadata[
                    "candidate_count"
                ] = len(payload)

        elif operation == "context":
            if not isinstance(
                payload,
                dict,
            ):
                metadata[
                    "parse_error"
                ] = "context payload must be an object"
            else:
                context_files = payload.get(
                    "files",
                    [],
                )

                if isinstance(
                    context_files,
                    list,
                ):
                    for item in context_files:
                        if not isinstance(
                            item,
                            dict,
                        ):
                            continue

                        path = item.get(
                            "path"
                        )

                        if isinstance(
                            path,
                            str,
                        ):
                            files.append(
                                _normalize_path(
                                    path
                                )
                            )

        elif operation == "symbol":
            if not isinstance(
                payload,
                dict,
            ):
                metadata[
                    "parse_error"
                ] = "symbol payload must be an object"
            else:
                groups = [
                    "definitions",
                    "callers",
                    "callees",
                ]

                for group in groups:
                    values = payload.get(
                        group,
                        [],
                    )

                    if not isinstance(
                        values,
                        list,
                    ):
                        continue

                    for value in values:
                        name = _symbol_name(
                            value
                        )
                        path = _symbol_path(
                            value
                        )

                        if name is not None:
                            symbols.append(
                                name
                            )

                        if path is not None:
                            files.append(
                                path
                            )

                callers = payload.get(
                    "callers",
                    [],
                )

                callees = payload.get(
                    "callees",
                    [],
                )

                metadata[
                    "callers"
                ] = [
                    name
                    for item in callers
                    if (
                        name := _symbol_name(
                            item
                        )
                    )
                ]

                metadata[
                    "callees"
                ] = [
                    name
                    for item in callees
                    if (
                        name := _symbol_name(
                            item
                        )
                    )
                ]

                references = payload.get(
                    "references",
                    [],
                )

                metadata[
                    "references_count"
                ] = (
                    len(references)
                    if isinstance(
                        references,
                        list,
                    )
                    else 0
                )

        elif operation == "impact":
            if not isinstance(
                payload,
                dict,
            ):
                metadata[
                    "parse_error"
                ] = "impact payload must be an object"
            else:
                definitions = payload.get(
                    "definitions",
                    [],
                )
                direct = payload.get(
                    "direct_callers",
                    [],
                )
                impacted = payload.get(
                    "impacted",
                    [],
                )

                for value in definitions:
                    name = _symbol_name(
                        value
                    )
                    path = _symbol_path(
                        value
                    )

                    if name is not None:
                        symbols.append(
                            name
                        )

                    if path is not None:
                        files.append(
                            path
                        )

                direct_names = []

                for value in direct:
                    name = _symbol_name(
                        value
                    )
                    path = _symbol_path(
                        value
                    )

                    if name is not None:
                        direct_names.append(
                            name
                        )
                        symbols.append(
                            name
                        )

                    if path is not None:
                        files.append(
                            path
                        )

                impacted_names = []

                for value in impacted:
                    if not isinstance(
                        value,
                        dict,
                    ):
                        continue

                    symbol = value.get(
                        "symbol"
                    )

                    name = _symbol_name(
                        symbol
                    )
                    path = _symbol_path(
                        symbol
                    )

                    if name is not None:
                        impacted_names.append(
                            name
                        )
                        symbols.append(
                            name
                        )

                    if path is not None:
                        files.append(
                            path
                        )

                metadata[
                    "direct_callers"
                ] = direct_names

                metadata[
                    "impacted"
                ] = impacted_names

                metadata[
                    "blast_radius"
                ] = payload.get(
                    "blast_radius"
                )

                metadata[
                    "pagerank"
                ] = payload.get(
                    "pagerank"
                )

        success = (
            "parse_error"
            not in metadata
        )

        return BenchmarkResult(
            runner=self.name,
            task_id=task_id,
            success=success,
            duration_ms=process.duration_ms,
            files=_dedupe(files),
            symbols=_dedupe(symbols),
            tool_calls=[],
            tokens=TokenUsage(),
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.exit_code,
            metadata=metadata,
        )

    def run(
        self,
        task: BenchmarkTask,
        repo: Path,
    ) -> BenchmarkResult:
        if task.type == "locate-symbol":
            operation: Operation = (
                "search"
            )
            text = task.query

        elif task.type in {
            "relevant-files",
            "change-planning",
        }:
            operation = "context"
            text = task.prompt

        elif task.type == "impact-analysis":
            operation = "impact"
            text = task.query

        else:
            raise ValueError(
                f"unsupported task type: {task.type}"
            )

        return self.run_operation(
            operation=operation,
            text=text,
            repo=repo,
            task_id=task.id,
        )
