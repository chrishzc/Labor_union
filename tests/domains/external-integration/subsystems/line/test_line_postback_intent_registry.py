from subsystems.line import postback_intent_registry as registry


def test_matching_willingness_uses_exact_plan_segment_and_event_identity(monkeypatch):
    captured = {}

    def record(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status": "recorded"}

    monkeypatch.setattr(registry, "record_matching_plan_willingness", record)

    result = registry.handle_matching_willingness(
        {"action": "willing", "case_no": "C-1", "plan_id": "7", "segment_id": "9"},
        "line-event-1",
        "U-staff",
    )

    assert result == {"status": "recorded"}
    assert captured["args"] == ("C-1", 7, 9, "willing", "line-event-1", "line:U-staff")
    assert captured["kwargs"]["reply_to_user_id"] == "U-staff"


def test_matching_willingness_rejects_incomplete_identity():
    try:
        registry.handle_matching_willingness(
            {"action": "willing", "case_no": "C-1", "plan_id": "7"},
            "line-event-1",
            "U-staff",
        )
    except registry.LinePostbackIntentError as error:
        assert "segment_id" in str(error)
    else:
        raise AssertionError("incomplete LINE identity must fail closed")
