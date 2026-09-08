"""Append the complete UI validation dataset to the integrated disposable schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_validation_dataset import DEFAULT_MANIFEST, require_dataset_database


_FINANCE_MANUAL_REVIEW_SCENARIO_ID = "foundation-finance-manual-review"


def seed(arguments) -> dict[str, object]:
    _configure_runtime_database(arguments)
    from scripts.seed_validation_beclass_review import (
        seed_open_review,
    )
    from scripts.seed_validation_dataset import seed_into_integrated_dataset
    from scripts.seed_validation_finance_manual_review import seed as seed_finance_review

    foundation = seed_into_integrated_dataset(arguments)
    beclass_open_review = seed_open_review()
    finance_review = seed_finance_review(_FINANCE_MANUAL_REVIEW_SCENARIO_ID)
    return {
        "database": arguments.database,
        "foundation": foundation,
        "beclass_open_review": beclass_open_review,
        "finance_manual_review": finance_review,
    }


def _configure_runtime_database(arguments) -> None:
    require_dataset_database(arguments.database)
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("validation dataset seed requires a development validation profile")
    settings = {
        "DB_HOST": arguments.host,
        "DB_PORT": str(arguments.port),
        "DB_USER": arguments.user,
        "DB_PASSWORD": arguments.password,
        "DB_DATABASE": arguments.database,
    }
    os.environ.update(settings)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    print(json.dumps(seed(parser.parse_args()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
