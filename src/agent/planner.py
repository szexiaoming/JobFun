"""
Agent Planner — simple, predictable plan.

The agent does NOT interrogate the user about every gap.
It runs the analysis, presents results, and lets the user
decide what to do next.
"""

from datetime import datetime

from src.agent.types import Plan, PlanStep
from src.utils.logger import logger


class Planner:
    """Creates minimal, focused execution plans."""

    def create_plan(self, goal: str, context: dict) -> Plan:
        """
        The plan has at most 3 steps:
        1. Parse data (if missing)
        2. Run comprehensive analysis
        3. Present report

        No interrogation, no auto-investigation.
        The user directs what happens after seeing results.
        """
        has_resume = bool(context.get("resume_json") or context.get("resume_dir"))
        has_jd = bool(context.get("jd_json") or context.get("jd_text"))

        steps = []
        n = 0

        def _next() -> str:
            nonlocal n
            n += 1
            return f"s{n}"

        # Only parse what's missing
        if not has_resume:
            steps.append(PlanStep(id=_next(), description="解析简历", tool="parse_resume"))
        if not has_jd:
            steps.append(PlanStep(id=_next(), description="解析 JD", tool="parse_job_description"))

        # The core analysis — one call, full results
        steps.append(PlanStep(
            id=_next(),
            description="运行全面匹配分析",
            tool="run_comprehensive_analysis",
        ))

        # Present results — no interrogation
        steps.append(PlanStep(
            id=_next(),
            description="生成分析报告",
            tool="",  # Synthesize from match results directly
        ))

        plan = Plan(
            goal=goal,
            approach="一键分析：解析 → 匹配 → 报告",
            steps=steps,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        logger.info("Plan: %d steps", len(steps))
        return plan
