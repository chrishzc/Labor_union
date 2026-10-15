"""A current caregiver withdrawal requires replacement without rewriting assignments."""

import pytest

from subsystems.orders.core_stage_projection_query import project_core_stage_page
from subsystems.orders.stage_projection_query import OrderStageProjectionQueryService, StageProjectionQuery
from tests.domains.orders.subsystems.orders.integration.test_orders_stage_projection import BUSINESS_CLOCK, _Repository, _row


@pytest.mark.parametrize("assignment_count", [0, 1])
def test_current_consent_change_does_not_reuse_old_customer_acceptance(assignment_count):
    row = _row()
    row.update(matching_unwilling_count=1, assignment_count=assignment_count)
    page = OrderStageProjectionQueryService(_Repository((row,)), BUSINESS_CLOCK).query(StageProjectionQuery(50))
    recommendation = project_core_stage_page(page).items[0].core_stages[4]
    assert recommendation.status == "blocked"
    assert recommendation.blockers[0].code == "recommendation_caregiver_unwilling"
    assert page.items[0].current_step_ordinal == 5
    assert row["assignment_count"] == assignment_count
