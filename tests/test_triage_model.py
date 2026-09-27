import triage_model


def test_red_flag_can_never_be_downgraded(monkeypatch):
    monkeypatch.setattr(triage_model, "TRIAGE_BACKEND", "openai")
    monkeypatch.setattr(triage_model, "_openai", lambda m, c: (
        triage_model.TriageResult(urgency="low", advice="Drink water and rest."),
        {"tokens_in": 10, "tokens_out": 5}))
    result = triage_model.triage_model("heavy bleeding after a fall", "Kisii")
    assert result["urgency"] == "high"
    assert result["advice"].startswith("Warning signs reported")


def test_malformed_model_output_becomes_model_unavailable(monkeypatch):
    def bad(message, county):
        return triage_model.TriageResult.model_validate_json('{"urgency": "extreme"}'), {}
    monkeypatch.setattr(triage_model, "TRIAGE_BACKEND", "openai")
    monkeypatch.setattr(triage_model, "_openai", bad)
    try:
        triage_model.triage_model("I have a mild cough", "Kisumu")
    except triage_model.ModelUnavailable as exc:
        assert "malformed" in str(exc)
    else:
        raise AssertionError("expected ModelUnavailable")
