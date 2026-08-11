"""Safely upgrade the known legacy canonical Rich Menu defaults."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas.line_config import LineMenusConfig
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_application import LineConfigurationApplication

KNOWN_LEGACY_SHA256 = (
    "10fc62aca2d2a689e15eec622a34353d692b5e2eaba74357e6faaba1f2a9e422"
)
TARGET_PATH = ROOT / "config" / "line_menu.json"


# Kept cohesive so the fingerprint gate remains visibly adjacent to its only write path.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append the new canonical revision when the current revision is the known legacy value.",
    )
    arguments = parser.parse_args()
    target = _target_definition()
    target_json = canonical_line_payload_json(target)
    load_dotenv(ROOT / ".env")
    actor = _actor()
    application = LineConfigurationApplication(open_line_unit_of_work)
    current = application.get(LineConfigurationKind.RICH_MENUS, actor)
    current_hash = definition_sha256(current.definition_json)
    target_hash = definition_sha256(target_json)
    print(f"Current Rich Menu revision: {current.revision.value}")
    print(f"Current definition SHA-256: {current_hash}")
    if current_hash == target_hash:
        print("Canonical Rich Menu defaults already match the merge defaults.")
        return 0
    if current_hash != KNOWN_LEGACY_SHA256:
        print("Blocked: current Rich Menu revision is not the known legacy definition.")
        return 2
    if not arguments.apply:
        print("Eligible for upgrade; dry-run completed without a DB write.")
        return 0
    result = application.apply(
        kind=LineConfigurationKind.RICH_MENUS,
        expected_revision=current.revision,
        definition=target,
        actor=actor,
        reason="upgrade known legacy Rich Menu defaults to merge interface",
        idempotency_key=IdempotencyKey("line-menu-merge-defaults:20260811:v1"),
        correlation_id=CorrelationId("line-menu-merge-defaults:20260811:v1"),
    )
    print(f"Applied canonical Rich Menu revision {result.snapshot.revision.value}.")
    return 0


def definition_sha256(definition_json: str) -> str:
    return hashlib.sha256(definition_json.encode("utf-8")).hexdigest()


def _target_definition() -> dict[str, object]:
    raw = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    validated = LineMenusConfig.model_validate(raw)
    return validated.model_dump(mode="json")


def _actor() -> ActorContext:
    permissions = {
        LineCapability.CONFIG_READ.value,
        LineCapability.CONFIG_MANAGE.value,
    }
    return ActorContext(
        "system:line-menu-merge-default-upgrade",
        tuple(sorted(permissions)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
