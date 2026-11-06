import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from crewai import LLM, Agent, Crew, Process, Task

from app.analytics.errors import AnalyticalError
from app.analytics.registry import ToolRegistry
from app.core.config import Settings
from app.orchestration.errors import (
    LLMConfigurationError,
    LLMExecutionError,
    ToolExecutionError,
)
from app.orchestration.schemas import AgentResponseOutput
from app.orchestration.tools import build_registry_tools

logger = logging.getLogger(__name__)


class TwoAgentWorkflow:
    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry

    def run(
        self,
        question: str,
        dataset_context: str,
        execute_tool: Callable[[str, dict[str, Any]], tuple[UUID, dict[str, Any]]],
    ) -> tuple[AgentResponseOutput, dict[str, Any], list[tuple[str, UUID]]]:
        if not self.settings.gemini_api_key:
            raise LLMConfigurationError("Gemini API key is not configured")
        tool_results: dict[str, Any] = {}
        executions: list[tuple[str, UUID]] = []

        def execute_and_capture(
            tool_name: str, parameters: dict[str, Any]
        ) -> tuple[UUID, dict[str, Any]]:
            if len(executions) >= self.settings.max_agent_tool_calls:
                raise LLMExecutionError("The workflow reached its analytical tool limit")
            execution_id, result = execute_tool(tool_name, parameters)
            executions.append((tool_name, execution_id))
            tool_results[tool_name] = result
            return execution_id, result

        try:
            llm = LLM(
                model=f"gemini/{self.settings.gemini_model}",
                api_key=self.settings.gemini_api_key,
                temperature=0,
                max_tokens=4_000,
            )
            tools = build_registry_tools(self.registry, execute_and_capture)
            analyst = Agent(
                role="Data Analyst",
                goal=(
                    "Select the smallest set of registered analytical tools needed to "
                    "answer the question."
                ),
                backstory=(
                    "You interpret dataset questions and use only the supplied deterministic "
                    "tools. Never invent values or write code."
                ),
                tools=tools,
                llm=llm,
                allow_delegation=False,
                max_iter=self.settings.max_agent_iterations,
                max_execution_time=120,
                allow_code_execution=False,
            )
            response_analyst = Agent(
                role="Response Analyst",
                goal="Summarize verified analytical results accurately and concisely.",
                backstory=(
                    "You report only facts present in verified tool results. If the tools "
                    "cannot answer the question, say so explicitly."
                ),
                llm=llm,
                allow_delegation=False,
                max_iter=2,
                max_execution_time=120,
                allow_code_execution=False,
            )
            analysis_task = Task(
                description=(
                    f"Question: {question}\nDataset context: {dataset_context}\n"
                    "Use registered tools when they can answer the question. Do not use any "
                    "unlisted tool and do not claim results before a tool returns them."
                ),
                expected_output="A concise account of the tool calls and their verified outputs.",
                agent=analyst,
            )
            response_task = Task(
                description=(
                    "Produce a JSON response with answer, tools_used, and limitations. "
                    "Use only the verified results below; do not infer unsupported statistics.\n"
                    f"Verified results: {json.dumps(tool_results, default=str)}"
                ),
                expected_output="A JSON object matching the AgentResponseOutput schema.",
                agent=response_analyst,
                context=[analysis_task],
                output_pydantic=AgentResponseOutput,
            )
            Crew(
                agents=[analyst, response_analyst],
                tasks=[analysis_task, response_task],
                process=Process.sequential,
                verbose=False,
                max_rpm=10,
            ).kickoff()
            output = response_task.output
            if output is None:
                raise LLMExecutionError("The response agent returned no result")
            parsed = (
                output.pydantic
                if isinstance(output.pydantic, AgentResponseOutput)
                else AgentResponseOutput.model_validate_json(output.raw)
            )
            if not executions:
                parsed = AgentResponseOutput(
                    answer=(
                        "The question could not be answered with the available "
                        "registered analytical tools."
                    ),
                    limitations=[
                        "No registered analytical tool produced verified results."
                    ],
                )
            return parsed, tool_results, executions
        except (LLMConfigurationError, LLMExecutionError):
            raise
        except AnalyticalError as exc:
            raise ToolExecutionError("A registered analytical tool could not complete") from exc
        except Exception as exc:
            logger.exception("CrewAI Gemini workflow failed")
            raise LLMExecutionError("The analysis workflow could not be completed") from exc
