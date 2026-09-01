"""Application service for issue/redeem/revoke/readback of safe review links."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable

from subsystems.line.safe_review_link_contracts import (
    IssueSafeReviewLink,
    QuerySafeReviewLink,
    RedeemSafeReviewLink,
    RevokeSafeReviewLink,
    SafeReviewLinkError,
    SafeReviewLinkReceipt,
    SafeReviewLinkState,
    SafeReviewLinkView,
    command_fingerprint,
)


class SafeReviewLinkApplication:
    def __init__(self, unit_of_work_factory: Callable[[], object], now: Callable[[], datetime]):
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def issue(self, command: IssueSafeReviewLink) -> tuple[SafeReviewLinkReceipt, str]:
        if command.required_capability not in command.actor.permission_scope:
            raise SafeReviewLinkError("safe_review_link_wrong_actor", "issuer lacks required review capability")
        digest = _digest(command.raw_token)
        fingerprint = command_fingerprint(command).value
        with self._unit_of_work_factory() as reader:
            existing = reader.safe_review_links.load_receipt(command.idempotency_key.value)
            if existing is not None:
                _check_fingerprint(existing, fingerprint)
                return _receipt_from_row(existing), ""
        def mutate(uow):
            repo = uow.safe_review_links
            existing = repo.load_receipt(command.idempotency_key.value, for_update=True)
            if existing is not None:
                _check_fingerprint(existing, fingerprint)
                return _receipt_from_row(existing), ""
            now = _utc(self._now())
            link_pk = repo.insert_link(
                link_id=command.link_id,
                token_digest=digest,
                canonical_internal_target=command.canonical_internal_target,
                target_version=command.target_version,
                source_alert_identity=command.source_alert_identity,
                allowed_actor_ref=command.allowed_actor_ref,
                required_capability=command.required_capability,
                issued_at=now,
                expires_at=now + timedelta(seconds=command.ttl_seconds),
                idempotency_key=command.idempotency_key.value,
                correlation_id=command.correlation_id.value,
            )
            repo.insert_event(link_pk, "issued", command.actor.actor_id, "issued", command.target_version,
                              command.idempotency_key.value, command.correlation_id.value,
                              {"target": command.canonical_internal_target})
            repo.insert_outbox(link_pk, command.idempotency_key.value, command.correlation_id.value,
                               {"link_id": command.link_id, "target": command.canonical_internal_target,
                                "source_alert_identity": command.source_alert_identity})
            view = _view(repo.get_link(command.link_id))
            receipt = SafeReviewLinkReceipt(command.link_id, SafeReviewLinkState.ISSUED, False,
                                            command.idempotency_key.value, view.root_version, view)
            repo.insert_receipt(command.idempotency_key.value, fingerprint, "issued", _receipt_payload(receipt), link_pk)
            return receipt, command.raw_token
        return _mutate(self._unit_of_work_factory, mutate)

    def query(self, command: QuerySafeReviewLink) -> SafeReviewLinkView:
        with self._unit_of_work_factory() as uow:
            row = uow.safe_review_links.get_link(command.link_id)
            if row is None:
                raise SafeReviewLinkError("safe_review_link_not_found", "safe review link not found")
            return _view(row)

    def redeem(self, command: RedeemSafeReviewLink) -> SafeReviewLinkReceipt:
        fingerprint = command_fingerprint(command).value
        with self._unit_of_work_factory() as reader:
            existing = reader.safe_review_links.load_receipt(command.idempotency_key.value)
            if existing is not None:
                _check_fingerprint(existing, fingerprint)
                return _receipt_from_row(existing)
        def mutate(uow):
            repo = uow.safe_review_links
            existing = repo.load_receipt(command.idempotency_key.value, for_update=True)
            if existing is not None:
                _check_fingerprint(existing, fingerprint)
                return _receipt_from_row(existing)
            row = repo.get_link(command.link_id, for_update=True)
            if row is None:
                raise SafeReviewLinkError("not_found", "safe review link not found")
            status = SafeReviewLinkState(str(row["status"]))
            now = _utc(self._now())
            if status is SafeReviewLinkState.ISSUED and now >= _utc(row["expires_at_utc"]):
                repo.transition(row["id"], "expired", now)
                repo.insert_event(row["id"], "expired", command.actor.actor_id, "expired", row["target_version"],
                                  command.idempotency_key.value, command.correlation_id.value, {})
                view = _view(repo.get_link(command.link_id, for_update=True))
                receipt = SafeReviewLinkReceipt(command.link_id, SafeReviewLinkState.EXPIRED, False,
                                                command.idempotency_key.value, view.root_version, view)
                repo.insert_receipt(command.idempotency_key.value, fingerprint, "expired", _receipt_payload(receipt), row["id"])
                raise _CommittedFailure(SafeReviewLinkError("safe_review_link_expired", "safe review link has expired"))
            if status is SafeReviewLinkState.REDEEMED:
                raise SafeReviewLinkError("safe_review_link_replayed", "safe review link was already redeemed")
            if status is SafeReviewLinkState.EXPIRED:
                raise SafeReviewLinkError("safe_review_link_expired", "safe review link has expired")
            if status is SafeReviewLinkState.REVOKED:
                raise SafeReviewLinkError("safe_review_link_revoked", "safe review link has been revoked")
            if _digest(command.raw_token) != str(row["token_digest"]):
                raise SafeReviewLinkError("safe_review_link_wrong_actor", "safe review link token is invalid")
            if command.actor.actor_id != str(row["allowed_actor_ref"]):
                raise SafeReviewLinkError("safe_review_link_wrong_actor", "actor is not allowed to redeem this link")
            if command.capability not in command.actor.permission_scope:
                raise SafeReviewLinkError("safe_review_link_wrong_actor", "actor lacks required review capability")
            if command.capability != str(row["required_capability"]):
                raise SafeReviewLinkError("safe_review_link_wrong_actor", "actor capability is not allowed")
            if command.current_target != str(row["canonical_internal_target"]):
                raise SafeReviewLinkError("safe_review_link_target_stale", "review target is stale")
            if command.current_target_version != int(row["target_version"]):
                raise SafeReviewLinkError("safe_review_link_version_conflict", "review target version is stale")
            repo.transition(row["id"], "redeemed", now)
            repo.insert_event(row["id"], "redeemed", command.actor.actor_id, "redeemed", row["target_version"],
                              command.idempotency_key.value, command.correlation_id.value, {})
            view = _view(repo.get_link(command.link_id, for_update=True))
            receipt = SafeReviewLinkReceipt(command.link_id, SafeReviewLinkState.REDEEMED, False,
                                            command.idempotency_key.value, view.root_version, view)
            repo.insert_receipt(command.idempotency_key.value, fingerprint, "redeemed", _receipt_payload(receipt), row["id"])
            return receipt
        return _mutate(self._unit_of_work_factory, mutate)

    def revoke(self, command: RevokeSafeReviewLink) -> SafeReviewLinkReceipt:
        fingerprint = command_fingerprint(command).value
        def mutate(uow):
            repo = uow.safe_review_links
            existing = repo.load_receipt(command.idempotency_key.value, for_update=True)
            if existing is not None:
                _check_fingerprint(existing, fingerprint)
                return _receipt_from_row(existing)
            row = repo.get_link(command.link_id, for_update=True)
            if row is None:
                raise SafeReviewLinkError("safe_review_link_not_found", "safe review link not found")
            status = SafeReviewLinkState(str(row["status"]))
            if status is SafeReviewLinkState.REDEEMED:
                raise SafeReviewLinkError("safe_review_link_replayed", "redeemed link cannot be revoked")
            if status is SafeReviewLinkState.EXPIRED:
                raise SafeReviewLinkError("safe_review_link_expired", "expired link cannot be revoked")
            if status is SafeReviewLinkState.REVOKED:
                raise SafeReviewLinkError("safe_review_link_revoked", "safe review link has already been revoked")
            now = _utc(self._now())
            repo.transition(row["id"], "revoked", now)
            repo.insert_event(row["id"], "revoked", command.actor.actor_id, "revoked", row["target_version"],
                              command.idempotency_key.value, command.correlation_id.value,
                              {"reason": command.reason})
            view = _view(repo.get_link(command.link_id, for_update=True))
            receipt = SafeReviewLinkReceipt(command.link_id, SafeReviewLinkState.REVOKED, False,
                                            command.idempotency_key.value, view.root_version, view)
            repo.insert_receipt(command.idempotency_key.value, fingerprint, "revoked", _receipt_payload(receipt), row["id"])
            return receipt
        return _mutate(self._unit_of_work_factory, mutate)


def _mutate(unit_of_work_factory, operation):
    uow = unit_of_work_factory()
    uow.__enter__()
    try:
        result = operation(uow)
        uow.commit()
        uow.__exit__(None, None, None)
        return result
    except _CommittedFailure as committed:
        uow.commit()
        uow.__exit__(None, None, None)
        raise committed.error
    except Exception as error:
        try:
            uow.__exit__(type(error), error, error.__traceback__)
        finally:
            raise


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _view(row) -> SafeReviewLinkView:
    return SafeReviewLinkView(
        str(row["link_id"]), SafeReviewLinkState(str(row["status"])),
        str(row["canonical_internal_target"]), int(row["target_version"]),
        str(row["source_alert_identity"]), _utc(row["expires_at_utc"]),
        _utc(row["redeemed_at_utc"]) if row.get("redeemed_at_utc") else None,
        _utc(row["revoked_at_utc"]) if row.get("revoked_at_utc") else None,
        int(row["root_version"]),
    )


def _receipt_payload(receipt: SafeReviewLinkReceipt) -> dict:
    return {"link_id": receipt.link_id, "status": receipt.outcome.value,
            "receipt_id": receipt.receipt_id, "root_version": receipt.root_version,
            "canonical_internal_target": receipt.view.canonical_internal_target,
            "target_version": receipt.view.target_version,
            "expires_at_utc": receipt.view.expires_at_utc.isoformat(),
            "source_alert_identity": receipt.view.source_alert_identity}


def _receipt_from_row(row) -> SafeReviewLinkReceipt:
    payload = row.get("result_snapshot") or {}
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    expires = payload.get("expires_at_utc")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    expires = expires or row.get("created_at_utc") or datetime.now(timezone.utc)
    return SafeReviewLinkReceipt(str(payload.get("link_id") or row.get("link_id")),
                                 SafeReviewLinkState(str(row["outcome"])), True,
                                 str(row["idempotency_key"]), int(payload.get("root_version", 0)),
                                 SafeReviewLinkView(str(payload.get("link_id") or row.get("link_id")),
                                                    SafeReviewLinkState(str(row["outcome"])),
                                                    str(payload.get("canonical_internal_target", "masked")), int(payload.get("target_version", 0)),
                                                    str(payload.get("source_alert_identity", "masked")), _utc(expires),
                                                    None, None, int(payload.get("root_version", 0))))


def _check_fingerprint(row, expected: str) -> None:
    if str(row["command_fingerprint"]) != expected:
        raise SafeReviewLinkError("safe_review_link_idempotency_mismatch", "idempotency key was reused with a different command")


class _CommittedFailure(Exception):
    def __init__(self, error: SafeReviewLinkError) -> None:
        super().__init__(str(error))
        self.error = error


__all__ = ["SafeReviewLinkApplication"]
