"""Model-adapter provenance and fallback tests."""

import json
from types import SimpleNamespace

import openai

from app.diagnosis.adapter import OpenAICompatibleModelAdapter
from app.diagnosis.model import DiagnosisContext


def _context() -> DiagnosisContext:
    return DiagnosisContext(
        incident_id="incident-1",
        diagnosis_run_id="run-1",
        ontology_version="paytrace.ontology.v1",
    )


def test_missing_model_configuration_records_fallback_provenance():
    adapter = OpenAICompatibleModelAdapter()
    report = adapter.generate(_context())
    assert report.adapter_name == "RuleBasedModelAdapter"
    assert report.model_name == "rule_based"
    assert report.fallback_used is True
    assert report.fallback_reason == "MODEL_NOT_CONFIGURED"
    assert adapter.last_fallback_reason == "MODEL_NOT_CONFIGURED"
    assert adapter.last_usage is None


def test_model_call_failure_records_stable_reason_without_exception_text(monkeypatch):  # noqa: ANN001
    class FailingCompletions:
        def create(self, **kwargs):  # noqa: ANN003, ANN201
            del kwargs
            raise RuntimeError("secret upstream detail")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FailingCompletions()),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: fake_client)
    adapter = OpenAICompatibleModelAdapter(
        base_url="https://model.example/v1",
        api_key="synthetic-test-key",  # noqa: S106
        model="test-model",
    )
    report = adapter.generate(_context())
    assert report.fallback_used is True
    assert report.fallback_reason == "MODEL_CALL_FAILED"
    assert "secret" not in json.dumps(report.model_dump(mode="json"))


def test_successful_model_call_records_adapter_and_tokens(monkeypatch):  # noqa: ANN001
    body = json.dumps(
        {
            "status": "SUCCEEDED",
            "summary": "No anomaly detected.",
            "anomalous_stages": [],
            "root_causes": [],
            "total_estimated_lost_intents": 0,
            "explained_lost_intents": 0,
            "unexplained_lost_intents": 0,
            "missing_data": [],
            "alternative_explanations": [],
            "recommended_actions": [],
        }
    )

    class SuccessfulCompletions:
        def create(self, **kwargs):  # noqa: ANN003, ANN201
            del kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
                usage=SimpleNamespace(prompt_tokens=17, completion_tokens=9),
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SuccessfulCompletions()),
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: fake_client)
    adapter = OpenAICompatibleModelAdapter(
        base_url="https://model.example/v1",
        api_key="synthetic-test-key",  # noqa: S106
        model="test-model",
    )
    report = adapter.generate(_context())
    assert report.adapter_name == "OpenAICompatibleModelAdapter"
    assert report.model_name == "test-model"
    assert report.fallback_used is False
    assert report.fallback_reason is None
    assert report.input_tokens == 17
    assert report.output_tokens == 9
