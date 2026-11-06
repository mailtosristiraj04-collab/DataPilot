from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    session_id: UUID | None = None


class AgentResponseOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    tools_used: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class ExecutionReference(BaseModel):
    execution_id: UUID
    tool_name: str


class ChatResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    answer: str
    tools_used: list[str]
    executions: list[ExecutionReference]
    limitations: list[str]
    verified_results: dict[str, Any]
