"""Original immutable per-file receipt projections; never execute project SQL."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from infrastructure.db.controlled_file_repository import (
    MySqlControlledFileWorkflowRepository, _committed_apply_evidence, _receipt_snapshot,
    _COMMITTED_APPLY_EVIDENCE_SQL, _bounded_readback_list_query,
)
from subsystems.controlled_files.workflow import (
    ControlledFileReadback, ControlledFileOwner, ControlledFilePurpose, ControlledFileApplyReceipt,
    ControlledFileApplyOutcome, ControlledFileWorkflowError,
    ControlledFileDownloadReference,
)

NOW = datetime(2026,11,6,tzinfo=timezone.utc)
FILE = "cf_"+"a"*32
HASH = "b"*64


def evidence_row():
    readback=ControlledFileReadback(FILE,ControlledFileOwner.CONTRACT_SIGNING,ControlledFilePurpose.FINAL_SIGNED_CONTRACT,
        "CASE","staff.pdf","contract-signing/CASE",3,HASH,"application/pdf",101,"registered",NOW)
    receipt=ControlledFileApplyReceipt("cfr_"+"c"*32,ControlledFileApplyOutcome.CREATED,readback)
    return {"file_id":FILE,"owner_type":"contract_signing","purpose":"final_signed_contract","subject_reference":"CASE",
        "filename":"staff.pdf","logical_folder":"contract-signing/CASE","version_number":3,"content_sha256":HASH,
        "content_type":"application/pdf","size_bytes":101,"applied_at_utc":NOW,"receipt_id":receipt.receipt_id,
        "command_type":"controlled_file_apply","schema_version":"controlled-file-apply-receipt.v1",
        "command_fingerprint":"d"*64,"result_snapshot":_receipt_snapshot(receipt),"outcome_state":"created",
        "idempotency_key":"original-file-command","receipt_actor_ref":"admin:7","object_actor_ref":"admin:7",
        "correlation_id":"original-correlation","object_database_id":2,"controlled_object_id":2,
        "source_staging_id":10,"staging_object_id":10}


def test_own_immutable_apply_snapshot_supplies_exact_legacy_file_hash_and_provenance():
    row=evidence_row()
    evidence=_committed_apply_evidence(row)
    assert evidence.receipt.readback.file_id==FILE and evidence.receipt.readback.version==3
    assert evidence.receipt.readback.sha256_digest==HASH
    assert evidence.receipt.readback.purpose is ControlledFilePurpose.FINAL_SIGNED_CONTRACT
    assert evidence.idempotency_key.value=="original-file-command"
    assert evidence.actor.actor_id=="admin:7" and evidence.correlation_id.value=="original-correlation"
    assert row==evidence_row()  # Read projection does not backfill historical JSON.


@pytest.mark.parametrize("key,value", [("file_id","cf_"+"e"*32),("version",4),("sha256_digest","e"*64),
    ("owner","staff"),("purpose","staff_resume"),("subject_reference","OTHER"),("size_bytes",102),
    ("mime_type","image/jpeg"),("outcome","unknown"),("status","available")])
def test_snapshot_object_disagreement_is_typed_corrupt_not_a_weaker_fallback(key,value):
    row=evidence_row(); row["result_snapshot"]=deepcopy(row["result_snapshot"])
    row["result_snapshot"][key]=value
    with pytest.raises(ControlledFileWorkflowError) as error:
        _committed_apply_evidence(row)
    assert error.value.code=="controlled_file_receipt_corrupt" and not error.value.retryable


@pytest.mark.parametrize("key,value", [("command_type","other"),("schema_version","other"),("outcome_state","pending"),
    ("controlled_object_id",1),("staging_object_id",11),("object_database_id",0),("controlled_object_id",True),
    ("receipt_actor_ref","admin:8"),("receipt_actor_ref",None),("idempotency_key",None),("correlation_id",None)])
def test_receipt_requires_exact_foreign_keys_closed_command_and_typed_provenance(key,value):
    row=evidence_row();row[key]=value
    with pytest.raises(ControlledFileWorkflowError) as error:_committed_apply_evidence(row)
    assert error.value.code=="controlled_file_receipt_corrupt"


def test_invalid_file_id_stops_before_cursor_and_receipt_query_is_exact_readonly_bounded():
    class NoSqlConnection:
        def cursor(self):raise AssertionError("project SQL including fake execute is forbidden")
    assert MySqlControlledFileWorkflowRepository(NoSqlConnection()).get_committed_apply_evidence("not-a-file")==None
    # Static contract only; database SQL syntax, immutable triggers and FK
    # execution are NOT_RUN under the user's explicit SQL prohibition.
    assert "o.id=r.controlled_object_id" in _COMMITTED_APPLY_EVIDENCE_SQL
    assert _COMMITTED_APPLY_EVIDENCE_SQL.endswith("WHERE o.opaque_object_id=%s LIMIT 2")
    assert not any(token in _COMMITTED_APPLY_EVIDENCE_SQL.upper() for token in ("UPDATE ","INSERT ","DELETE ","FOR UPDATE"))


@pytest.mark.parametrize("limit,expected", [(None,100),(1,1),(100,100)])
def test_original_default_and_explicit_list_limit_never_generate_double_limit(limit,expected):
    statement,parameters=_bounded_readback_list_query(limit)
    assert statement.count(" LIMIT ")==1 and statement.endswith(" LIMIT %s")
    assert parameters==(expected,)


@pytest.mark.parametrize("limit", [0,101,True,"1"])
def test_invalid_list_bounds_are_rejected_before_sql(limit):
    with pytest.raises(ValueError):_bounded_readback_list_query(limit)


def legacy_maintenance(monkeypatch, mode):
    from domains.contract_signing.external_signing import ExternalSigningState, SignedContractDocumentTarget
    from subsystems.contract_signing.final_document_workflow import (
        FinalContractDocumentReadback, FinalSignedContractApplyReceipt, SignedContractDocumentReadback,
        signed_contract_object_key, signed_contract_file_apply_key,
    )
    from infrastructure.db import contract_external_signing_repository as owner
    from subsystems.controlled_files.maintenance import ControlledFileMaintenanceApplication
    from subsystems.controlled_files.contracts import ControlledFileStagingContent
    from shared_kernel.identities import IdempotencyKey
    from shared_kernel.clock import FixedBusinessClock
    content=b"abc"; own_hash=sha256(content).hexdigest(); primary_hash=sha256(b"client").hexdigest()
    prefix="TEST-ONLY-" if mode=="test_only" else ""
    modern=mode in {"modern","missing_modern_hash"}
    purpose=ControlledFilePurpose.SIGNED_STAFF_AGREEMENT if modern else ControlledFilePurpose.FINAL_SIGNED_CONTRACT
    target=SignedContractDocumentTarget("staff",11,8)
    staff=SignedContractDocumentReadback(target,FILE,1,prefix+"staff.pdf","application/pdf",3,
        own_hash if mode=="modern" else None,purpose if mode=="modern" else None)
    client=SignedContractDocumentReadback(SignedContractDocumentTarget("client",None,7),"cf_"+"e"*32,
        1,prefix+"client.pdf","application/pdf",6,
        primary_hash if modern else None,ControlledFilePurpose.FINAL_SIGNED_CONTRACT if modern else None)
    document=FinalContractDocumentReadback("cfd_"+"f"*32,"CASE",client.file_id,1,client.filename,"application/pdf",6,"completed",NOW)
    receipt=FinalSignedContractApplyReceipt("cesr_"+"a"*32,"ces_"+"b"*32,4,ExternalSigningState.COMPLETED,document,"identity",(client,staff))
    snapshot=owner._final_receipt_snapshot(receipt); before=deepcopy(snapshot)
    object_row={"object_id":2,"opaque_object_id":FILE,"object_key":signed_contract_object_key(receipt.session_id,target),
        "owner_type":"contract_signing","purpose":purpose.value,"subject_reference":"CASE","version_number":1,
        "filename":staff.filename,"content_type":"application/pdf","size_bytes":3,"content_sha256":own_hash}
    parent={"external_signing_session_id":receipt.session_id,"case_no":"CASE","final_document_id":document.final_document_id,
        "receipt_id":receipt.receipt_id,"result_status_version":4,"primary_object_id":1,"primary_content_sha256":primary_hash,
        "primary_size_bytes":6,"result_snapshot":snapshot,"is_current":1,
        "parent_idempotency_key":"legacy-parent","parent_actor_ref":"admin:7","parent_correlation_id":"original-correlation"}
    own=evidence_row() | {"version_number":1,"filename":staff.filename,"size_bytes":3,"content_sha256":own_hash,
        "purpose":purpose.value,"idempotency_key":signed_contract_file_apply_key(IdempotencyKey("legacy-parent"),target).value}
    readback=ControlledFileReadback(FILE,ControlledFileOwner.CONTRACT_SIGNING,purpose,"CASE",staff.filename,
        "contract-signing/CASE",1,own_hash,"application/pdf",3,"registered",NOW)
    own["result_snapshot"]=_receipt_snapshot(ControlledFileApplyReceipt(own["receipt_id"],ControlledFileApplyOutcome.CREATED,readback))
    if mode=="parent":parent["parent_idempotency_key"]="different-parent"
    if mode=="actor":parent["parent_actor_ref"]="admin:8"
    if mode=="correlation":parent["parent_correlation_id"]="different-correlation"
    if mode=="target":object_row["object_key"]=signed_contract_object_key(receipt.session_id,SignedContractDocumentTarget("staff",12,8))
    if mode=="corrupt":own["result_snapshot"]["version"]=2
    class NoSqlConnection:
        def cursor(self):raise AssertionError("project SQL including fake execute is forbidden")
    connection=NoSqlConnection()
    contract=owner.MySqlContractExternalSigningRepository(connection)
    # Query ports return synthetic persisted rows. No cursor/execute method is
    # called, and the original closed owner reader/projections remain real.
    contract._one=lambda statement,parameters:object_row
    contract._all=lambda statement,parameters:(parent,)
    def contract_factory(actual):
        assert actual is connection
        return contract
    monkeypatch.setattr(owner,"MySqlContractExternalSigningRepository",contract_factory)
    cfs=MySqlControlledFileWorkflowRepository(connection); calls=[]
    def own_receipt(file_id):
        calls.append(file_id)
        assert file_id==FILE
        return None if mode=="missing" else _committed_apply_evidence(own)
    cfs.get_committed_apply_evidence=own_receipt
    cfs.get_download_reference=lambda _:ControlledFileDownloadReference(readback,"cfs_"+"a"*32)
    class Storage:
        def read_registered_staged(self,staging_id,**kwargs):
            return ControlledFileStagingContent(staging_id,content,own_hash,NOW)
    def no_transaction():raise AssertionError("Preview must not begin a transaction")
    service=ControlledFileMaintenanceApplication(cfs,Storage(),no_transaction,FixedBusinessClock(NOW))
    return service,calls,snapshot,before,own_hash,primary_hash


@pytest.mark.parametrize("mode,complete", [("legacy",True),("modern",True),("missing_modern_hash",False),("test_only",False),("missing",False),
    ("parent",False),("actor",False),("correlation",False),("target",False),("corrupt",False)])
def test_actual_cfs_caller_original_contract_reader_and_own_receipt_bridge_to_maintenance(monkeypatch,mode,complete):
    from shared_kernel.identities import ActorContext,CorrelationId
    service,calls,snapshot,before,own_hash,client_hash=legacy_maintenance(monkeypatch,mode)
    result=service.reconcile(FILE,actor=ActorContext("admin:7"),correlation_id=CorrelationId("readonly-bridge"))
    assert result["complete"] is complete
    assert own_hash!=client_hash and snapshot==before
    assert calls==([] if mode in {"modern","missing_modern_hash","target"} else [FILE])
    if mode=="test_only":
        assert result["references"]["frozen_completion_reference"]=="matched"
        assert result["references"]["external_completion_reference"]=="test_only"
    if not complete and mode!="test_only":assert result["references"]["external_completion_reference"]=="unavailable"


def test_legacy_receipt_storage_failure_keeps_original_typed_http_unavailable(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pymysql import OperationalError
    from api.routes.controlled_file_maintenance import router
    from api.dependencies.admin_auth import require_persisted_admin
    from api.dependencies.controlled_files import get_controlled_file_maintenance
    from subsystems.access.authentication_session import AdminPrincipal
    service,*_=legacy_maintenance(monkeypatch,"legacy")
    def unavailable(file_id):raise OperationalError(2003,"synthetic metadata unavailable")
    service.repository.get_committed_apply_evidence=unavailable
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[require_persisted_admin]=lambda:AdminPrincipal(7,"root","Root","system_admin",is_root=True)
    app.dependency_overrides[get_controlled_file_maintenance]=lambda:service
    response=TestClient(app).post("/api/v1/data-center/reconciliation/preview",json={"file_id":FILE})
    assert response.status_code==503
    error=response.json()["detail"]["error"]
    assert error["category"]=="unavailable" and error["code"]=="controlled_file_maintenance_unavailable" and error["retryable"] is True
