"""Read-only verifier for UI-ANOM-REOPEN-001."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_TIMELINE = ["claim", "resolve", "reopen", "auto_resolve", "reopen"]


def verify(arguments) -> dict[str, object]:
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    from scripts.seed_validation_anomaly_scenario import (
        _application,
        _configure_scenario,
        _existing_projection,
        _timeline_actions,
    )

    DB_CONFIG.update({"host": arguments.host, "port": arguments.port, "user": arguments.user, "password": arguments.password, "database": arguments.database})
    _configure_scenario(
        arguments.case_no,
        date.fromisoformat(arguments.service_start),
        arguments.expected_service_days,
    )
    application, connection = _application()
    try:
        projection = _existing_projection(application)
        observed = None if projection is None else {
            "status": projection.workflow_status.value,
            "timeline_actions": _timeline_actions(application, projection),
        }
    finally:
        connection.close()
    checks = _checks(observed)
    return {"observed": observed, "checks": checks, "valid": all(item["passed"] for item in checks)}


def _checks(observed) -> list[dict[str, object]]:
    status = None if observed is None else observed["status"]
    timeline = None if observed is None else observed["timeline_actions"]
    return [
        _check("reopen_timeline", timeline, _TIMELINE),
        _check("active_root_reopens_alert", status, "open"),
    ]


def _check(check_id: str, observed: object, expected: object) -> dict[str, object]:
    return {"check_id": check_id, "expected": expected, "observed": observed, "passed": observed == expected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--case-no", default="DSV1-CASE-0001")
    parser.add_argument("--service-start", default="2026-08-01")
    parser.add_argument("--expected-service-days", type=int, default=5)
    result = verify(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
