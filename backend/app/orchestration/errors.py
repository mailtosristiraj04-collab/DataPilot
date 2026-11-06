class OrchestrationError(ValueError):
    """A safe, client-facing orchestration error."""


class LLMConfigurationError(OrchestrationError):
    """The configured LLM provider cannot be used."""


class LLMExecutionError(OrchestrationError):
    """The LLM workflow failed without exposing provider details."""


class ToolExecutionError(OrchestrationError):
    """A registered analytical tool rejected or failed an invocation."""
