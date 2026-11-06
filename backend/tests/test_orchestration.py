from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analytics.registry import registry
from app.analytics.service import AnalyticalService
from app.core.config import Settings
from app.core.security import Principal
from app.db.models import (
    AnalysisSession,
    ConversationMessage,
    Dataset,
    MessageRole,
)
from app.orchestration.errors import LLMConfigurationError, OrchestrationError
from app.orchestration.schemas import AgentResponseOutput
from app.orchestration.service import ChatService
from app.orchestration.tools import build_registry_tools
from app.orchestration.workflow import TwoAgentWorkflow
from tests.conftest import TestSessionLocal


def test_registry_adapters_expose_only_registered_tools() -> None:
    tools = build_registry_tools(registry, lambda name, params: (uuid4(), {}))
    assert {tool.name for tool in tools} == {info.name for info in registry.list()}
    with pytest.raises(Exception):
        registry.get("execute_arbitrary_python")


def test_chat_service_persists_messages_and_enforces_session_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(database_url="sqlite://")
    analytical_service = AnalyticalService(settings, registry)
    service = ChatService(settings, registry, analytical_service)
    execution_id = uuid4()
    monkeypatch.setattr(
        service.workflow,
        "run",
        lambda question, context, execute: (
            AgentResponseOutput(
                answer="The verified mean is 2.",
                tools_used=["get_summary_statistics"],
            ),
            {"get_summary_statistics": {"numeric": {"value": {"mean": 2.0}}}},
            [("get_summary_statistics", execution_id)],
        ),
    )
    with TestSessionLocal() as db:
        dataset = Dataset(
            owner_id="test-user",
            original_filename="chat.csv",
            storage_key="chat.csv",
            file_format="csv",
            file_size_bytes=1,
        )
        db.add(dataset)
        db.commit()
        response = service.execute(
            dataset,
            "What is the mean?",
            None,
            db,
            Principal("test-user"),
        )
        assert response.answer == "The verified mean is 2."
        assert response.tools_used == ["get_summary_statistics"]
        messages = db.query(ConversationMessage).all()
        assert [message.role for message in messages] == [
            MessageRole.user,
            MessageRole.assistant,
        ]
        session = db.query(AnalysisSession).one()
        with pytest.raises(OrchestrationError):
            service.execute(
                dataset,
                "Should fail",
                session.id,
                db,
                Principal("another-user"),
            )


def test_missing_gemini_key_fails_before_provider_call() -> None:
    workflow = TwoAgentWorkflow(Settings(database_url="sqlite://"), registry)
    with pytest.raises(LLMConfigurationError):
        workflow.run("What is the mean?", "dataset context", lambda name, params: (uuid4(), {}))


def test_workflow_uses_two_mocked_agents_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeTask:
        def __init__(self, **kwargs: object) -> None:
            self.output = None

    class FakeCrew:
        def __init__(
            self, *, agents: list[object], tasks: list[FakeTask], **kwargs: object
        ) -> None:
            self.agents = agents
            self.tasks = tasks

        def kickoff(self) -> None:
            self.agents[0].kwargs["tools"][1]._run()
            self.tasks[1].output = SimpleNamespace(
                pydantic=AgentResponseOutput(
                    answer="Verified answer",
                    tools_used=["get_missing_values"],
                ),
                raw='{"answer":"Verified answer","tools_used":["get_missing_values"]}',
            )

    monkeypatch.setattr("app.orchestration.workflow.LLM", lambda **kwargs: object())
    monkeypatch.setattr("app.orchestration.workflow.Agent", FakeAgent)
    monkeypatch.setattr("app.orchestration.workflow.Task", FakeTask)
    monkeypatch.setattr("app.orchestration.workflow.Crew", FakeCrew)
    settings = Settings(database_url="sqlite://", gemini_api_key="test-key")
    execution_id = uuid4()
    result, verified, executions = TwoAgentWorkflow(settings, registry).run(
        "What is missing?",
        "dataset context",
        lambda name, params: (execution_id, {"columns": {}}),
    )
    assert result.answer == "Verified answer"
    assert verified == {"get_missing_values": {"columns": {}}}
    assert executions == [("get_missing_values", execution_id)]


def test_chat_endpoint_rejects_missing_gemini_key(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/datasets",
        files={"file": ("chat.csv", b"value\n1\n2\n", "text/csv")},
    )
    assert upload.status_code == 201
    response = client.post(
        f"/api/v1/datasets/{upload.json()['id']}/chat",
        json={"question": "What is the mean?"},
    )
    assert response.status_code == 503


def test_crew_tool_calls_the_supplied_registry_callback() -> None:
    execution_id = uuid4()
    calls: list[tuple[str, dict[str, object]]] = []

    def execute(name: str, params: dict[str, object]) -> tuple[object, dict[str, object]]:
        calls.append((name, params))
        return execution_id, {"ok": True}

    tool = next(
        item
        for item in build_registry_tools(registry, execute)
        if item.name == "get_missing_values"
    )
    result = tool._run(columns=["value"])
    assert calls == [("get_missing_values", {"columns": ["value"]})]
    assert str(execution_id) in result
