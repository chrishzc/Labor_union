"""Audit legacy LINE FAQ evidence and backfill confirmed publication references."""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re

from domains.knowledge_retrieval.qa_catalog import QA_SOURCE_PREFIX, decode_governed_qa
from domains.line.faq_chat_layout import FaqCategory, FaqLayout, FaqQuestionLink
from infrastructure.mysql.line_unit_of_work import LineMySqlUnitOfWork
from shared_kernel.identities import ActorContext, CorrelationId
from subsystems.line.capabilities import LineCapability
from subsystems.line.configuration_contracts import LineConfigurationCommandOutcome
from subsystems.line.faq_chat_layout import (
    FAQ_CHAT_LAYOUT_KIND, append_faq_layout_audit, build_initial_faq_layout_command,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "document/line/AI客服QA題庫.jsonl"
LAYOUT_META = {
    "service_flow": (
        "服務流程", "📋 服務流程 常見問題",
        "整理月嫂媒合、申請流程與服務預約相關問題，點選題目即可查看說明：",
        ("服務流程如何進行？", "如果和月嫂合作不適合，可以更換月嫂嗎？",
         "服務天數或每日時數可以延長嗎？", "實際生產日期和預產期不同時可以改期嗎？"),
    ),
    "payment_subsidy": (
        "收費與補助", "💰 費用與補助 常見問題",
        "整理到宅月子費用收費、補助申請與退費相關問題，點選題目即可查看說明：",
        ("一般市民（最高40小時）", "補助市民（最高120小時）",
         "符合補助退還條件後，大約什麼時候會收到款項？", "如果提前取消服務，退費或補收如何處理？"),
    ),
}
LEGACY_GROUPS = {
    **dict.fromkeys(("服務流程", "服務登記", "月嫂媒合", "服務排程", "請假代班", "餐飲服務"), "service_flow"),
    **dict.fromkeys(("費用", "收費與補助", "補助", "社福補助"), "payment_subsidy"),
}
POLICY_LABELS = LAYOUT_META["payment_subsidy"][3][:2]


@dataclass(frozen=True)
class Pointer:
    item_id: int
    version: int | None
    aliases: tuple[str, ...]
    category_id: str | None


def _json(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _publication(root, revisions, events):
    pointer = root["published_version"]
    state, version = root["state"], root["version"]
    by_version = {row["item_version"]: row for row in revisions}
    if pointer is not None:
        publication = by_version.get(pointer)
        if state == "retired" or publication is None or publication["event_type"] != "published":
            raise ValueError("invalid_existing_publication_pointer")
        return publication
    if state == "retired":
        return None
    if state == "published":
        snapshot = by_version.get(version)
        if snapshot is None or snapshot["event_type"] != "published":
            raise ValueError("published_revision_missing")
        return snapshot
    transitions = [row for row in revisions if row["event_type"] in {"published", "retired"}]
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
        "SELECT e.knowledge_item_id,e.after_version,e.event_type,e.snapshot_json "
        "FROM knowledge_item_events e JOIN knowledge_items i ON i.id=e.knowledge_item_id "
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
            resolved.append(Pointer(item_id, version, tuple(sorted(texts)), category_id))
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


def backfill(connection, legacy, reviewed, *, actor, correlation_id, apply=False):
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
            resolved, layout, issues = build_plan(_read_rows(cursor, apply), legacy, reviewed, current_categories)
            report = {
                "mode": "apply" if apply else "audit",
                "issues": issues,
                "publication_candidates": sum(row.version is not None for row in resolved),
                "legacy_cards": [{"category_id": card.category_id, "qa_ids": [link.qa_id for link in card.questions]} for card in layout.categories],
                "layout_revision": snapshot.revision.value,
                "updated_items": 0,
            }
            if not apply or issues:
                return report
            for row in resolved:
                cursor.execute(
                    "UPDATE knowledge_items SET published_version=COALESCE(published_version,%s), "
                    "faq_legacy_aliases=COALESCE(faq_legacy_aliases,%s), "
                    "faq_legacy_category_id=COALESCE(faq_legacy_category_id,%s), "
                    "faq_legacy_category_version=COALESCE(faq_legacy_category_version,%s) "
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


def main():
    import pymysql

    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--reviewed-mapping", type=Path)
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
