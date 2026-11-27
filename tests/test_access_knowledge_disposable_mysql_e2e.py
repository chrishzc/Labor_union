"""Durable business flow for equal-access sessions and reviewed cited knowledge."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from infrastructure.mysql.knowledge_retrieval_repository import query_published_knowledge
from infrastructure.mysql.knowledge_retrieval_unit_of_work import open_knowledge_retrieval_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.application import KnowledgeApplication
from subsystems.knowledge_retrieval.contracts import (
    IngestKnowledgeSourceCommand,
    PublishKnowledgeItemCommand,
    ReviewKnowledgeItemCommand,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires explicitly configured disposable MySQL")


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": DATABASE,
        "charset": "utf8mb4",
    })


def _seed_admin_users():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            run_identity = uuid4().hex[:12]
            usernames = {
                "author": f"knowledge_author_{run_identity}",
                "reviewer": f"knowledge_reviewer_{run_identity}",
            }
            cursor.executemany(
                "INSERT INTO admin_users (username,password_hash,display_name,role) VALUES (%s,%s,%s,%s)",
                [(usernames["author"], "unused", "內容作者", "line_agent"), (usernames["reviewer"], "unused", "內容覆核", "line_agent")],
            )
            placeholders = ",".join(["%s"] * len(usernames))
            cursor.execute(
                f"SELECT id,username FROM admin_users WHERE username IN ({placeholders})",
                tuple(usernames.values()),
            )
            ids_by_username = {row["username"]: int(row["id"]) for row in cursor.fetchall()}
            return {role: ids_by_username[username] for role, username in usernames.items()}
    finally:
        connection.commit()
        connection.close()


def test_equal_enabled_users_review_publish_and_retrieve_cited_knowledge():
    ids = _seed_admin_users()
    run_identity = uuid4().hex
    _seed_active_session(ids["author"])
    assert _session_is_active(ids["author"])
    application = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    author = ActorContext(str(ids["author"]))
    reviewer = ActorContext(str(ids["reviewer"]))
    source_uri = f"https://gov.example/subsidy-2026/{run_identity}"

    draft_id, created = application.ingest(IngestKnowledgeSourceCommand(
        source_identity=f"knowledge:subsidy-2026:{run_identity}",
        source_trust_tier="government_source",
        title=f"2026 補助資格 {run_identity}",
        content="補助資格需由行政以正式證明文件確認。",
        source_uri=source_uri,
        actor=author,
        idempotency_key=IdempotencyKey(f"knowledge-ingest-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-1"),
    ))
    assert created is True
    reviewed_version = application.review(ReviewKnowledgeItemCommand(
        item_id=draft_id,
        expected_version=ExpectedVersion(1),
        actor=reviewer,
        reason="覆核來源與適用日期",
        idempotency_key=IdempotencyKey(f"knowledge-review-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-2"),
    ))
    published_version = application.publish(PublishKnowledgeItemCommand(
        item_id=draft_id,
        expected_version=ExpectedVersion(2),
        actor=reviewer,
        reason="核准對外說明",
        idempotency_key=IdempotencyKey(f"knowledge-publish-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-3"),
    ))
    answer = query_published_knowledge("補助資格")

    assert reviewed_version == 2
    assert published_version == 3
    item = application.get_item(draft_id)
    assert item is not None
    assert item["lifecycle_status"] == "published"
    assert item["current_version"] == 3
    assert item["source_uri"] == source_uri
    assert answer is not None
    assert answer["authoritative"] is False
    assert answer["citations"][0]["source_uri"] == source_uri
    assert answer["citations"][0]["version"] == 3


def _seed_active_session(admin_user_id: int) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            session_token_hash = uuid4().hex + uuid4().hex
            cursor.execute(
                """INSERT INTO admin_sessions (
                    admin_user_id,session_token_hash,expires_at,absolute_expires_at,last_seen_at
                ) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 MINUTE),
                    DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 8 HOUR),UTC_TIMESTAMP(6))""",
                (admin_user_id, session_token_hash),
            )
        connection.commit()
    finally:
        connection.close()


def _session_is_active(admin_user_id: int) -> bool:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT revoked_at,expires_at FROM admin_sessions WHERE admin_user_id=%s",
                (admin_user_id,),
            )
            row = cursor.fetchone()
            return row["revoked_at"] is None and row["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None)
    finally:
        connection.close()


def test_faq_04_mysql_publication_and_receipt_rollback(monkeypatch):
    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from infrastructure.mysql.knowledge_retrieval_unit_of_work import KnowledgeRetrievalMySqlUnitOfWork
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog

    actors = _seed_admin_users()
    actor = ActorContext(str(actors["author"]))
    reviewer = ActorContext(str(actors["reviewer"]))
    qa_id = "CI-" + uuid4().hex[:16].upper()

    def key(operation):
        return IdempotencyKey(f"{qa_id}:{operation}")

    def save(answer, expected_version, suffix=None):
        suffix = suffix or answer
        content = GovernedQaContent(
            qa_id=qa_id, category="服務流程", category_id="service_flow", tag="合成",
            question=f"測試題 {qa_id}？", aliases=("合成別名",), answer=answer, source_ref=f"source-{suffix}-{qa_id}",
        )
        return app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", content.question, encode_governed_qa(content),
            content.source_ref, actor, key(f"draft-{suffix}"), CorrelationId(f"{qa_id}:draft"),
            ExpectedVersion(expected_version) if expected_version is not None else None,
        ))[0]

    def publish(version, attempt):
        return PublishKnowledgeItemCommand(
            item_id, ExpectedVersion(version), reviewer, "合成發布", key(attempt),
            CorrelationId(f"{qa_id}:publish"),
        )

    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    catalog = PublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    item_id = save("A", None)
    first = publish(1, "publish-A")
    first_version, index_job = app.publish_and_request_index(first)
    assert app.publish_and_request_index(first) == (first_version, index_job)
    assert save("B", first_version) == item_id
    second = publish(first_version + 1, "publish-B")
    assert catalog.get(qa_id).answer == "A"
    assert catalog.get(qa_id).source_uri == f"source-A-{qa_id}"

    original_commit = KnowledgeRetrievalMySqlUnitOfWork.commit

    def fail_after_writes(unit):
        with unit._connection.cursor() as cursor:
            cursor.execute("SELECT published_version FROM knowledge_items WHERE id=%s", (item_id,))
            assert cursor.fetchone()["published_version"] == first_version + 2
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s", (second.idempotency_key.value,))
            assert cursor.fetchone()["n"] == 1
        raise RuntimeError("synthetic failure after official pointer and receipt")

    monkeypatch.setattr(KnowledgeRetrievalMySqlUnitOfWork, "commit", fail_after_writes)
    with pytest.raises(RuntimeError, match="synthetic failure after official pointer and receipt"):
        app.publish_and_request_index(second)

    assert catalog.get(qa_id).answer == "A"
    with get_connection() as fresh:
        with fresh.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s", (second.idempotency_key.value,))
            assert cursor.fetchone()["n"] == 0
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_versions WHERE item_id=%s AND item_version=%s", (item_id, first_version + 2))
            assert cursor.fetchone()["n"] == 0

    monkeypatch.setattr(KnowledgeRetrievalMySqlUnitOfWork, "commit", original_commit)
    assert app.publish_and_request_index(second)[0] == first_version + 2
    assert catalog.get(qa_id).answer == "B"

    assert save("答" * 4999 + "😀", first_version + 2, "oversize") == item_id
    too_long = publish(first_version + 3, "publish-oversize")
    with pytest.raises(ValueError, match="knowledge_qa_line_reply_too_long"):
        app.publish_and_request_index(too_long)
    assert catalog.get(qa_id).answer == "B"
    with get_connection() as fresh:
        with fresh.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s", (too_long.idempotency_key.value,))
            assert cursor.fetchone()["n"] == 0


def test_faq_04_mysql_compatible_upgrade_rerun():
    from pathlib import Path

    from scripts.migrate_preserved_database_additive_schema import (
        DatabaseConfig, _canonical_artifact_descriptor, _schema_snapshot, local_additive_descriptor_state,
    )
    from scripts.reset_fake_database import split_sql

    root = Path(__file__).resolve().parents[1]
    sql = root / "db/schema_parts/1087_shared_line_faq.sql"
    descriptor = _canonical_artifact_descriptor(sql.name)
    config = DatabaseConfig(
        os.environ["LABOR_UNION_TEST_MYSQL_HOST"], int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        os.environ["LABOR_UNION_TEST_MYSQL_USER"], os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
    )
    assert DATABASE.startswith("lu_test_faq_")
    assert config.host == "127.0.0.1"

    def migrate():
        before = _schema_snapshot(config, DATABASE)
        status = local_additive_descriptor_state(before, descriptor, sql.name)
        if status == "absent":
            with config.connect(DATABASE) as connection:
                with connection.cursor() as cursor:
                    for statement in split_sql(sql.read_text(encoding="utf-8")):
                        cursor.execute(statement)
        else:
            assert status == "exact"
        after = _schema_snapshot(config, DATABASE)
        assert local_additive_descriptor_state(after, descriptor, sql.name) == "exact"
        return status

    assert migrate() == "absent"
    assert migrate() == "exact"


def test_faq_04_mysql_legacy_audit_and_backfill_rerun():
    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from infrastructure.mysql.mysql_adapter import get_connection
    from scripts.backfill_shared_line_faq import POLICY_LABELS, backfill
    from subsystems.knowledge_retrieval.faq_catalog import KnowledgeCatalogUnavailable, PublishedFaqCatalog
    from subsystems.line.capabilities import LineCapability

    actors = _seed_admin_users()
    actor = ActorContext(str(actors["author"]), (LineCapability.CONFIG_MANAGE.value,))
    reviewer = ActorContext(str(actors["reviewer"]))
    run = uuid4().hex[:12].upper()
    correlation = CorrelationId(f"legacy-faq-{run}")
    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    catalog = PublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    legacy = []
    item_ids = []

    for index, category in enumerate(("服務流程", "收費與補助")):
        qa_id = f"LEGACY-{run}-{index}"
        question = f"舊題 {qa_id}？"
        source_ref = f"original:{qa_id}"
        content = GovernedQaContent(qa_id, category, "合成", question, (), "正式 A", source_ref)
        legacy.append({"id": qa_id, "category": category, "question": question, "answer": "匯入來源內容", "enabled": True})
        item_id = app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", question, encode_governed_qa(content),
            source_ref, actor, IdempotencyKey(f"{qa_id}:initial"), correlation,
        ))[0]
        item_ids.append(item_id)
        assert app.publish(PublishKnowledgeItemCommand(
            item_id, ExpectedVersion(1), reviewer, "正式 A", IdempotencyKey(f"{qa_id}:publish"), correlation,
        )) == 2
        revised = GovernedQaContent(qa_id, category, "合成", "只在草稿的題目", (), "草稿 B", f"revised:{qa_id}")
        app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", revised.question, encode_governed_qa(revised),
            revised.source_ref, actor, IdempotencyKey(f"{qa_id}:revision"), correlation, ExpectedVersion(2),
        ))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany("UPDATE knowledge_items SET published_version=NULL WHERE id=%s", [(item_id,) for item_id in item_ids])
        connection.commit()

    with pytest.raises(KnowledgeCatalogUnavailable):
        catalog.page(None)

    def migration(reviewed, *, apply):
        with get_connection() as connection:
            return backfill(connection, legacy, reviewed, actor=actor, correlation_id=correlation, apply=apply)

    blocked = migration({}, apply=True)
    assert blocked["updated_items"] == 0
    assert {issue["code"] for issue in blocked["issues"]} == {"legacy_policy_unresolved"}
    reviewed = {"legacy_questions": {text: legacy[1]["id"] for text in POLICY_LABELS}}
    audit = migration(reviewed, apply=False)
    assert audit["issues"] == [] and audit["updated_items"] == 0 and audit["layout_revision"] == 0
    with pytest.raises(KnowledgeCatalogUnavailable):
        catalog.page(None)
    applied = migration(reviewed, apply=True)
    assert applied["issues"] == [] and applied["updated_items"] >= 2 and applied["layout_revision"] == 1
    for row in legacy:
        official = catalog.get(row["id"])
        assert official.answer == "正式 A" and official.source_version == 2
        assert catalog.match_legacy_text(row["question"]) == (official,)
    assert catalog.match_legacy_text(POLICY_LABELS[0])[0].qa_id == legacy[1]["id"]
    repeated = migration(reviewed, apply=True)
    assert repeated["issues"] == [] and repeated["updated_items"] == 0 and repeated["layout_revision"] == 1


_FQ_SERVICE = "cutover-service"
_FQ_PAYMENT = "cutover-payment"
_FQ_RETIRED = "cutover-retired"
_FQ_OLD_MESSAGE = "舊卡片送出的服務問句？"
_FQ_DUPLICATE_MESSAGE = "兩題共用的舊文字？"
_FQ_OFFICIAL_A = "隔離測試正式答案 A"
_FQ_DRAFT_B = "隔離測試未發布草稿 B"
_FQ_READER_MARKER = "migration:shared-line-faq:reader-ready:v1"


def _seed_faq_predecessor(config, database, scenario):
    """Create legacy facts on 1086, including the historical v1 ingest fingerprint."""
    from hashlib import sha256
    import json

    from domains.knowledge_retrieval.knowledge import source_digest
    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa

    aliases = (_FQ_OLD_MESSAGE,)
    duplicate = (_FQ_DUPLICATE_MESSAGE,) if scenario == "ambiguous" else ()
    service = GovernedQaContent(
        _FQ_SERVICE, "服務流程", "合成", "服務何時開始？", aliases + duplicate, _FQ_OFFICIAL_A,
        "fixture:official-service-source",
    )
    draft = GovernedQaContent(
        _FQ_SERVICE, "服務流程", "合成", "新服務問題？", (), _FQ_DRAFT_B, "fixture:draft-service-source",
    )
    payment = GovernedQaContent(
        _FQ_PAYMENT, "收費與補助", "合成", "補助如何計算？", duplicate, "隔離測試補助答案",
        "fixture:official-payment-source",
    )
    retired = GovernedQaContent(
        _FQ_RETIRED, "服務流程", "合成", "已停用的合成問題？", (), "已停用的合成答案",
        "fixture:retired-source",
    )

    with config.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO admin_users(username,password_hash,display_name,role) VALUES (%s,%s,%s,%s)",
            ("fixture_faq_cutover", "unused", "FAQ 合成管理員", "line_agent"),
        )
        actor_id = int(cursor.lastrowid)
        for revisions, state in (
            ((("ingested", service), ("published", service), ("ingested", draft)), "draft"),
            ((("ingested", payment), ("published", payment)), "published"),
            ((("ingested", retired), ("published", retired), ("retired", retired)), "retired"),
        ):
            latest = revisions[-1][1]
            cursor.execute(
                "INSERT INTO knowledge_items(source_identity,source_uri,source_trust_tier,title,content,"
                "content_digest,state,version,created_by_admin_user_id,published_by_admin_user_id) "
                "VALUES (%s,%s,'internal_policy',%s,%s,%s,%s,%s,%s,%s)",
                (latest.source_identity, latest.source_ref, latest.question, encode_governed_qa(latest),
                 source_digest(encode_governed_qa(latest)), state, len(revisions), actor_id,
                 actor_id if state == "published" else None),
            )
            item_id = int(cursor.lastrowid)
            for version, (event_type, item) in enumerate(revisions, 1):
                encoded = encode_governed_qa(item)
                digest = source_digest(encoded)
                key = f"fixture:{item.qa_id}:{version}"
                correlation = f"fixture:{item.qa_id}:correlation"
                event_state = "draft" if event_type == "ingested" else event_type
                snapshot = json.dumps({
                    "knowledge_item_id": item_id, "state": event_state, "version": version,
                    "source_identity": item.source_identity if event_type == "ingested" else None,
                    "content_digest": digest,
                })
                cursor.execute(
                    "INSERT INTO knowledge_item_versions(item_id,item_version,content,source_digest,"
                    "event_type,actor_admin_user_id,reason,idempotency_key) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (item_id, version, encoded, digest, event_type, actor_id, "合成歷史事件", key),
                )
                cursor.execute(
                    "INSERT INTO knowledge_item_events(knowledge_item_id,actor_admin_user_id,event_type,"
                    "before_version,after_version,reason,idempotency_key,correlation_id,snapshot_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (item_id, actor_id, event_type, version - 1, version, "合成歷史事件", key, correlation, snapshot),
                )
                if event_type != "ingested":
                    continue
                source_uri = item.source_ref
                if scenario == "unproven" and item is service:
                    source_uri = "fixture:unmatched-legacy-source"
                command = IngestKnowledgeSourceCommand(
                    item.source_identity, "internal_policy", item.question, encoded, source_uri,
                    ActorContext(str(actor_id)), IdempotencyKey(key), CorrelationId(correlation),
                )
                predecessor_repr = repr(command).removesuffix(", expected_version=None)") + ")"
                cursor.execute(
                    "INSERT INTO knowledge_apply_receipts(idempotency_key,command_fingerprint,receipt_json) "
                    "VALUES (%s,%s,%s)",
                    (key, sha256(predecessor_repr.encode()).hexdigest(), snapshot),
                )

    return [
        {"id": item.qa_id, "category": item.category, "tag": item.tag, "question": item.question,
         "answer": item.answer, "aliases": item.aliases, "source_ref": item.source_ref, "enabled": True}
        for item in (service, payment)
    ]


@pytest.fixture
def _faq_preserved_upgrade(tmp_path, request, monkeypatch, capsys):
    import json
    from argparse import Namespace
    from types import SimpleNamespace

    from scripts import backfill_shared_line_faq as faq
    from scripts import migrate_preserved_database_additive_schema as migration
    from scripts.bootstrap_disposable_mysql_schema import bootstrap

    container = os.environ.get("FAQ_CUTOVER_MYSQL_CONTAINER")
    if not container:
        pytest.skip("requires the Shared LINE FAQ CI workflow isolated MySQL service")
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    port = int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"])
    assert host == "127.0.0.1" and port == 3307 and DATABASE.startswith("lu_test_faq_")
    config = migration.DatabaseConfig(host, port, "root", "")
    run_id = uuid4().hex[:12]
    source, candidate = (f"lu_test_faq_cut_{kind}_{run_id}" for kind in ("source", "candidate"))
    bootstrap(Namespace(
        host=host, port=port, user=config.user, password=config.password,
        database=source, confirm_database=source, max_schema_part=1086,
    ))
    scenario = getattr(request, "param", "positive")
    catalog = _seed_faq_predecessor(config, source, scenario)
    catalog_path = tmp_path / "legacy.jsonl"
    catalog_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in catalog),
        encoding="utf-8",
    )
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps({
        "reviewed_by": "fixture-data-maintainer",
        "categories": {},
        "legacy_questions": {label: _FQ_PAYMENT for label in faq.POLICY_LABELS},
    }, ensure_ascii=False), encoding="utf-8")
    environment_file = tmp_path / "runtime.env"
    environment_file.write_text(
        f"DB_HOST={host}\nDB_PORT={port}\nDB_USER=root\nDB_PASSWORD=\nDB_DATABASE={source}\n",
        encoding="utf-8",
    )
    plan_path = tmp_path / "candidate-plan.json"
    receipt_path = tmp_path / "candidate-operation.json"
    switch_path = tmp_path / "candidate-switch.json"
    dump_path = tmp_path / "source.sql"
    backup_path = tmp_path / "source-backup.json"
    monkeypatch.setattr(faq, "DEFAULT_INPUT", catalog_path)
    case = SimpleNamespace(
        config=config, source=source, candidate=candidate, reviewed=reviewed_path,
        environment=environment_file, receipt=receipt_path, switched=switch_path,
        migration=migration, scenario=scenario, capsys=capsys,
        args=[
            "--rehearsal", "--environment-file", str(environment_file),
            "--source-database", source, "--candidate-database", candidate, "--mysql-container", container,
            "--plan-receipt", str(plan_path), "--operation-receipt", str(receipt_path),
            "--source-dump", str(dump_path), "--source-backup-receipt", str(backup_path),
            "--switch-receipt", str(switch_path),
        ],
    )
    plan = _faq_controlled_command(case, "dry-run")
    assert plan["status"] == "ready"
    assert any("faq" in item["backfill_id"] for item in plan["backfills"]), plan["backfills"]
    _faq_controlled_command(case, "backup")
    _faq_controlled_command(case, "restore")
    return case


def _faq_controlled_command(case, mode, *, reviewed=True, blocked=False):
    import json

    args = [*case.args, f"--{mode}"]
    if mode == "apply":
        args += ["--confirm", case.migration.APPLY_CONFIRMATION]
        if reviewed:
            args += ["--faq-reviewed-mapping", str(case.reviewed)]
    case.capsys.readouterr()
    exit_code = case.migration.main(args)
    captured = case.capsys.readouterr()
    assert exit_code == int(blocked), captured.err
    output = captured.err if blocked else captured.out
    result = json.loads(output.strip().splitlines()[-1])
    if blocked:
        assert result["status"] == "blocked" and result["error_type"] == "UpgradeBlocked", result
    return result


def _faq_expect_switch_blocked(case):
    result = _faq_controlled_command(case, "switch", blocked=True)
    assert "verified" in result["message"] or "readback" in result["message"]
    assert case.migration.config_from_env(case.environment)[1] == case.source
    assert not case.switched.exists()


def _faq_runtime_answers(case, monkeypatch, database=None, *, shared=False):
    from types import SimpleNamespace
    import json

    from fastapi.testclient import TestClient

    from api.dependencies.admin_auth import require_admin
    from api.dependencies.line_worker_operation import _event_handlers, webhook_reply_dispatcher
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.access.integration_capabilities import IntegrationCapability
    from api.main import app
    from domains.line.identities import LineSourceType, LineUserId, LineWebhookEventId
    from infrastructure.mysql import mysql_adapter
    from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE

    runtime_config, live_database = case.migration.config_from_env(case.environment)
    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", {
        "host": runtime_config.host, "port": runtime_config.port,
        "user": runtime_config.user, "password": runtime_config.password,
        "database": database or live_database, "charset": "utf8mb4",
    })
    def now():
        return datetime.now(timezone.utc)

    handlers, _ = _event_handlers(now)
    dispatch = webhook_reply_dispatcher(now, lambda *_: False)

    def reply(*, text="", postback="", worker=False):
        requests = []
        payload = {"message": {"type": "text", "text": text}} if text else {"postback": {"data": postback}}
        event = SimpleNamespace(
            event_type="message" if text else "postback",
            event_id=LineWebhookEventId(f"fixture:{uuid4().hex}"),
            payload_json=json.dumps(payload, ensure_ascii=False),
            occurred_at=now(),
            source=SimpleNamespace(source_type=LineSourceType.USER, user_id=LineUserId("U" + "1" * 32)),
        )
        unit = SimpleNamespace(
            delivery_tasks=SimpleNamespace(enqueue=requests.append),
            platform_users=SimpleNamespace(apply_friend_event=lambda _: None),
        )
        inbox = SimpleNamespace(event=event)
        if worker:
            handlers[event.event_type](inbox, unit)
        elif not dispatch(inbox, unit):
            assert requests == []
        if not requests:
            return None
        [request] = requests
        assert request.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE
        return json.loads(request.payload_json)

    monkeypatch.setitem(app.dependency_overrides, require_admin, lambda: AdminPrincipal(
        None, "fixture", "fixture", "operator",
        capabilities=frozenset({IntegrationCapability.KNOWLEDGE_READ.value}),
    ))
    response = TestClient(app).get("/api/v1/line/faq-layout/published-questions", params={"qa_id": _FQ_SERVICE})
    assert response.status_code == 200, response.text
    [item] = response.json()["data"]["items"]
    assert item["version"] == 2
    assert item["answer"] == _FQ_OFFICIAL_A
    assert item["category_id"] == ("service_flow" if shared else None)
    for worker in (False, True):
        message = reply(text=_FQ_OLD_MESSAGE, worker=worker)["text"]
        assert _FQ_OFFICIAL_A in message and _FQ_DRAFT_B not in message
    return reply


def _faq_candidate_state(case):
    with case.config.connect(case.candidate) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_identity,version,state,published_version FROM knowledge_items "
            "WHERE source_identity LIKE 'line-common-qa:%' ORDER BY source_identity",
        )
        knowledge = {row["source_identity"]: row for row in cursor.fetchall()}
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_versions")
        version_count = cursor.fetchone()["n"]
        cursor.execute("SELECT COUNT(*) AS n FROM line_configuration_revisions WHERE configuration_kind='faq_chat_layout'")
        layout_count = cursor.fetchone()["n"]
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s",
                       (_FQ_READER_MARKER,))
        marker_count = cursor.fetchone()["n"]
    return knowledge, version_count, layout_count, marker_count


def _faq_observe_candidate_readback(monkeypatch, case, *, fault=None):
    import pymysql

    state = {"writer": None, "readback": None, "injected": False}
    execute = pymysql.cursors.DictCursor.execute

    def candidate_execute(cursor, query, args=None):
        if cursor.connection.db in {case.candidate, case.candidate.encode()} and isinstance(query, str):
            if query.startswith("UPDATE knowledge_items SET published_version"):
                state["writer"] = cursor.connection.thread_id()
                if fault == "backfill-failure":
                    state["injected"] = True
                    raise pymysql.OperationalError(1105, "fixture backfill write failed")
            if (
                state["writer"] is not None
                and query.startswith("SELECT id, source_identity, version, published_version,")
                and cursor.connection.thread_id() != state["writer"]
            ):
                state["readback"] = cursor.connection.thread_id()
                if fault == "readback-failure":
                    state["injected"] = True
                    raise pymysql.OperationalError(1105, "fixture verification readback failed")
        return execute(cursor, query, args)

    monkeypatch.setattr(pymysql.cursors.DictCursor, "execute", candidate_execute)
    return state


def test_faq_cutover_preserved_release_reads_official_a_and_replays(_faq_preserved_upgrade, monkeypatch):
    case = _faq_preserved_upgrade
    _faq_runtime_answers(case, monkeypatch)
    _faq_expect_switch_blocked(case)

    blocked = _faq_controlled_command(case, "apply", reviewed=False, blocked=True)
    assert blocked["message"] == "faq_cutover_reviewed_mapping_required"
    _, versions, layouts, marker = _faq_candidate_state(case)
    assert (versions, layouts, marker) == (8, 0, 0)
    _faq_runtime_answers(case, monkeypatch, case.candidate)
    _faq_expect_switch_blocked(case)

    observed = _faq_observe_candidate_readback(monkeypatch, case)
    applied = _faq_controlled_command(case, "apply")
    assert applied["faq_cutover"]["status"] == "read_back"
    assert _faq_candidate_state(case)[-1] == 0
    _faq_expect_switch_blocked(case)
    assert observed["writer"] is not None
    assert observed["readback"] not in (None, observed["writer"])
    verified = _faq_controlled_command(case, "verify")
    assert verified["status"] == "verified"
    before_replay = _faq_candidate_state(case)
    knowledge, versions, layouts, marker = before_replay
    assert (versions, layouts, marker) == (8, 1, 1)
    assert knowledge["line-common-qa:" + _FQ_SERVICE] == {
        "source_identity": "line-common-qa:" + _FQ_SERVICE, "version": 3, "state": "draft", "published_version": 2,
    }
    assert knowledge["line-common-qa:" + _FQ_RETIRED]["published_version"] is None
    _faq_controlled_command(case, "apply")
    assert _faq_candidate_state(case) == before_replay

    switched = _faq_controlled_command(case, "switch")
    assert switched["status"] == "switched"
    assert case.migration.config_from_env(case.environment)[1] == case.candidate
    reply = _faq_runtime_answers(case, monkeypatch, shared=True)
    new_button = reply(postback="faq:v1:question:" + _FQ_SERVICE, worker=True)["text"]
    assert _FQ_OFFICIAL_A in new_button and _FQ_DRAFT_B not in new_button


@pytest.mark.parametrize("_faq_preserved_upgrade", [
    pytest.param("ambiguous", id="ambiguous"),
    pytest.param("unproven", id="unproven"),
    pytest.param("backfill-failure", id="backfill-failure"),
    pytest.param("readback-failure", id="readback-failure"),
], indirect=True)
def test_faq_cutover_blocked_keeps_legacy_readers(_faq_preserved_upgrade, monkeypatch):
    case = _faq_preserved_upgrade
    scenario = case.scenario
    _faq_runtime_answers(case, monkeypatch)
    observed = _faq_observe_candidate_readback(monkeypatch, case, fault=scenario)

    blocked = _faq_controlled_command(case, "apply", blocked=True)
    gate = case.migration.read_receipt(case.receipt)["faq_cutover"]
    assert gate["status"] == "blocked"
    failure = {
        "ambiguous": "legacy_text_ambiguous",
        "unproven": "published_source_metadata_unproven",
        "backfill-failure": "faq_cutover_apply_failed",
        "readback-failure": "faq_cutover_verify_failed",
    }[scenario]
    assert failure in gate["reason"] and failure in blocked["message"]
    if scenario.endswith("-failure"):
        assert observed["injected"]
    _, versions, layouts, marker = _faq_candidate_state(case)
    assert versions == 8 and marker == 0
    assert layouts == (1 if scenario == "readback-failure" else 0)
    if scenario == "readback-failure":
        assert observed["readback"] not in (None, observed["writer"])
    _faq_expect_switch_blocked(case)
    _faq_runtime_answers(case, monkeypatch, case.candidate)
    _faq_runtime_answers(case, monkeypatch)


def test_faq_delete_mysql_permanent_purge_and_active_answer_guard(monkeypatch):
    from dataclasses import replace

    from pymysql.err import OperationalError

    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from infrastructure.mysql.knowledge_retrieval_unit_of_work import KnowledgeRetrievalMySqlUnitOfWork
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.knowledge_retrieval.contracts import (
        DeleteFaqKnowledgeItemCommand,
        RetireKnowledgeItemCommand,
    )
    from subsystems.knowledge_retrieval.faq_catalog import (
        PredecessorPublishedFaqCatalog,
        PublishedFaqCatalog,
    )

    actors = _seed_admin_users()
    actor = ActorContext(str(actors["author"]))
    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    catalog = PublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    predecessor = PredecessorPublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    run_id = "CI-" + uuid4().hex[:16].upper()
    correlation = CorrelationId(run_id)
    answer = "隔離測試正式答案"

    def ingest(qa_id: str, attempt: str, text: str) -> IngestKnowledgeSourceCommand:
        qa = GovernedQaContent(
            qa_id, "服務流程", "合成", f"合成問題 {qa_id}？", (), text,
            f"fixture:{qa_id}",
        )
        return IngestKnowledgeSourceCommand(
            qa.source_identity, "internal_policy", qa.question, encode_governed_qa(qa),
            qa.source_ref, actor, IdempotencyKey(f"{run_id}:{attempt}"), correlation,
        )

    def delete(item_id: int, version: int, attempt: str) -> DeleteFaqKnowledgeItemCommand:
        return DeleteFaqKnowledgeItemCommand(
            item_id, ExpectedVersion(version), actor, "清除隔離測試題目",
            IdempotencyKey(f"{run_id}:{attempt}"), correlation,
        )

    draft = ingest(run_id + "-DRAFT", "draft", "隔離測試草稿")
    draft_id, _ = app.ingest(draft)
    draft_delete = delete(draft_id, 1, "delete-draft")
    with get_connection() as connection, connection.cursor() as cursor:
        with pytest.raises(OperationalError, match="knowledge_item_versions records cannot be deleted"):
            cursor.execute("DELETE FROM knowledge_item_versions WHERE item_id=%s", (draft_id,))
        connection.rollback()

    def fail_before_commit(_unit_of_work):
        raise RuntimeError("fixture failure after FAQ purge")

    with monkeypatch.context() as patch:
        patch.setattr(KnowledgeRetrievalMySqlUnitOfWork, "commit", fail_before_commit)
        with pytest.raises(RuntimeError, match="fixture failure after FAQ purge"):
            app.delete_faq(draft_delete)
    assert app.get_item(draft_id)["current_version"] == 1
    assert app.delete_faq(draft_delete) == draft_id
    assert app.delete_faq(draft_delete) == draft_id
    with pytest.raises(RuntimeError, match="knowledge_idempotency_conflict"):
        app.delete_faq(replace(draft_delete, reason="不同刪除操作"))
    with pytest.raises(LookupError, match="knowledge_item_not_found"):
        app.delete_faq(delete(draft_id, 1, "delete-missing"))

    official = ingest(run_id, "official", answer)
    item_id, _ = app.ingest(official)
    published_version = app.publish(PublishKnowledgeItemCommand(
        item_id, ExpectedVersion(1), actor, "發布隔離測試題目",
        IdempotencyKey(f"{run_id}:publish"), correlation,
    ))
    with pytest.raises(RuntimeError, match="knowledge_faq_delete_published"):
        app.delete_faq(delete(item_id, published_version, "delete-active"))
    assert catalog.get(run_id).answer == answer

    revision = ingest(run_id, "revision", "編輯中的新版草稿")
    app.ingest(replace(revision, expected_version=ExpectedVersion(published_version)))
    current_version = published_version + 1
    blocked = delete(item_id, current_version, "delete-active-draft")
    with pytest.raises(RuntimeError, match="knowledge_faq_delete_published"):
        app.delete_faq(blocked)
    with pytest.raises(RuntimeError, match="knowledge_item_version_conflict"):
        app.delete_faq(delete(item_id, published_version, "delete-stale"))
    assert catalog.get(run_id).answer == answer

    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE knowledge_items SET published_version=NULL WHERE id=%s", (item_id,))
        connection.commit()
    assert predecessor.get(run_id).answer == answer
    assert not next(row for row in app.list_items(500) if row["id"] == item_id)["faq_delete_eligible"]
    with pytest.raises(RuntimeError, match="knowledge_faq_delete_published"):
        app.delete_faq(blocked)
    assert predecessor.get(run_id).answer == answer
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE knowledge_items SET published_version=%s WHERE id=%s",
            (published_version, item_id),
        )
        connection.commit()

    retired_version = app.retire(RetireKnowledgeItemCommand(
        item_id, ExpectedVersion(current_version), actor, "停用隔離測試題目",
        IdempotencyKey(f"{run_id}:retire"), correlation,
    ))
    assert next(row for row in app.list_items(500) if row["id"] == item_id)["faq_delete_eligible"]
    assert app.delete_faq(delete(item_id, retired_version, "delete-retired")) == item_id
    assert app.get_item(item_id) is None
    assert predecessor.get(run_id) is None
    assert catalog.get(run_id) is None

    replacement = ingest(run_id.lower(), "reimport", "不可匯入的新版答案")
    for command in (official, replacement, replace(replacement, expected_version=ExpectedVersion(retired_version))):
        with pytest.raises(RuntimeError, match="knowledge_faq_identity_deleted"):
            app.ingest(command)
    unrelated = ingest(run_id + "-NEW", "unrelated", "可以匯入的草稿")
    imported, _ = app.import_missing((replacement, unrelated))
    assert len(imported) == 1
    assert app.get_item(imported[0][0])["source_identity"] == unrelated.source_identity
    assert not {item_id, draft_id} & {row["id"] for row in app.list_items(500)}

    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge_items WHERE id IN (%s,%s)", (item_id, draft_id))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_versions WHERE item_id IN (%s,%s)", (item_id, draft_id))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_events WHERE knowledge_item_id IN (%s,%s)", (item_id, draft_id))
        assert cursor.fetchone()["n"] == 0
        cursor.execute(
            "SELECT idempotency_key,receipt_json FROM knowledge_apply_receipts WHERE idempotency_key IN (%s,%s,%s,%s)",
            (draft_delete.idempotency_key.value, official.idempotency_key.value,
             replacement.idempotency_key.value, blocked.idempotency_key.value),
        )
        receipts = {row["idempotency_key"]: row["receipt_json"] for row in cursor.fetchall()}
        assert set(receipts) == {draft_delete.idempotency_key.value, official.idempotency_key.value}
        assert answer not in receipts[draft_delete.idempotency_key.value]


def test_faq_delete_guard_upgrade_preserves_1087_rows_and_reruns():
    from pathlib import Path

    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from scripts.migrate_preserved_database_additive_schema import (
        DatabaseConfig,
        _canonical_artifact_descriptor,
        _schema_snapshot,
        local_additive_descriptor_state,
        schema_statements_for_state,
    )

    assert DATABASE.startswith("lu_test_faq_")
    config = DatabaseConfig(
        os.environ["LABOR_UNION_TEST_MYSQL_HOST"], int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        os.environ["LABOR_UNION_TEST_MYSQL_USER"], os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
    )
    assert config.host == "127.0.0.1"
    sql = Path(__file__).resolve().parents[1] / "db/schema_parts/1088_faq_permanent_delete_guard.sql"
    descriptor = _canonical_artifact_descriptor(sql.name)
    actor = ActorContext(str(_seed_admin_users()["author"]))
    qa_id = "CI-UPGRADE-" + uuid4().hex[:12].upper()
    qa = GovernedQaContent(qa_id, "服務流程", "合成", "升級前的題目", (), "保留的答案", f"fixture:{qa_id}")
    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    item_id, _ = app.ingest(IngestKnowledgeSourceCommand(
        qa.source_identity, "internal_policy", qa.question, encode_governed_qa(qa), qa.source_ref,
        actor, IdempotencyKey(qa_id), CorrelationId(qa_id),
    ))
    before = app.get_item(item_id)

    def migrate() -> str:
        snapshot = _schema_snapshot(config, DATABASE)
        status = local_additive_descriptor_state(snapshot, descriptor, sql.name)
        if status == "absent":
            with config.connect(DATABASE) as connection, connection.cursor() as cursor:
                for statement in schema_statements_for_state(sql, status, snapshot):
                    cursor.execute(statement)
        else:
            assert status == "exact"
        assert local_additive_descriptor_state(_schema_snapshot(config, DATABASE), descriptor, sql.name) == "exact"
        assert app.get_item(item_id) == before
        with config.connect(DATABASE) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_events WHERE knowledge_item_id=%s", (item_id,))
            assert cursor.fetchone()["n"] == 1
        return status

    assert migrate() == "absent"
    assert migrate() == "exact"
