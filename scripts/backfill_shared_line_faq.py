"""Audit legacy LINE FAQ evidence and backfill confirmed publication references."""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

from pymysql.err import IntegrityError

from domains.knowledge_retrieval.qa_catalog import QA_SOURCE_PREFIX, decode_governed_qa
from domains.line.faq_chat_layout import FaqCategory, FaqLayout, FaqQuestionLink, decode_layout
from domains.line.legacy_faq import (
    LEGACY_FAQ_CATEGORIES as LAYOUT_META,
    LEGACY_FAQ_GROUPS as LEGACY_GROUPS,
    LEGACY_FAQ_POLICY_LABELS as POLICY_LABELS,
)
from infrastructure.mysql.knowledge_retrieval_repository import MySqlKnowledgeRetrievalRepository
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from infrastructure.mysql.shared_line_faq_cutover import READY_CONTRACT, READY_KEY, shared_faq_ready_fingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.knowledge_retrieval.contracts import IngestKnowledgeSourceCommand
from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_contracts import LineConfigurationCommandOutcome
from subsystems.line.faq_chat_layout import (
    FAQ_CHAT_LAYOUT_KIND, append_faq_layout_audit, build_initial_faq_layout_command,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "document/line/AI客服QA題庫.jsonl"


@dataclass(frozen=True)
class Pointer:
    item_id: int
    qa_id: str
    version: int | None
    aliases: tuple[str, ...]
    category_id: str | None
    changes: tuple[str, ...]


def _json(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _publication(root, revisions, events):
    pointer = root["published_version"]
    state, version = root["state"], root["version"]
    by_version = {row["item_version"]: row for row in revisions}
    transitions = [row for row in revisions if row["event_type"] in {"published", "retired"}]
    if pointer is not None and (
        state == "retired"
        or not transitions
        or transitions[-1]["event_type"] != "published"
        or transitions[-1]["item_version"] != pointer
        or (state == "published" and pointer != version)
    ):
        raise ValueError("invalid_existing_publication_pointer")
    if state == "retired":
        return None
    if state == "published":
        snapshot = by_version.get(version)
        if snapshot is None or snapshot["event_type"] != "published":
            raise ValueError("published_revision_missing")
        return snapshot
    if not transitions or transitions[-1]["event_type"] == "retired":
        return None
    publication = transitions[-1]
    for number in range(publication["item_version"], version + 1):
        revision = by_version.get(number)
        event = events.get(number)
        if revision is None or event is None or (
            revision["event_type"], revision["source_digest"]
        ) != (event["event_type"], _json(event["snapshot_json"]).get("content_digest")):
            raise ValueError("incomplete_publication_event_chain")
    if by_version[version]["source_digest"] != root["content_digest"]:
        raise ValueError("current_revision_digest_mismatch")
    return publication


def _historical_source_proven(root, publication, versions, events, content):
    if all(publication[field] is not None for field in ("title", "source_uri", "source_trust_tier")):
        return True
    ingest = next((
        row for row in reversed(versions)
        if row["item_version"] <= publication["item_version"] and row["event_type"] == "ingested"
    ), None)
    if ingest is None or ingest["source_digest"] != publication["source_digest"]:
        return False
    event = events.get(ingest["item_version"])
    if event is None or not event["command_fingerprint"]:
        return False
    command = IngestKnowledgeSourceCommand(
        root["source_identity"], "internal_policy", content.question, ingest["content"],
        content.source_ref, ActorContext(str(event["actor_admin_user_id"])),
        IdempotencyKey(event["idempotency_key"]), CorrelationId(event["correlation_id"]),
    )
    # Before expected_version was added, the durable receipt hashed this representation.
    canonical = repr(command).removesuffix(", expected_version=None)") + ")"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() == event["command_fingerprint"]


def _read_rows(cursor, lock):
    cursor.execute(
        "SELECT id, source_identity, version, published_version, state, title, source_uri, "
        "source_trust_tier, content_digest, faq_legacy_aliases, faq_legacy_category_id, "
        "faq_legacy_category_version FROM knowledge_items "
        "WHERE source_identity LIKE %s ORDER BY id" + (" FOR UPDATE" if lock else ""),
        (QA_SOURCE_PREFIX + "%",),
    )
    roots = cursor.fetchall()
    cursor.execute(
        "SELECT v.* FROM knowledge_item_versions v JOIN knowledge_items i ON i.id=v.item_id "
        "WHERE i.source_identity LIKE %s ORDER BY v.item_id,v.item_version",
        (QA_SOURCE_PREFIX + "%",),
    )
    revisions = defaultdict(list)
    for row in cursor.fetchall():
        revisions[row["item_id"]].append(row)
    cursor.execute(
        "SELECT e.knowledge_item_id,e.after_version,e.event_type,e.snapshot_json,e.actor_admin_user_id,"
        "e.idempotency_key,e.correlation_id,r.command_fingerprint "
        "FROM knowledge_item_events e JOIN knowledge_items i ON i.id=e.knowledge_item_id "
        "LEFT JOIN knowledge_apply_receipts r ON r.idempotency_key=e.idempotency_key "
        "WHERE i.source_identity LIKE %s ORDER BY e.id",
        (QA_SOURCE_PREFIX + "%",),
    )
    events = defaultdict(dict)
    for row in cursor.fetchall():
        events[row["knowledge_item_id"]][row["after_version"]] = row
    return roots, revisions, events


def build_plan(rows, legacy, reviewed, known_categories):
    roots, revisions, events = rows
    issues = []
    categories = {**LEGACY_GROUPS, **reviewed.get("categories", {})}
    explicit_aliases = reviewed.get("legacy_questions", {})
    aliases_by_qa = defaultdict(set)
    evidence = defaultdict(set)
    official = {}
    resolved = []
    known_ids = {row["source_identity"].removeprefix(QA_SOURCE_PREFIX) for row in roots}
    enabled = [row for row in legacy if row.get("enabled") is True and row.get("answer", "").strip()]
    for row in enabled:
        qa_id = row["id"]
        if qa_id not in known_ids:
            issues.append({"code": "legacy_question_missing", "qa_id": qa_id})
            continue
        aliases_by_qa[qa_id].update((row["question"], *row.get("aliases", [])))
    for text, qa_id in explicit_aliases.items():
        if qa_id not in known_ids or not text.strip():
            issues.append({"code": "reviewed_alias_target_invalid", "qa_id": qa_id})
        else:
            aliases_by_qa[qa_id].add(text.strip())

    for root in roots:
        item_id = root["id"]
        qa_id = root["source_identity"].removeprefix(QA_SOURCE_PREFIX)
        try:
            if (root["faq_legacy_category_id"] is None) != (root["faq_legacy_category_version"] is None):
                raise ValueError("saved_legacy_category_incomplete")
            versions = revisions[item_id]
            publication = _publication(root, versions, events[item_id])
            texts = aliases_by_qa[qa_id]
            for row in versions:
                if row["event_type"] == "published":
                    old = decode_governed_qa(row["content"])
                    if old is None or old.qa_id != qa_id:
                        raise ValueError("published_item_content_invalid")
                    texts.update((old.question, *old.aliases))
            saved_aliases = _json(root["faq_legacy_aliases"])
            if saved_aliases is not None and (
                not isinstance(saved_aliases, list) or not all(isinstance(value, str) for value in saved_aliases)
            ):
                raise ValueError("saved_legacy_aliases_invalid")
            if saved_aliases is not None and not aliases_by_qa[qa_id].issubset(saved_aliases):
                # New official questions use their versioned exact aliases. Only
                # imported legacy records must be represented in a prior backfill.
                imported = {text for row in enabled if row["id"] == qa_id for text in (row["question"], *row.get("aliases", []))}
                imported.update(text for text, target in explicit_aliases.items() if target == qa_id)
                if not imported.issubset(saved_aliases):
                    raise ValueError("saved_legacy_aliases_conflict")
            for text in texts | set(saved_aliases or ()):
                evidence[text.strip()].add(qa_id)

            category_id = None
            if publication is not None:
                content = decode_governed_qa(publication["content"])
                if content is None or not content.answer.strip() or content.qa_id != qa_id:
                    raise ValueError("published_item_content_invalid")
                version = publication["item_version"]
                title = publication["title"] or content.question
                uri = publication["source_uri"] or content.source_ref
                trust = publication["source_trust_tier"] or "internal_policy"
                if version == root["version"] and (
                    title, uri, trust, publication["source_digest"]
                ) != (root["title"], root["source_uri"], root["source_trust_tier"], root["content_digest"]):
                    raise ValueError("published_source_metadata_conflict")
                if version != root["version"] and not _historical_source_proven(
                    root, publication, versions, events[item_id], content,
                ):
                    raise ValueError("published_source_metadata_unproven")
                category_id = content.category_id or categories.get(content.category)
                if category_id not in known_categories:
                    issues.append({"code": "published_category_unmapped", "qa_id": qa_id, "category": content.category})
                    category_id = None
                if (
                    root["faq_legacy_category_version"] == version
                    and root["faq_legacy_category_id"] != category_id
                ):
                    raise ValueError("saved_legacy_category_conflict")
                if content.category_id:
                    category_id = None
                official[qa_id] = content
            else:
                version = None
            changes = []
            if version is not None and root["published_version"] is None:
                changes.append("published_version")
            if texts and saved_aliases is None:
                changes.append("faq_legacy_aliases")
            if category_id is not None and root["faq_legacy_category_id"] is None:
                changes.append("faq_legacy_category")
            resolved.append(Pointer(item_id, qa_id, version, tuple(sorted(texts)), category_id, tuple(changes)))
        except ValueError as error:
            issues.append({"code": str(error), "qa_id": qa_id})

    for text, ids in sorted(evidence.items()):
        if len(ids) > 1:
            issues.append({"code": "legacy_text_ambiguous", "qa_ids": sorted(ids), "text": text})
    for text in POLICY_LABELS:
        if len(evidence[text]) != 1 or next(iter(evidence[text]), None) not in official:
            issues.append({"code": "legacy_policy_unresolved", "text": text})

    cards = []
    for category_id, (name, title, description, fallback) in LAYOUT_META.items():
        previous = list(dict.fromkeys(
            row["question"] for row in enabled if LEGACY_GROUPS.get(row["category"]) == category_id
        ))[:4] or list(fallback)
        links = []
        for text in previous:
            match = evidence[text]
            qa_id = next(iter(match)) if len(match) == 1 else None
            if qa_id not in official:
                issues.append({"code": "legacy_card_question_unavailable", "category_id": category_id, "qa_ids": sorted(match), "text": text})
            elif qa_id not in {link.qa_id for link in links}:
                links.append(FaqQuestionLink(qa_id, text if len(text) <= 18 else text[:17] + "…"))
        cards.append(FaqCategory(category_id, name, title, description, "🤖 找不到答案？試試 AI 智慧問答", tuple(links)))
    return resolved, FaqLayout(tuple(cards)), issues


def _fingerprint(payload):
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backfill(
    connection, legacy, reviewed, *, actor, correlation_id, apply=False, expected_plan_fingerprint=None,
):
    with LineMySqlUnitOfWork(connection) as unit:
        with connection.cursor() as cursor:
            if not apply:
                connection.rollback()
                cursor.execute("START TRANSACTION READ ONLY")
            snapshot = unit.configurations.get(FAQ_CHAT_LAYOUT_KIND)
            current_categories = set(LAYOUT_META)
            if snapshot.revision.value:
                current = json.loads(snapshot.definition_json)
                current_categories.update(row["category_id"] for row in current["draft_layout"]["categories"])
            rows = _read_rows(cursor, apply)
            resolved, layout, issues = build_plan(rows, legacy, reviewed, current_categories)
            report = {
                "mode": "apply" if apply else "audit",
                "issues": issues,
                "differences": [{"qa_id": row.qa_id, "publication_version": row.version, "fields": row.changes}
                                for row in resolved if row.changes],
                "legacy_cards": [{"category_id": card.category_id, "qa_ids": [link.qa_id for link in card.questions]} for card in layout.categories],
                "layout_revision": snapshot.revision.value,
                "plan_fingerprint": _fingerprint({
                    "reviewed": reviewed, "revisions": [row["version"] for row in rows[0]],
                    "items": [asdict(row) for row in resolved], "layout": asdict(layout),
                    "layout_revision": snapshot.revision.value, "issues": issues,
                }),
                "updated_items": 0,
            }
            if expected_plan_fingerprint is not None and report["plan_fingerprint"] != expected_plan_fingerprint:
                raise ValueError("faq_cutover_reviewed_plan_changed")
            if not apply or issues:
                return report
            for row in resolved:
                if not row.changes:
                    continue
                cursor.execute(
                    "UPDATE knowledge_items SET published_version=COALESCE(published_version,%s), "
                    "faq_legacy_aliases=COALESCE(faq_legacy_aliases,%s), "
                    "faq_legacy_category_id=COALESCE(faq_legacy_category_id,%s), "
                    "faq_legacy_category_version=COALESCE(faq_legacy_category_version,%s), "
                    "updated_at=updated_at "
                    "WHERE id=%s AND ((published_version IS NULL AND %s IS NOT NULL) "
                    "OR (faq_legacy_aliases IS NULL AND %s IS NOT NULL) "
                    "OR (faq_legacy_category_id IS NULL AND %s IS NOT NULL))",
                    (
                        row.version, json.dumps(row.aliases, ensure_ascii=False) if row.aliases else None,
                        row.category_id, row.version if row.category_id else None, row.item_id,
                        row.version, bool(row.aliases) or None, row.category_id,
                    ),
                )
                report["updated_items"] += cursor.rowcount
            if snapshot.revision.value == 0:
                command = build_initial_faq_layout_command(layout, actor, correlation_id)
                result = unit.configurations.apply(command)
                if result.outcome is LineConfigurationCommandOutcome.CREATED:
                    append_faq_layout_audit(unit, command)
                report["layout_revision"] = 1
            unit.commit()
        return report


def verify_cutover(connection, legacy, reviewed):
    """Verify the committed backfill through the actual published projection."""
    with LineMySqlUnitOfWork(connection) as unit:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION READ ONLY")
            snapshot = unit.configurations.get(FAQ_CHAT_LAYOUT_KIND)
            if not snapshot.revision.value:
                raise ValueError("faq_cutover_published_layout_missing")
            definition = json.loads(snapshot.definition_json)
            published_revision = definition.get("published_revision")
            if (
                definition.get("schema_version") != 1
                or type(published_revision) is not int
                or not 0 < published_revision <= snapshot.revision.value
                or definition.get("published_layout") is None
            ):
                raise ValueError("faq_cutover_published_layout_missing")
            published_layout = decode_layout(definition["published_layout"])
            category_ids = set(LAYOUT_META) | {
                card.category_id for card in decode_layout(definition["draft_layout"]).categories
            }
            rows = _read_rows(cursor, False)
            resolved, expected_layout, issues = build_plan(rows, legacy, reviewed, category_ids)
            if issues:
                raise ValueError(f"faq_cutover_readback:{issues[0]['code']}")
            if any(row.changes for row in resolved):
                raise ValueError("faq_cutover_readback_missing_values")

            current = {card.category_id: card for card in published_layout.categories}
            for expected in expected_layout.categories:
                card = current.get(expected.category_id)
                expected_ids = {link.qa_id for link in expected.questions}
                if not card or not expected_ids or not expected_ids <= {link.qa_id for link in card.questions}:
                    raise ValueError("faq_cutover_required_card_mismatch")

            knowledge = MySqlKnowledgeRetrievalRepository(connection)
            catalog = PublishedFaqCatalog(lambda: nullcontext(SimpleNamespace(knowledge=knowledge)))
            published = {}
            for row in resolved:
                observed = catalog.get(row.qa_id)
                if observed is None:
                    if row.version is not None:
                        raise ValueError("faq_cutover_official_version_missing")
                    continue
                if observed.source_version != row.version or (row.category_id and observed.category_id != row.category_id):
                    raise ValueError("faq_cutover_official_version_mismatch")
                published[row.qa_id] = observed

            legacy_targets = {
                text.strip(): row["id"]
                for row in legacy if row.get("enabled") is True and row.get("answer", "").strip()
                for text in (row["question"], *row.get("aliases", []))
            }
            legacy_targets.update({text.strip(): qa_id for text, qa_id in reviewed.get("legacy_questions", {}).items()})
            for text, qa_id in legacy_targets.items():
                expected = (published[qa_id],) if qa_id in published else ()
                if catalog.match_legacy_text(text) != expected:
                    raise ValueError("faq_cutover_legacy_alias_mismatch")
            for card in published_layout.categories:
                if any(link.qa_id not in published for link in card.questions):
                    raise ValueError("faq_cutover_card_reference_unavailable")

            dataset = {
                "official": [asdict(published[qa_id]) for qa_id in sorted(published)],
                "legacy_targets": legacy_targets,
                "published_revision": published_revision,
                "layout": asdict(published_layout),
            }
            return {
                "dataset_fingerprint": _fingerprint(dataset),
                "official_count": len(published),
                "legacy_alias_count": len(legacy_targets),
                "published_revision": published_revision,
                "published_category_count": len(published_layout.categories),
            }


def assert_cutover_ready(connection, *, dataset_fingerprint):
    if not dataset_fingerprint or shared_faq_ready_fingerprint(connection) != dataset_fingerprint:
        raise ValueError("faq_cutover_ready_receipt_mismatch")


def record_cutover_ready(connection, *, dataset_fingerprint):
    """Append a gate receipt after the controlled owner has verified the candidate."""
    if not isinstance(dataset_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", dataset_fingerprint):
        raise ValueError("faq_cutover_dataset_fingerprint_invalid")
    payload = json.dumps({"contract": READY_CONTRACT, "dataset_fingerprint": dataset_fingerprint})
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO knowledge_apply_receipts (idempotency_key,command_fingerprint,receipt_json) "
                "VALUES (%s,%s,%s)",
                (READY_KEY, dataset_fingerprint, payload),
            )
    except IntegrityError as error:
        if error.args[0] != 1062:
            raise
    assert_cutover_ready(connection, dataset_fingerprint=dataset_fingerprint)


def initialize_empty_faq_reader(connection):
    """The fresh initializer calls this only after verifying the empty target schema."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM knowledge_items LIMIT 1")
        if cursor.fetchone() is not None:
            raise ValueError("faq_cutover_fresh_knowledge_not_empty")
        cursor.execute("SELECT revision FROM line_configuration_current WHERE configuration_kind='faq_chat_layout'")
        if cursor.fetchone() is not None:
            raise ValueError("faq_cutover_fresh_layout_not_empty")
    fingerprint = _fingerprint({"fresh": True, "official": [], "published_revision": None})
    record_cutover_ready(connection, dataset_fingerprint=fingerprint)
    return fingerprint


def main():
    import pymysql

    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--reviewed-mapping", type=Path,
        help="UTF-8 JSON with categories (old category to stable ID) and legacy_questions (exact text to QA ID)",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--actor")
    args = parser.parse_args()
    database = DB_CONFIG["database"]
    if args.apply and (
        DB_CONFIG["host"] not in {"localhost", "127.0.0.1", "::1"}
        or not re.fullmatch(r"lu_test_[a-z0-9_]+", database)
        or args.confirm_database != database or not args.actor
    ):
        parser.error("apply requires a confirmed local lu_test_* database and an audit actor")
    legacy = [json.loads(line) for line in args.catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
    reviewed = json.loads(args.reviewed_mapping.read_text(encoding="utf-8")) if args.reviewed_mapping else {}
    actor = ActorContext(args.actor or "faq-legacy-audit", (LineCapability.CONFIG_MANAGE.value,))
    try:
        with pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor) as connection:
            report = backfill(connection, legacy, reviewed, actor=actor, correlation_id=CorrelationId("faq-legacy-backfill:v1"), apply=args.apply)
    except pymysql.MySQLError as error:
        parser.exit(1, f"faq_legacy_database_unavailable: {type(error).__name__}\n")
    print(json.dumps(report, ensure_ascii=False))
    return 2 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
