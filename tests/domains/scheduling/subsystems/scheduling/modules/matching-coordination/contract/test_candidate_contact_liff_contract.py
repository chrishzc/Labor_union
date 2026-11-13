"""Retired candidate coordination links give guidance without accepting any input."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import line_candidate_contact, line_mobile_admin, notification_task_actions, notification_tasks


def test_candidate_form_links_are_gone_and_legacy_writers_are_unreachable():
    app = FastAPI()
    for router in (
        line_candidate_contact.page_router,
        line_mobile_admin.router,
        notification_task_actions.router,
        notification_tasks.router,
    ):
        app.include_router(router)
    with TestClient(app) as client:
        for page in ("/line-candidate-contact", "/line-candidate-contact-customer"):
            response = client.get(page + "?ref=irrelevant")
            assert response.status_code == 410
            assert "直接聯絡工會" in response.text
            assert "<form" not in response.text
        for endpoint in (
            "/api/v1/line/candidate-contact/submit",
            "/api/v1/line/candidate-contact/customer/submit",
            "/api/v1/line/mobile-admin/candidate-information/1/send",
            "/api/v1/line/mobile-admin/matching-followups/1/terms/apply",
            "/api/v1/line/mobile-admin/matching-followups/1/recontact/apply",
            "/api/v1/line/notification-task-actions/information/1/send",
            "/api/v1/line/notification-task-actions/adjustments/1/recontact/apply",
        ):
            assert client.post(endpoint, json={}).status_code == 404
