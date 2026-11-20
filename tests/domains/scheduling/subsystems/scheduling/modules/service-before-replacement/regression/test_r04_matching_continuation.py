"""R-04 matching continuation for candidate contact and customer confirmation."""

from dataclasses import replace

import pytest

from infrastructure.mysql.replacement_matching_query import candidate_contact_open, replacement_matching_open
from domains.scheduling.matching_communication import MatchingCommunicationStaleError
from subsystems.scheduling.matching_notification_application import _require_sendable_state


class Cursor:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def execute(self, sql, args):
        self.queries.append((sql, args))

    def fetchone(self):
        return self.row


@pytest.mark.parametrize('status,blocker,allowed', [
    ('洽談中', None, True), ('訂單成立', None, True),
    ('訂單成立', 'candidate_contact_order_not_negotiating', False),
    ('服務中', 'candidate_matching_service_started', False),
    ('訂單取消', 'candidate_contact_order_not_negotiating', False),
])
def test_candidate_contact_requires_current_r04_receipt_for_established_case(status, blocker, allowed):
    cursor = Cursor({'blocker': blocker})
    assert candidate_contact_open(cursor, 'CASE-1', status) is allowed
    if status == '訂單成立':
        sql, args = cursor.queries[0]
        assert 'generation.id=aggregate.effective_generation_id' in sql
        assert 'event.replacement_generation_id=generation.id' in sql
        assert 'scheduling_service_before_replacement_receipts' in sql
        assert 'assignment.generation_id=generation.id' in sql
        assert args == ('CASE-1',)
    elif status not in {'洽談中', '訂單成立'}:
        assert not cursor.queries


def test_old_replacement_no_longer_authorizes_matching_after_current_generation_has_assignments():
    assert not replacement_matching_open(Cursor({'blocker': 'candidate_matching_assignment_present'}), 'CASE-1')


@pytest.mark.parametrize('replacement_open', [False, True])
def test_new_confirmation_send_requires_the_committed_replacement_round(replacement_open):
    from subsystems.scheduling.matching_notification_contracts import MatchingContactState
    from domains.scheduling.matching_communication import MatchingPlanReference, CustomerMatchingDecision
    state = MatchingContactState(MatchingPlanReference('CASE-1', 52, 0), 'proposed', True,
                                 '訂單成立', None, CustomerMatchingDecision.PENDING, None, (),
                                 replacement_matching_open=replacement_open)
    if replacement_open:
        _require_sendable_state(state, 0)
        with pytest.raises(MatchingCommunicationStaleError):
            _require_sendable_state(replace(state, plan_is_active=False), 0)
    else:
        with pytest.raises(MatchingCommunicationStaleError):
            _require_sendable_state(state, 0)


@pytest.mark.parametrize('replacement_open', [False, True])
def test_real_customer_confirmation_preview_uses_same_replacement_gate_as_send(replacement_open):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from domains.line.identities import LineUserId
    from domains.scheduling.matching_communication import MatchingPlanReference, CustomerMatchingDecision, CaregiverWillingness
    from shared_kernel.identities import ActorContext
    from subsystems.scheduling.matching_notification_contracts import MatchingContactState, MatchingSegmentContact
    from subsystems.scheduling.matching_notification_application import MatchingNotificationApplication

    state = MatchingContactState(MatchingPlanReference('CASE-1', 52, 0), 'proposed', True,
        '訂單成立', LineUserId('U-synthetic-customer'), CustomerMatchingDecision.PENDING, None,
        (MatchingSegmentContact(72, 1, 2, 'Synthetic successor', None, '2026-11-01', '2026-11-05', CaregiverWillingness.WILLING),),
        replacement_matching_open=replacement_open)
    repository = SimpleNamespace(
        get_contact_state=lambda *args, **kwargs: state,
        customer_confirmation_preview=lambda *args: {
            'blockers': [], 'order_information_1_ready': True, 'order_information_2_ready': True,
            'weekly_service_ready': True, 'weekly_service_row_count': 0,
            'order_information_1': [], 'order_information_2': [], 'weekly_service_rows': [],
            'caregiver_resumes': [{'staff_id': 2, 'staff_name': 'Synthetic successor', 'ready': True,
                                  'filename': 'synthetic-resume.pdf', 'version': 1, 'blocker': None}],
        },
    )
    application = MatchingNotificationApplication(lambda: nullcontext(SimpleNamespace(matching_notifications=repository)),
        lambda: None, availability_validator=lambda state: None)
    preview = application.preview_customer_confirmation(ActorContext('operator:1', ('line.matching.read',)), state.plan)
    assert preview.send_allowed is replacement_open
