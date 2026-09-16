from pathlib import Path


PAGE = (
    Path(__file__).resolve().parents[6]
    / "line"
    / "static"
    / "service_help.html"
).read_text(encoding="utf-8")


def test_liff_question_carries_verified_identity_for_persisted_answer() -> None:
    assert "liff.getIDToken()" in PAGE
    assert "interaction_id: interactionId" in PAGE
    assert "line_id_token: token" in PAGE
    assert "answer_receipt_id" in PAGE


def test_answer_feedback_uses_existing_preview_and_apply_contract() -> None:
    assert "'/api/v1/line/feedback/preview'" in PAGE
    assert "'/api/v1/line/feedback'" in PAGE
    assert "knowledge-answer-receipt:${answerData.answer_receipt_id}" in PAGE
    assert "outcome === 'resolved'" in PAGE
    assert "outcome === 'unresolved'" in PAGE


def test_unresolved_copy_only_claims_ticket_when_receipt_contains_ticket_id() -> None:
    assert "Number.isInteger(result.data.ticket_id) && result.data.ticket_id > 0" in PAGE
    assert "客服需求已建立" in PAGE
    assert "客服需求狀態請稍後確認" in PAGE
