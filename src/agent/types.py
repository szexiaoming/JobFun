"""
Core type definitions for the Agent system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class AgentState(Enum):
    """States the agent can be in during execution."""

    IDLE = "idle"
    THINKING = "thinking"       # Planning or reflecting
    ACTING = "acting"           # Executing a tool
    WAITING_USER = "waiting"    # Blocked on user input
    DONE = "done"
    ERROR = "error"


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class ToolDef:
    """Definition of a tool the agent can call."""

    name: str
    description: str
    parameters: dict  # JSON Schema for parameters
    handler: Callable  # Async or sync function
    requires_user_confirmation: bool = False
    is_destructive: bool = False  # e.g. file modification


@dataclass
class ToolCall:
    """A pending or completed tool call."""

    name: str
    arguments: dict
    call_id: str = ""


@dataclass
class ToolResult:
    """Result of executing a tool."""

    tool_name: str
    success: bool
    data: Any = None
    error: str = ""
    summary: str = ""  # Human-readable one-liner


@dataclass
class PlanStep:
    """A single step in the agent's execution plan."""

    id: str = ""
    description: str = ""
    tool: str = ""              # Tool name (or "" if agent decides at runtime)
    status: StepStatus = StepStatus.PENDING
    result: Optional[ToolResult] = None
    depends_on: list[str] = field(default_factory=list)  # Step IDs


@dataclass
class Plan:
    """An execution plan created by the agent."""

    goal: str = ""
    approach: str = ""  # High-level strategy description
    steps: list[PlanStep] = field(default_factory=list)
    created_at: str = ""


@dataclass
class AgentEvent:
    """Event emitted during agent execution (for UI streaming)."""

    type: str  # "thinking" | "step_start" | "step_end" | "tool_call" |
    # "tool_result" | "ask_user" | "warning" | "error" | "done"
    message: str = ""
    data: Any = None  # Extra structured data
    step_id: str = ""
