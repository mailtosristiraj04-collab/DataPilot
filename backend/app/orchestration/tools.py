import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from crewai.tools import BaseTool
from pydantic import PrivateAttr

from app.analytics.registry import ToolRegistry


class RegistryCrewTool(BaseTool):
    """Thin CrewAI adapter over one explicitly registered analytical tool."""

    _execute: Callable[[str, dict[str, Any]], tuple[UUID, dict[str, Any]]] = PrivateAttr()

    def __init__(
        self,
        *,
        execute: Callable[[str, dict[str, Any]], tuple[UUID, dict[str, Any]]],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._execute = execute

    def _run(self, **kwargs: Any) -> str:
        execution_id, result = self._execute(self.name, kwargs)
        return json.dumps(
            {"execution_id": str(execution_id), "tool_name": self.name, "result": result},
            separators=(",", ":"),
        )


def build_registry_tools(
    registry: ToolRegistry,
    execute: Callable[[str, dict[str, Any]], tuple[UUID, dict[str, Any]]],
) -> list[RegistryCrewTool]:
    """Expose exactly the registry's fixed definitions to CrewAI."""
    return [
        RegistryCrewTool(
            name=definition.name,
            description=(
                f"{definition.description} Input must match the declared schema: "
                f"{definition.input_model.model_json_schema()}"
            ),
            args_schema=definition.input_model,
            execute=execute,
        )
        for definition in (registry.get(info.name) for info in registry.list())
    ]
