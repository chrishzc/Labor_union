"""Validate or seed canonical LINE configuration revisions from bootstrap JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domains.line.configuration import LineConfigurationKind
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.message_configuration import (
    validate_message_schedules,
    validate_message_templates,
)

CONFIG_FILES = {
    LineConfigurationKind.MESSAGE_TEMPLATES: ROOT / "config" / "message_templates.json",
    LineConfigurationKind.MESSAGE_SCHEDULES: ROOT / "config" / "message_schedules.json",
    LineConfigurationKind.RICH_MENUS: ROOT / "config" / "line_menu.json",
    LineConfigurationKind.LIFF: ROOT / "config" / "liff_settings.json",
    LineConfigurationKind.CUSTOMER_SERVICE: ROOT / "config" / "customer_service.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write only missing revision-0 LINE configuration into MySQL.",
    )
    arguments = parser.parse_args()
    definitions = _definitions()
    validate_message_templates(definitions[LineConfigurationKind.MESSAGE_TEMPLATES])
    validate_message_schedules(
        definitions[LineConfigurationKind.MESSAGE_SCHEDULES],
        definitions[LineConfigurationKind.MESSAGE_TEMPLATES],
    )
    if not arguments.apply:
        print("LINE configuration bootstrap JSON validation passed; no DB write performed.")
        return 0
    load_dotenv(ROOT / ".env")
    actor = ActorContext(
        "system:line-configuration-bootstrap",
        tuple(sorted({LineCapability.CONFIG_MANAGE.value})),
    )
    results = LineConfigurationApplication(open_line_unit_of_work).bootstrap_missing(
        definitions,
        actor,
        reason="initial canonical LINE configuration bootstrap",
        correlation_id=CorrelationId("line-config-bootstrap:v1"),
    )
    print(f"Applied {len(results)} missing canonical LINE configuration revision(s).")
    return 0


def _definitions() -> dict[LineConfigurationKind, dict[str, object]]:
    result = {}
    for kind, path in CONFIG_FILES.items():
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path} must contain a JSON object")
        result[kind] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
