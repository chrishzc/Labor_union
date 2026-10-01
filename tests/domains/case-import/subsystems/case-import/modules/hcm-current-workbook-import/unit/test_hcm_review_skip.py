"""Audited disposition is limited to a current missing rejection reason."""
from contextlib import AbstractContextManager
from dataclasses import replace

import pytest

from domains.case_import.hcm_import_review import HCM_SKIP_REJECT_REASON_PATH
from subsystems.case_import.hcm_resubmission_workflow import (
    ApplyHcmReviewSkip, HcmResubmissionConflict, HcmResubmissionWorkflow, HcmReviewSkipFacts,
)


class Repository:
    def __init__(self):
        self.facts = HcmReviewSkipFacts('review-1', 'SYNTH-1', 0, 'a' * 64,
                                       ('hcm_field_missing:不符合原因', 'hcm_field_missing:姓名'),
                                       None, False, True)
        self.receipts = {}
        self.events = []
        self.outbox = []

    def load_skip_facts(self, identity, *, for_update):
        assert identity == self.facts.review_identity
        return self.facts

    def find_receipt(self, key, *, for_update=False):
        return self.receipts.get(key)

    def apply_skip(self, facts, request):
        self.events.append((facts, request))
        self.facts = replace(facts, review_version=facts.review_version + 1, already_skipped=True)
        return 'event-1'

    def save_receipt(self, key, command_fingerprint, preview_fingerprint, receipt):
        self.receipts[key] = command_fingerprint, receipt

    def append_outbox(self, event_identity, review_identity):
        self.outbox.append((event_identity, review_identity))


class Uow(AbstractContextManager):
    commits = 0
    def __exit__(self, *args):
        return False
    def commit(self):
        self.commits += 1


def command(preview, **changes):
    return replace(ApplyHcmReviewSkip(preview.review_identity, preview.review_version,
                                    preview.preview_fingerprint, 'skip-key-1', 'admin:1', 'corr-1'), **changes)


def test_preview_zero_writes_apply_one_commit_exact_replay_and_audited_field_only():
    repository = Repository()
    uow = Uow()
    workflow = HcmResubmissionWorkflow(repository, lambda: uow)
    preview = workflow.preview_skip('review-1')
    assert not repository.events and not repository.receipts and uow.commits == 0
    receipt = workflow.apply_skip(command(preview))
    assert receipt.target_fields == (HCM_SKIP_REJECT_REASON_PATH,)
    assert repository.facts.reject_reason is None
    assert repository.facts.issue_codes == ('hcm_field_missing:不符合原因', 'hcm_field_missing:姓名')
    assert uow.commits == 1 and len(repository.events) == 1 and len(repository.outbox) == 1
    assert repository.events[0][1].actor == 'admin:1'
    assert workflow.apply_skip(command(preview)).replayed is True
    assert uow.commits == 1 and len(repository.events) == 1
    with pytest.raises(HcmResubmissionConflict, match='idempotency_conflict'):
        workflow.apply_skip(command(preview, actor='admin:2'))


@pytest.mark.parametrize('change', [
    {'review_version': 1}, {'reject_reason': '已補原因'}, {'already_skipped': True}, {'is_current': False},
])
def test_changed_review_or_corrected_reason_is_a_typed_conflict_without_writes(change):
    repository = Repository()
    uow = Uow()
    workflow = HcmResubmissionWorkflow(repository, lambda: uow)
    preview = workflow.preview_skip('review-1')
    repository.facts = replace(repository.facts, **change)
    with pytest.raises(HcmResubmissionConflict):
        workflow.apply_skip(command(preview))
    assert not repository.events and uow.commits == 0


def test_other_missing_fields_and_invalid_reason_cannot_use_skip():
    repository = Repository()
    workflow = HcmResubmissionWorkflow(repository, Uow)
    for codes in (('hcm_field_missing:姓名',), ('hcm_field_invalid:不符合原因',)):
        repository.facts = replace(repository.facts, issue_codes=codes)
        with pytest.raises(ValueError, match='field_not_allowed'):
            workflow.preview_skip('review-1')
    assert not repository.events
