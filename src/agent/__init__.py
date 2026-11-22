"""
AI Agent module for JobFun.

Transforms the pipeline-based architecture into an autonomous agent
that observes, plans, acts, and reflects — deciding which tools to
use and in what order, rather than following a hardcoded flow.
"""

from src.agent.types import AgentEvent, AgentState, ToolCall, ToolDef, ToolResult
from src.agent.tools import ToolRegistry, get_tool_registry
from src.agent.memory import AgentMemory
from src.agent.planner import Planner
from src.agent.orchestrator import RecruiterAgent, AgentConfig

__all__ = [
    "AgentConfig",
    "AgentEvent",
    "AgentMemory",
    "AgentState",
    "Planner",
    "RecruiterAgent",
    "ToolCall",
    "ToolDef",
    "ToolRegistry",
    "ToolResult",
    "get_tool_registry",
]
