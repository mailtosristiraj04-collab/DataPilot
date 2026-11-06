import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.registry import ToolRegistry
from app.analytics.service import AnalyticalService
from app.core.config import Settings
from app.core.security import Principal
from app.db.models import (
    AnalysisSession,
    AnalysisSessionStatus,
    ConversationMessage,
    Dataset,
    MessageRole,
)
from app.orchestration.errors import OrchestrationError
from app.orchestration.schemas import ChatResponse, ExecutionReference
from app.orchestration.workflow import TwoAgentWorkflow

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        analytical_service: AnalyticalService,
    ) -> None:
        self.workflow = TwoAgentWorkflow(settings, registry)
        self.analytical_service = analytical_service

    def execute(
        self,
        dataset: Dataset,
        question: str,
        session_id: UUID | None,
        db: Session,
        principal: Principal,
    ) -> ChatResponse:
        session = self._get_or_create_session(dataset, session_id, db, principal)
        user_message = ConversationMessage(
            session_id=session.id, role=MessageRole.user, content=question
        )
        db.add(user_message)
        db.commit()
        try:
            dataframe_context = (
                f"dataset_id={dataset.id}; format={dataset.file_format}; "
                f"rows={dataset.row_count}; columns={dataset.column_count}"
            )
            result, verified_results, executions = self.workflow.run(
                question,
                dataframe_context,
                lambda tool_name, parameters: self.analytical_service.execute(
                    dataset,
                    tool_name,
                    parameters,
                    db,
                    principal,
                    session_id=session.id,
                    agent_name="Data Analyst",
                ),
            )
            assistant_message = ConversationMessage(
                session_id=session.id, role=MessageRole.assistant, content=result.answer
            )
            db.add(assistant_message)
            db.commit()
            return ChatResponse(
                session_id=session.id,
                message_id=assistant_message.id,
                answer=result.answer,
                tools_used=[tool_name for tool_name, _ in executions],
                executions=[
                    ExecutionReference(execution_id=execution_id, tool_name=tool_name)
                    for tool_name, execution_id in executions
                ],
                limitations=result.limitations,
                verified_results=verified_results,
            )
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def _get_or_create_session(
        dataset: Dataset,
        session_id: UUID | None,
        db: Session,
        principal: Principal,
    ) -> AnalysisSession:
        if session_id is not None:
            session = db.scalar(
                select(AnalysisSession).where(
                    AnalysisSession.id == session_id,
                    AnalysisSession.dataset_id == dataset.id,
                    AnalysisSession.owner_id == principal.principal_id,
                    AnalysisSession.status == AnalysisSessionStatus.active,
                )
            )
            if session is None:
                raise OrchestrationError("Analysis session not found")
            return session
        session = AnalysisSession(
            owner_id=principal.principal_id,
            dataset_id=dataset.id,
            status=AnalysisSessionStatus.active,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session
