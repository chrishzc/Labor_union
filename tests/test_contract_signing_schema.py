from __future__ import annotations

from pathlib import Path


SCHEMA_PART = Path("db/schema_parts/166_contract_signing_workflow.sql")


def test_contract_signing_schema_declares_append_only_document_and_commitment_roots():
    schema = SCHEMA_PART.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS contract_document_versions" in schema
    assert "CREATE TABLE IF NOT EXISTS contract_document_access_grants" in schema
    assert "CREATE TABLE IF NOT EXISTS contract_signing_events" in schema
    assert "CREATE TABLE IF NOT EXISTS contract_signing_command_receipts" in schema
    assert "CREATE TABLE IF NOT EXISTS contract_signing_outbox" in schema
    assert "CREATE TABLE IF NOT EXISTS precontract_service_commitments" in schema
    assert "CREATE TABLE IF NOT EXISTS precontract_service_commitment_days" in schema
    assert "CREATE TABLE IF NOT EXISTS precontract_service_commitment_events" in schema
    assert "contract_document_versions records cannot be updated" in schema
    assert "contract_signing_events records cannot be deleted" in schema
    assert "precontract_service_commitments records cannot be updated" in schema


def test_contract_signing_schema_declares_idempotent_receipt_and_committed_outbox_roots():
    schema = SCHEMA_PART.read_text(encoding="utf-8")

    assert "UNIQUE KEY uq_contract_signing_receipt_key (idempotency_key)" in schema
    assert "command_fingerprint CHAR(64) NOT NULL" in schema
    assert "UNIQUE KEY uq_contract_signing_outbox_key (intent_key)" in schema
    assert "signing_event_id BIGINT NOT NULL" in schema


def test_contract_signing_schema_keeps_client_and_staff_document_targets_distinct():
    schema = SCHEMA_PART.read_text(encoding="utf-8")

    assert "document_scope ENUM('staff_segment', 'client_contract')" in schema
    assert "document_target_key VARCHAR(100) NOT NULL" in schema
    assert "CHAR_LENGTH(TRIM(document_target_key)) > 0" in schema
    assert "UNIQUE KEY uq_contract_document_version" in schema


def test_contract_signing_schema_links_signed_returns_to_their_sent_document_chain():
    schema = SCHEMA_PART.read_text(encoding="utf-8")

    assert "source_document_version_id BIGINT NULL" in schema
    assert "document_role ENUM('template_generated', 'signed_return')" in schema
    assert "AND source_document_version_id IS NULL" in schema
    assert "OR (document_role = 'signed_return' AND source_document_version_id IS NOT NULL)" in schema


def test_contract_signing_schema_allows_only_line_as_the_send_channel():
    schema = SCHEMA_PART.read_text(encoding="utf-8")

    assert "delivery_channel ENUM('line') NULL" in schema
    assert "line_delivery_task_id BIGINT UNSIGNED NULL" in schema
    assert "document_access_grant_id BIGINT UNSIGNED NULL" in schema
    assert "fk_contract_signing_event_line_delivery_task" in schema
    assert "fk_contract_signing_event_document_access_grant" in schema
    assert "AND line_delivery_task_id IS NOT NULL" in schema


def test_api_composition_supplies_orders_contract_identity_projection():
    repository = Path("infrastructure/mysql/order_contract_completion_repository.py")
    signing_application = Path("subsystems/contract_signing/client_contract_application.py")
    composition = Path("api/dependencies/contract_signing.py")

    assert "def record_contract_identity" in repository.read_text(encoding="utf-8")
    assert "repository.record_contract_identity" not in signing_application.read_text(
        encoding="utf-8"
    )
    assert "repository.record_contract_identity" in composition.read_text(encoding="utf-8")
