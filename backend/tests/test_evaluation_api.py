"""Integration coverage for the M3 EvaluationRun API."""

from unittest.mock import patch

from httpx import AsyncClient

_PAYLOAD = {
    "model_mode": "B0",
    "prompt_version": "rule-based.v1",
    "scenario_kinds": ["mixed_failure", "data_gap"],
    "seed": 42,
    "num_intents": 20,
}


class TestEvaluationAPI:
    async def test_create_is_idempotent_and_listable(self, client: AsyncClient) -> None:
        with patch("app.api.v1.evaluations.run_evaluation_task.delay") as mock_delay:
            mock_delay.return_value.id = "evaluation-task-1"
            first = await client.post(
                "/api/v1/evaluation-runs",
                headers={"Idempotency-Key": "eval-api-001"},
                json=_PAYLOAD,
            )

        assert first.status_code == 202
        first_body = first.json()
        assert first_body["status"] == "QUEUED"
        assert mock_delay.call_count == 1

        duplicate = await client.post(
            "/api/v1/evaluation-runs",
            headers={"Idempotency-Key": "eval-api-001"},
            json=_PAYLOAD,
        )
        assert duplicate.status_code == 202
        duplicate_body = duplicate.json()
        assert duplicate_body["evaluation_run_id"] == first_body["evaluation_run_id"]
        assert "Existing evaluation run" in duplicate_body["message"]

        listed = await client.get("/api/v1/evaluation-runs?page=1&page_size=10")
        assert listed.status_code == 200
        listed_body = listed.json()
        assert listed_body["total"] >= 1
        item = next(
            item for item in listed_body["items"] if item["idempotency_key"] == "eval-api-001"
        )
        assert item["id"] == first_body["evaluation_run_id"]

        detail = await client.get(f"/api/v1/evaluation-runs/{first_body['evaluation_run_id']}")
        assert detail.status_code == 200
        assert detail.json()["celery_task_id"] == "evaluation-task-1"

    async def test_invalid_scenario_kind_is_rejected_without_dispatch(
        self, client: AsyncClient
    ) -> None:
        with patch("app.api.v1.evaluations.run_evaluation_task.delay") as mock_delay:
            response = await client.post(
                "/api/v1/evaluation-runs",
                headers={"Idempotency-Key": "eval-api-invalid"},
                json={**_PAYLOAD, "scenario_kinds": ["not-a-scenario"]},
            )

        assert response.status_code == 422
        assert "not-a-scenario" in response.json()["detail"]
        mock_delay.assert_not_called()

    async def test_dispatch_failure_is_persisted(self, client: AsyncClient) -> None:
        with patch(
            "app.api.v1.evaluations.run_evaluation_task.delay",
            side_effect=RuntimeError("broker unavailable"),
        ):
            response = await client.post(
                "/api/v1/evaluation-runs",
                headers={"Idempotency-Key": "eval-api-dispatch-failure"},
                json=_PAYLOAD,
            )

        assert response.status_code == 500
        listed = await client.get("/api/v1/evaluation-runs?page=1&page_size=10")
        assert listed.status_code == 200
        item = next(
            item
            for item in listed.json()["items"]
            if item["idempotency_key"] == "eval-api-dispatch-failure"
        )
        assert item["status"] == "DISPATCH_FAILED"
        assert item["error_type"] == "CELERY_DISPATCH_FAILED"
