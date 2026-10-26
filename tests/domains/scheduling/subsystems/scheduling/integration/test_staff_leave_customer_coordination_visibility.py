"""Retired customer leave controls are consumed without any effect."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from subsystems.line.staff_leave_customer_coordination import StaffLeaveCustomerCoordinationApplication

@pytest.mark.parametrize('source',['user','group'])
@pytest.mark.parametrize('decision',['agree_defer','reject_substitution'])
def test_old_card_has_no_reply_or_write_for_any_actor_and_replay(source,decision):
    app=StaffLeaveCustomerCoordinationApplication(Mock(),Mock(),Mock())
    unit=Mock()
    inbox=SimpleNamespace(event=SimpleNamespace(source=SimpleNamespace(source_type=source),payload_json=json.dumps({'postback':{'data':'leave_customer_decision:request_id=17&version=4&case_no=CASE&decision='+decision}})))
    assert app.handle_postback(inbox,unit)
    assert app.handle_postback(inbox,unit)
    assert unit.mock_calls==[]
