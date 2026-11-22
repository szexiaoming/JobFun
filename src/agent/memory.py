"""
Agent memory — maintains conversation history, context, and execution state.

Two-tier memory:
  Short-term: current session's conversation + tool results (in-memory)
  Long-term: user preferences + historical feedback (SQLite-backed, Phase D)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.agent.types import Plan, PlanStep, ToolResult


@dataclass
class MemoryEntry:
    """A single entry in agent memory."""

    role: str  # "user" | "agent" | "tool" | "system"
    content: str
    tool_name: str = ""
    tool_result: Any = None
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


class AgentMemory:
    """
    Manages the agent's working memory for a single session.

    Stores:
    - The user's goal
    - Current context (resume, JD, etc.)
    - Conversation history (for multi-turn tool use)
    - Execution plan and progress
    - Tool call history
    """

    def __init__(self):
        self.goal: str = ""
        self.context: dict = {}
        self.plan: Optional[Plan] = None
        self._history: list[MemoryEntry] = []
        self._tool_results: dict[str, ToolResult] = {}  # tool_name → latest result
        self._observations: list[str] = []  # Key findings during analysis

    # ── Setters ──────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        self.goal = goal
        self._add("system", f"Goal: {goal}")

    def set_context(self, ctx: dict) -> None:
        """Set session context: resume_json, jd_json, resume_dir, etc."""
        self.context = ctx

    def set_plan(self, plan: Plan) -> None:
        self.plan = plan
        self._add("system", f"Plan: {plan.approach}")

    def add_user_response(self, text: str) -> None:
        self._add("user", text)

    def add_observation(self, obs: str) -> None:
        """Record a key finding during analysis."""
        self._observations.append(obs)
        self._add("agent", f"Observation: {obs}")

    def add_result(self, result: ToolResult) -> None:
        """Store a tool execution result."""
        self._tool_results[result.tool_name] = result
        self._add(
            "tool",
            result.summary or f"Tool {result.tool_name}: {'OK' if result.success else 'FAILED'}",
            tool_name=result.tool_name,
            tool_result=result.data,
        )

    def add_agent_message(self, content: str) -> None:
        self._add("agent", content)

    # ── Getters ──────────────────────────────────────

    def get_progress_summary(self) -> str:
        """One-paragraph summary of what's been done so far."""
        if not self.plan:
            return "No plan yet."

        lines = [f"Goal: {self.goal}", f"Approach: {self.plan.approach}"]
        for step in self.plan.steps:
            icon = {
                "pending": "⬜",
                "in_progress": "🔄",
                "completed": "✅",
                "skipped": "⏭️",
                "failed": "❌",
            }.get(step.status.value, "⬜")
            lines.append(f"{icon} {step.description}")
        return "\n".join(lines)

    def get_observations(self) -> list[str]:
        return list(self._observations)

    def get_conversation_for_llm(self) -> list[dict]:
        """
        Build a message list suitable for sending to the LLM.
        Filters internal entries and formats for API consumption.
        """
        messages = []
        for entry in self._history:
            if entry.role == "system":
                messages.append({"role": "user", "content": f"[System] {entry.content}"})
            elif entry.role == "tool":
                msg = f"Tool '{entry.tool_name}' result: {entry.content}"
                if entry.tool_result:
                    import json

                    msg += f"\nData: {json.dumps(entry.tool_result, ensure_ascii=False, indent=2)[:2000]}"
                messages.append({"role": "user", "content": msg})
            else:
                role = "assistant" if entry.role == "agent" else entry.role
                messages.append({"role": role, "content": entry.content})
        return messages

    def get_last_tool_result(self, tool_name: str) -> Optional[ToolResult]:
        return self._tool_results.get(tool_name)

    @property
    def step_count(self) -> int:
        return len([e for e in self._history if e.role == "tool"])

    # ── Helpers ──────────────────────────────────────

    def _add(
        self,
        role: str,
        content: str,
        tool_name: str = "",
        tool_result: Any = None,
    ) -> None:
        self._history.append(
            MemoryEntry(
                role=role,
                content=content,
                tool_name=tool_name,
                tool_result=tool_result,
                timestamp=datetime.now().strftime("%H:%M:%S"),
            )
        )
