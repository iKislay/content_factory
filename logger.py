import structlog
import logging
import sys

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

def get_logger(name: str = None):
    """Get a structured logger instance."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger


class PipelineLogger:
    """
    Structured logger for pipeline operations.
    
    Provides convenient methods for common logging patterns with
    structured data that can be parsed by log aggregators.
    """

    def __init__(self, component: str = "pipeline"):
        self._logger = get_logger(component)
        self._component = component

    def agent_started(self, agent: str, run_id: str = None, **kwargs):
        """Log when an agent starts processing."""
        self._logger.info(
            "agent_started",
            agent=agent,
            run_id=run_id,
            **kwargs
        )

    def agent_completed(self, agent: str, run_id: str = None, duration_ms: float = None, **kwargs):
        """Log when an agent completes successfully."""
        self._logger.info(
            "agent_completed",
            agent=agent,
            run_id=run_id,
            duration_ms=duration_ms,
            **kwargs
        )

    def agent_failed(self, agent: str, run_id: str = None, error: str = None, **kwargs):
        """Log when an agent fails."""
        self._logger.error(
            "agent_failed",
            agent=agent,
            run_id=run_id,
            error=error,
            **kwargs
        )

    def tool_called(self, tool_name: str, call_id: str = None, **kwargs):
        """Log when a tool is called."""
        self._logger.info(
            "tool_called",
            tool=tool_name,
            call_id=call_id,
            **kwargs
        )

    def tool_result(self, tool_name: str, call_id: str = None, success: bool = True, duration_ms: float = None, **kwargs):
        """Log tool execution result."""
        if success:
            self._logger.info(
                "tool_result",
                tool=tool_name,
                call_id=call_id,
                success=success,
                duration_ms=duration_ms,
                **kwargs
            )
        else:
            self._logger.error(
                "tool_result",
                tool=tool_name,
                call_id=call_id,
                success=success,
                duration_ms=duration_ms,
                **kwargs
            )

    def status_changed(self, run_id: str, old_status: str, new_status: str, **kwargs):
        """Log pipeline status change."""
        self._logger.info(
            "status_changed",
            run_id=run_id,
            old_status=old_status,
            new_status=new_status,
            **kwargs
        )

    def progress_update(self, run_id: str, progress: int, current_agent: str = None, **kwargs):
        """Log pipeline progress update."""
        self._logger.info(
            "progress_update",
            run_id=run_id,
            progress=progress,
            current_agent=current_agent,
            **kwargs
        )

    def circuit_breaker(self, tool: str, state: str, **kwargs):
        """Log circuit breaker state changes."""
        self._logger.warning(
            "circuit_breaker",
            tool=tool,
            state=state,
            **kwargs
        )

    def fallback_used(self, tool: str, reason: str = None, **kwargs):
        """Log when a fallback function is used."""
        self._logger.warning(
            "fallback_used",
            tool=tool,
            reason=reason,
            **kwargs
        )

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self._logger.error(message, **kwargs)


_pipeline_logger = None

def get_pipeline_logger(component: str = "pipeline") -> PipelineLogger:
    """Get the global pipeline logger."""
    global _pipeline_logger
    if _pipeline_logger is None:
        _pipeline_logger = PipelineLogger(component)
    return _pipeline_logger