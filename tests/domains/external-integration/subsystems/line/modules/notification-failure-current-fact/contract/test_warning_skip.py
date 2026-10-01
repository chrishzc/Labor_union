"""LINE owner dispositions are snapshot-bound, audited, replayable and zero-provider-effect."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.line.notification_failure_current_fact import (
    LINE_NOTIFICATION_WARNING_SKIP_ACTION, LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureReason, LineNotificationUnresolvedReason,
)
from subsystems.line.notification_manual_replay_application import (
    LineNotificationManualReplayApplication, LineNotificationWarningSkipConflict,
)

ISSUE = 'ci_' + 'a' * 64
ACTOR = ActorContext('admin-1', ('line.config.manage',))
READBACK = LineNotificationFailureCurrentFactReadback('SYNTH-LINE',
    LineNotificationFailureReason.RECIPIENT_UNAVAILABLE, 'b' * 64, 1, True, 1, 1,
    (LineNotificationUnresolvedReason.EXACT_REPLAY_SUCCESSOR_MISSING,), True)


class Uow:
    def __init__(self):
        self.readback = READBACK
        self.saved = {}
        self.audit_events = []
        self.rechecks = []
        self.deleted = []
        self.commits = 0
        self.hooks = []
        self.locked = []
        self.force_incomplete_after_audit = False
        self.notification_rules = SimpleNamespace(current_failure_fact=self.current_fact)
        self.receipts = SimpleNamespace(get=lambda key, **_: self.saved.get(key.value),
                                        append=lambda receipt: self.saved.__setitem__(receipt.key.value, receipt))
        self.audit = SimpleNamespace(append=self.audit_events.append)
        self.anomaly_rechecks = SimpleNamespace(query_current=self.projection,
            lock_scope=lambda scope: self.locked.append(scope), release_scope=lambda scope: self.locked.remove(scope),
            delete_current=self.deleted.append, append_recheck_intent=self.rechecks.append)

    def projection(self, key, **_):
        if key in self.deleted:
            return None
        return SimpleNamespace(candidate=SimpleNamespace(definition_code='LINE-006', owner_domain='line',
            owner_root_type='notification_failure', subject_identity={
                'case_no': 'SYNTH-LINE', 'notification_reason': 'recipient_unavailable'}))

    def current_fact(self, query):
        acknowledged = any(event.aggregate_identity == self.readback.owner_snapshot_token for event in self.audit_events)
        return replace(self.readback, predicate_active=self.readback.predicate_active and not acknowledged,
            authoritative_complete=self.readback.authoritative_complete and not (acknowledged and self.force_incomplete_after_audit))

    def add_after_completion(self, hook):
        self.hooks.append(hook)

    def __enter__(self):
        self.before = (list(self.audit_events), list(self.rechecks), list(self.deleted), dict(self.saved))
        return self

    def __exit__(self, error_type, *_):
        if error_type:
            self.audit_events[:], self.rechecks[:], self.deleted[:], self.saved = self.before
        for hook in self.hooks:
            hook()
        self.hooks.clear()
        return False

    def commit(self):
        self.commits += 1


def application(uow):
    return LineNotificationManualReplayApplication(lambda: uow, lambda: datetime.now(UTC))


def apply(app, preview, **changes):
    values = dict(issue_key=ISSUE, expected_snapshot=preview.owner_snapshot_token,
                  approved_fingerprint=preview.preview_fingerprint, actor=ACTOR, idempotency_key=IdempotencyKey('skip-1'))
    return app.apply_warning_skip(**{**values, **changes})


def test_preview_cancel_zero_writes_confirm_exact_replay_audit_and_recheck():
    uow = Uow()
    app = application(uow)
    preview = app.preview_warning_skip(ISSUE, ACTOR)
    assert not uow.audit_events and uow.commits == 0
    receipt = apply(app, preview)
    assert receipt.issue_key == ISSUE and receipt.replayed is False
    assert len(uow.audit_events) == 1 and uow.audit_events[0].action == LINE_NOTIFICATION_WARNING_SKIP_ACTION
    assert uow.audit_events[0].actor_id == 'admin-1'
    assert uow.audit_events[0].aggregate_identity == READBACK.owner_snapshot_token
    assert uow.deleted == [ISSUE] and len(uow.rechecks) == 1 and uow.commits == 1
    assert uow.readback == READBACK and not uow.locked
    assert uow.current_fact(None).unresolved_source_count == 1
    assert apply(app, preview).replayed is True and uow.commits == 1
    with pytest.raises(LineNotificationWarningSkipConflict, match='idempotency_conflict'):
        apply(app, preview, expected_snapshot='c' * 64)


@pytest.mark.parametrize('change', [{'owner_snapshot_token': 'c' * 64}, {'authoritative_complete': False}, {'predicate_active': False}])
def test_changed_or_incomplete_owner_state_does_not_save_audit_or_delete_projection(change):
    uow = Uow()
    app = application(uow)
    preview = app.preview_warning_skip(ISSUE, ACTOR)
    uow.readback = replace(uow.readback, **change)
    with pytest.raises(LineNotificationWarningSkipConflict):
        apply(app, preview)
    assert not uow.audit_events and not uow.deleted and not uow.saved and uow.commits == 0
    assert not uow.locked


def test_incomplete_final_readback_rolls_back_audit_receipt_and_projection():
    uow = Uow()
    app = application(uow)
    preview = app.preview_warning_skip(ISSUE, ACTOR)
    uow.force_incomplete_after_audit = True
    with pytest.raises(LineNotificationWarningSkipConflict, match='readback_conflict'):
        apply(app, preview)
    assert not uow.audit_events and not uow.saved and not uow.deleted and not uow.rechecks
    assert uow.commits == 0 and not uow.locked


def test_later_owner_snapshot_remains_actionable_after_an_earlier_skip():
    uow = Uow()
    app = application(uow)
    apply(app, app.preview_warning_skip(ISSUE, ACTOR))
    assert uow.current_fact(None).predicate_active is False
    uow.readback = replace(uow.readback, owner_snapshot_token='c' * 64, owner_version=2)
    assert uow.current_fact(None).predicate_active is True
