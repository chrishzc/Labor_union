"""
File: rebuild_beclass_import_anomalies.py
Description: 有界重建 BeClass durable review 對應的 current anomaly projections。
"""

from __future__ import annotations

import argparse
import json

from infrastructure.mysql.beclass_import_review_anomaly_source import (
    project_beclass_import_review_page,
)
from infrastructure.mysql.mysql_adapter import get_connection


def rebuild_beclass_import_anomalies(*, limit: int = 100) -> dict[str, object]:
    connection = get_connection()
    try:
        result = project_beclass_import_review_page(
            connection,
            after_review_row_id=0,
            limit=limit,
        )
    finally:
        connection.close()
    return {
        "status": "projected",
        "projected_count": result.projected_count,
        "next_review_row_id": result.next_review_row_id,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild BeClass review current anomaly projections."
    )
    parser.add_argument("--limit", type=int, default=100)
    options = parser.parse_args(arguments)
    try:
        result = rebuild_beclass_import_anomalies(limit=options.limit)
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["rebuild_beclass_import_anomalies"]
