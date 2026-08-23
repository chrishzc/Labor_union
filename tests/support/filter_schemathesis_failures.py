"""
File: filter_schemathesis_failures.py
Description: 將 Schemathesis failure 與無 case 執行錯誤白名單化、去重去敏，只輸出 Agent 所需摘要。
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any


MAX_INPUT_BYTES = 100 * 1024 * 1024
MAX_LINE_BYTES = 5 * 1024 * 1024
OPERATION_PATTERN = re.compile(
    r"^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|TRACE) ([A-Za-z0-9_./{}:-]{1,240})$"
)
SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
CONTENT_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+$")
SECONDARY_FAILURE_TYPES = frozenset({"RejectedPositiveData"})
TOKEN_ESTIMATE_DIVISOR = 4


def _artifact_metrics(path: Path, utf8_characters: int | None = None) -> dict[str, int]:
    payload = path.read_bytes()
    byte_count = len(payload)
    character_count = (
        utf8_characters if utf8_characters is not None else len(payload.decode("utf-8"))
    )
    return {
        "utf8_bytes": byte_count,
        "unicode_characters": character_count,
        "estimated_tokens": (byte_count + TOKEN_ESTIMATE_DIVISOR - 1)
        // TOKEN_ESTIMATE_DIVISOR,
    }


def _safe_name(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and SAFE_NAME_PATTERN.fullmatch(value) else fallback


def _operation(label: Any) -> tuple[str, str, str]:
    if not isinstance(label, str):
        return "UNKNOWN", "[REDACTED_PATH]", "UNKNOWN [REDACTED_PATH]"
    match = OPERATION_PATTERN.fullmatch(label)
    if match is None:
        return "UNKNOWN", "[REDACTED_PATH]", "UNKNOWN [REDACTED_PATH]"
    method, path_template = match.groups()
    return method, path_template, f"{method} {path_template}"


def _content_type(headers: Any) -> str | None:
    if not isinstance(headers, dict):
        return None
    value: Any = None
    for name, candidate in headers.items():
        if isinstance(name, str) and name.lower() == "content-type":
            value = candidate
            break
    if isinstance(value, list) and value:
        value = value[0]
    if not isinstance(value, str):
        return None
    normalized = value.split(";", 1)[0].strip().lower()
    return normalized if CONTENT_TYPE_PATTERN.fullmatch(normalized) else "[REDACTED_CONTENT_TYPE]"


def _interaction_response(recorder: dict[str, Any], case_id: str) -> tuple[int | None, str | None]:
    interactions = recorder.get("interactions")
    if not isinstance(interactions, dict):
        return None, None
    case_interactions = interactions.get(case_id)
    if isinstance(case_interactions, dict):
        interaction = case_interactions
    elif isinstance(case_interactions, list) and case_interactions:
        interaction = case_interactions[-1]
    else:
        return None, None
    if not isinstance(interaction, dict) or not isinstance(interaction.get("response"), dict):
        return None, None
    response = interaction["response"]
    status_code = response.get("status_code")
    safe_status = status_code if isinstance(status_code, int) and 100 <= status_code <= 599 else None
    return safe_status, _content_type(response.get("headers"))


def _suggested_category(check_name: str) -> str:
    return {
        "not_a_server_error": "implementation_error",
        "response_schema_conformance": "response_schema",
        "content_type_conformance": "openapi_content_type",
        "status_code_conformance": "openapi_status",
    }.get(check_name, "needs_agent_triage")


def _failed_checks(recorder: dict[str, Any], case_id: str) -> list[tuple[str, str]]:
    checks_by_case = recorder.get("checks")
    if not isinstance(checks_by_case, dict) or not isinstance(checks_by_case.get(case_id), list):
        return []
    failures: list[tuple[str, str]] = []
    for check in checks_by_case[case_id]:
        if not isinstance(check, dict) or check.get("status") not in {"failure", "error"}:
            continue
        check_name = _safe_name(check.get("name"), "unknown_check")
        failure_info = check.get("failure_info")
        failure = failure_info.get("failure") if isinstance(failure_info, dict) else None
        failure_type = _safe_name(
            failure.get("type") if isinstance(failure, dict) else None,
            "UnknownFailure",
        )
        failures.append((check_name, failure_type))
    if len(failures) > 1:
        failures = [item for item in failures if item[1] not in SECONDARY_FAILURE_TYPES]
    return failures


def _scenario_records(event: dict[str, Any]) -> tuple[str, list[dict[str, Any]], int]:
    scenario = event.get("ScenarioFinished")
    if not isinstance(scenario, dict):
        return "not_scenario", [], 0
    status = scenario.get("status")
    if status not in {"failure", "error"}:
        return "success", [], 0
    recorder = scenario.get("recorder")
    if not isinstance(recorder, dict):
        raise ValueError("failed ScenarioFinished event is missing recorder")
    cases = recorder.get("cases")
    if not isinstance(cases, dict):
        method, path_template, operation = _operation(recorder.get("label"))
        return (
            "failure",
            [
                {
                    "schema_version": 1,
                    "source": "schemathesis",
                    "operation": operation,
                    "method": method,
                    "path_template": path_template,
                    "failure_type": "ScenarioExecutionError",
                    "check_names": ["scenario_execution"],
                    "suggested_category": "needs_agent_triage",
                    "http_status": None,
                    "response_content_type": None,
                    "occurrences": 1,
                }
            ],
            0,
        )

    method, path_template, operation = _operation(recorder.get("label"))
    records: list[dict[str, Any]] = []
    suppressed = 0
    for case_id in cases:
        if not isinstance(case_id, str):
            raise ValueError("Schemathesis case identity must be a string")
        status_code, content_type = _interaction_response(recorder, case_id)
        all_failures = _failed_checks(recorder, case_id)
        raw_failed_check_count = 0
        checks_by_case = recorder.get("checks")
        if isinstance(checks_by_case, dict) and isinstance(checks_by_case.get(case_id), list):
            raw_failed_check_count = sum(
                1
                for check in checks_by_case[case_id]
                if isinstance(check, dict) and check.get("status") in {"failure", "error"}
            )
        suppressed += max(0, raw_failed_check_count - len(all_failures))
        for check_name, failure_type in all_failures:
            records.append(
                {
                    "schema_version": 1,
                    "source": "schemathesis",
                    "operation": operation,
                    "method": method,
                    "path_template": path_template,
                    "failure_type": failure_type,
                    "check_names": [check_name],
                    "suggested_category": _suggested_category(check_name),
                    "http_status": status_code,
                    "response_content_type": content_type,
                    "occurrences": 1,
                }
            )
    return "failure", records, suppressed


def _validate_paths(input_path: Path, output_path: Path, summary_path: Path) -> tuple[Path, Path, Path]:
    resolved_input = input_path.resolve(strict=True)
    resolved_output = output_path.resolve(strict=False)
    resolved_summary = summary_path.resolve(strict=False)
    if not resolved_input.is_file():
        raise ValueError("input NDJSON must be a file")
    if resolved_input.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("input NDJSON exceeds the 100 MiB safety limit")
    if resolved_output.parent != resolved_input.parent or resolved_summary.parent != resolved_input.parent:
        raise ValueError("input, output, and summary must share one run directory")
    if len({resolved_input, resolved_output, resolved_summary}) != 3:
        raise ValueError("input, output, and summary paths must be distinct")
    return resolved_input, resolved_output, resolved_summary


def _atomic_write_json_lines(path: Path, records: list[dict[str, Any]]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
        temporary_path = Path(stream.name)
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            stream.write("\n")
    os.replace(temporary_path, path)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
        temporary_path = Path(stream.name)
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary_path, path)


def filter_report(input_path: Path, output_path: Path, summary_path: Path) -> dict[str, Any]:
    started_at = time.perf_counter()
    resolved_input, resolved_output, resolved_summary = _validate_paths(
        input_path,
        output_path,
        summary_path,
    )
    counters: Counter[str] = Counter()
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    raw_utf8_characters = 0

    with resolved_input.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            counters["raw_events"] += 1
            if len(raw_line) > MAX_LINE_BYTES:
                raise ValueError(f"NDJSON line {line_number} exceeds the 5 MiB safety limit")
            try:
                decoded_line = raw_line.decode("utf-8")
                raw_utf8_characters += len(decoded_line)
                event = json.loads(decoded_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"NDJSON line {line_number} is invalid") from error
            if not isinstance(event, dict):
                raise ValueError(f"NDJSON line {line_number} must be an object")
            scenario_kind, records, suppressed = _scenario_records(event)
            counters[scenario_kind] += 1
            counters["suppressed_secondary_failures"] += suppressed
            for record in records:
                key = (
                    record["operation"],
                    record["failure_type"],
                    record["http_status"],
                    record["response_content_type"],
                )
                existing = unique.get(key)
                if existing is None:
                    unique[key] = record
                    continue
                existing["occurrences"] += 1
                existing["check_names"] = sorted(
                    set(existing["check_names"]) | set(record["check_names"])
                )

    records = sorted(
        unique.values(),
        key=lambda item: (
            item["operation"],
            item["failure_type"],
            item["http_status"] or 0,
        ),
    )
    _atomic_write_json_lines(resolved_output, records)
    raw_metrics = _artifact_metrics(resolved_input, raw_utf8_characters)
    agent_metrics = _artifact_metrics(resolved_output)
    estimated_tokens_saved = max(
        0,
        raw_metrics["estimated_tokens"] - agent_metrics["estimated_tokens"],
    )
    reduction_percent = (
        round(estimated_tokens_saved * 100 / raw_metrics["estimated_tokens"], 2)
        if raw_metrics["estimated_tokens"]
        else 0.0
    )
    summary = {
        "schema_version": 1,
        "raw_event_count": counters["raw_events"],
        "successful_scenarios_discarded": counters["success"],
        "failed_scenarios": counters["failure"],
        "suppressed_secondary_failures": counters["suppressed_secondary_failures"],
        "unique_failures": len(records),
        "agent_input": resolved_output.name,
        "privacy_policy": "allowlisted metadata only; request values, headers, bodies, timestamps, and case ids omitted",
        "context_metrics": {
            "measurement": "heuristic_estimate_ceiling_utf8_bytes_divided_by_4",
            "scope": "artifact input only; excludes Codex system prompts, tool calls, output, cache, and billing usage",
            "raw_report_baseline": raw_metrics,
            "filtered_agent_input": agent_metrics,
            "estimated_tokens_saved": estimated_tokens_saved,
            "estimated_token_reduction_percent": reduction_percent,
        },
        "filter_elapsed_milliseconds": round((time.perf_counter() - started_at) * 1000, 3),
    }
    _atomic_write_json(resolved_summary, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    arguments = parser.parse_args()
    summary = filter_report(arguments.input, arguments.output, arguments.summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
