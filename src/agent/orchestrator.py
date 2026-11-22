"""
Agent Orchestrator — executes a plan of fixed-tool steps.

Design principle:
    The agent does NOT ask LLM to decide which tool to use between steps.
    Instead, the planner creates a deterministic plan with fixed tools.
    The agent simply executes them in order.

    This eliminates the "LLM picks wrong tool" problem and ensures
    predictable, high-quality execution.

    Intelligence comes from the tools themselves:
    - run_comprehensive_analysis: full pipeline match (high quality)
    - investigate_gap: deep dive on specific skill gaps
    - ask_user_clarification: interactive user inquiry
    - generate_suggestion / validate_suggestion: quality control
    - apply_modifications / validate_changes: safe execution
"""

import json
from datetime import datetime
from typing import Callable, Generator, Optional

from src.agent.memory import AgentMemory
from src.agent.planner import Planner
from src.agent.tools import ToolRegistry, get_tool_registry
from src.agent.types import (
    AgentEvent,
    AgentState,
    PlanStep,
    StepStatus,
    ToolCall,
    ToolResult,
)
from src.utils.logger import logger


class AgentConfig:
    def __init__(
        self,
        max_steps: int = 20,
        auto_apply: bool = False,
        verbose: bool = True,
    ):
        self.max_steps = max_steps
        self.auto_apply = auto_apply
        self.verbose = verbose


class RecruiterAgent:
    """
    Autonomous recruiting agent with deterministic plan execution.

    Usage:
        agent = RecruiterAgent(config)
        agent.initialize(goal, context)

        for event in agent.run_step_by_step():
            if event.type == "ask_user":
                break  # Wait for user input
            render_event(event)

        # After user responds:
        agent.continue_with_user_response(user_text)
        for event in agent.run_step_by_step():
            ...
    """

    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()
        self.tools: ToolRegistry = get_tool_registry()
        self.planner = Planner()
        self.memory = AgentMemory()
        self.state = AgentState.IDLE
        self._step_index: int = 0
        self._current_plan_steps: list[PlanStep] = []
        self._pending_user_question: Optional[dict] = None
        self._collected_suggestions: list[dict] = []
        self._collected_analyses: dict = {}

    # ── Public API ──────────────────────────────────────

    def initialize(self, goal: str, context: dict) -> AgentEvent:
        """Set up the agent for a new task."""
        self.state = AgentState.THINKING
        self.memory = AgentMemory()
        self.memory.set_goal(goal)
        self.memory.set_context(context)
        self._step_index = 0
        self._collected_suggestions = []
        self._collected_analyses = {}
        self._pending_user_question = None

        plan = self.planner.create_plan(goal, context)
        self.memory.set_plan(plan)
        self._current_plan_steps = plan.steps

        logger.info("Agent initialized: goal='%s', %d steps", goal[:80], len(plan.steps))

        return AgentEvent(
            type="thinking",
            message=f"📋 分析策略: {plan.approach}\n\n共 {len(plan.steps)} 个步骤:\n"
            + "\n".join(f"{i+1}. {s.description}" for i, s in enumerate(plan.steps)),
        )

    def run_step_by_step(self) -> Generator[AgentEvent, None, None]:
        """Execute the next pending step (deterministic, fixed-tool)."""
        if self.state == AgentState.WAITING_USER:
            yield AgentEvent("thinking", "⏳ 等待你的回复...")
            return

        if self.state in (AgentState.DONE, AgentState.ERROR):
            return

        self.state = AgentState.THINKING

        while self._step_index < len(self._current_plan_steps):
            step = self._current_plan_steps[self._step_index]

            if step.status == StepStatus.COMPLETED:
                self._step_index += 1
                continue

            step.status = StepStatus.IN_PROGRESS
            yield AgentEvent("step_start", f"📌 {step.description}", step_id=step.id)

            try:
                for event in self._execute_step(step):
                    yield event
                    if event.type == "ask_user":
                        self.state = AgentState.WAITING_USER
                        return
                    if event.type == "error":
                        step.status = StepStatus.FAILED
                        self._step_index += 1
                        break

                if step.status == StepStatus.IN_PROGRESS:
                    step.status = StepStatus.COMPLETED

                yield AgentEvent("step_end", f"✅ 完成: {step.description}", step_id=step.id)

            except Exception as e:
                logger.error("Step failed: %s", e)
                step.status = StepStatus.FAILED
                yield AgentEvent("error", f"❌ 步骤失败: {e}", step_id=step.id)

            self._step_index += 1

        # All steps done — synthesize final report
        self.state = AgentState.THINKING
        yield AgentEvent("thinking", "📊 正在生成综合分析报告...")

        report = self._synthesize_report()
        self.memory.add_agent_message(report)
        self.state = AgentState.DONE

        yield AgentEvent(
            "done",
            report,
            data={
                "suggestions": self._collected_suggestions,
                "analyses": {
                    k: v for k, v in self._collected_analyses.items()
                    if k not in ("resume", "jd")  # Don't dump large raw data
                },
            },
        )

    def continue_with_user_response(self, user_text: str) -> None:
        """Feed user's response back into the agent."""
        if self.state != AgentState.WAITING_USER:
            return
        self.memory.add_user_response(user_text)
        self.state = AgentState.IDLE
        logger.info("User response recorded")

    @property
    def is_done(self) -> bool:
        return self.state == AgentState.DONE

    @property
    def is_waiting(self) -> bool:
        return self.state == AgentState.WAITING_USER

    @property
    def pending_question(self) -> Optional[dict]:
        return self._pending_user_question

    # ── Step Execution (all fixed-tool) ─────────────────

    def _execute_step(self, step: PlanStep) -> Generator[AgentEvent, None, None]:
        """Execute a step. If it has a tool, run it. Otherwise, it's the report step."""
        if step.tool:
            yield from self._run_tool(step.tool, step)
        else:
            # No-tool step = report synthesis. Just mark done.
            yield AgentEvent(
                "thinking",
                "📊 分析完成，正在整理报告...",
                step_id=step.id,
            )

    def _run_tool(self, tool_name: str, step: PlanStep) -> Generator[AgentEvent, None, None]:
        """Execute a specific tool with context-derived arguments."""
        args = self._build_tool_args(tool_name)

        yield AgentEvent(
            "tool_call",
            f"🔧 调用工具: {tool_name}",
            data={"tool": tool_name, "args": _safe_dict(args)},
            step_id=step.id,
        )

        result = self.tools.execute(ToolCall(name=tool_name, arguments=args))
        step.result = result
        self.memory.add_result(result)

        if result.success:
            yield AgentEvent(
                "tool_result",
                f"✅ {tool_name} 执行成功",
                data={"summary": result.summary},
                step_id=step.id,
            )
            self._store_result_data(tool_name, result.data)
        else:
            yield AgentEvent(
                "error",
                f"❌ {tool_name} 失败: {result.error}",
                step_id=step.id,
            )

    # ── Tool Arguments ──────────────────────────────────

    def _build_tool_args(self, tool_name: str) -> dict:
        """Build tool arguments from memory context and collected analyses."""
        ctx = self.memory.context

        if tool_name == "parse_resume":
            return {"resume_dir": str(ctx.get("resume_dir", ""))}

        if tool_name == "parse_job_description":
            return {
                "source_type": ctx.get("agent_jd_type", ctx.get("jd_source_type", "text")),
                "content": ctx.get("agent_jd_text", ctx.get("jd_text", "")),
            }

        if tool_name == "run_comprehensive_analysis":
            # Use already-parsed data if available, otherwise raw inputs
            jd = self._collected_analyses.get("jd", ctx.get("jd_json"))
            resume = self._collected_analyses.get("resume", ctx.get("resume_json"))
            return {
                "jd_json": jd if jd else None,
                "resume_json": resume if resume else None,
                "resume_dir": str(ctx.get("resume_dir", "")),
                "resume_id": int(ctx.get("resume_id", 0) or 0),
                "jd_text": ctx.get("agent_jd_text", ctx.get("jd_text", "")),
                "jd_source_type": ctx.get("agent_jd_type", ctx.get("jd_source_type", "text")),
                "jd_id": int(ctx.get("jd_id", 0) or 0),
            }

        if tool_name == "apply_modifications":
            return {
                "suggestions": self._collected_suggestions,
                "resume_dir": str(ctx.get("resume_dir", "")),
            }

        if tool_name == "validate_changes":
            return {"resume_dir": str(ctx.get("resume_dir", ""))}

        if tool_name == "generate_interview_questions":
            match = self._collected_analyses.get("match_result", {})
            return {
                "category": "all",
                "focus_areas": match.get("missing_skills", [])[:5] if match else [],
            }

        return {}

    # ── Data Storage ────────────────────────────────────

    def _store_result_data(self, tool_name: str, data: any) -> None:
        """Store structured data from tool results."""
        if not isinstance(data, dict):
            return

        if tool_name == "parse_resume" and data.get("resume"):
            self._collected_analyses["resume"] = data["resume"]
            self.memory.context["resume_json"] = data["resume"]
            sections = data["resume"].get("sections", [])
            self.memory.add_observation(f"简历已解析: {len(sections)} sections")

        elif tool_name == "parse_job_description" and data.get("jd"):
            self._collected_analyses["jd"] = data["jd"]
            self.memory.context["jd_json"] = data["jd"]
            jd = data["jd"]
            self.memory.add_observation(
                f"JD 已解析: {jd.get('company', '?')} - {jd.get('position', '?')}"
            )

        elif tool_name == "run_comprehensive_analysis":
            if data.get("match_result"):
                self._collected_analyses["match_result"] = data["match_result"]
                mr = data["match_result"]
                self.memory.add_observation(
                    f"综合匹配: 总分 {mr.get('total_score', 0):.0f}, "
                    f"匹配 {len(mr.get('matched_skills', []))} 项, "
                    f"缺失 {len(mr.get('missing_skills', []))} 项"
                )
            if data.get("suggestions"):
                self._collected_suggestions = data["suggestions"]
                self.memory.add_observation(f"生成 {len(data['suggestions'])} 条建议")

        elif tool_name == "investigate_gap" and data.get("gap_analysis"):
            gap = data["gap_analysis"]
            if isinstance(gap, dict):
                self._collected_analyses.setdefault("gap_investigations", []).append(gap)
                self.memory.add_observation(
                    f"差距分析: {gap.get('severity', '?')} - {gap.get('gap_strategy', '')[:80]}"
                )

        elif tool_name == "generate_suggestion" and data.get("suggestion"):
            self._collected_suggestions.append(data["suggestion"])

        elif tool_name == "validate_suggestion" and data.get("validation"):
            self._collected_analyses.setdefault("validations", []).append(data["validation"])

    # ── Report Synthesis ────────────────────────────────

    def _synthesize_report(self) -> str:
        """
        Synthesize the analysis results into a final report.

        When run_comprehensive_analysis was used, the match_result contains
        all scores + the LLM-generated summary. We format these directly.
        """
        match = self._collected_analyses.get("match_result")
        suggestions = self._collected_suggestions
        obs = self.memory.get_observations()

        # No data at all
        if not match and not suggestions:
            ctx = self.memory.context
            parts = [
                "## 📊 分析报告\n",
                "⚠️ Agent 未能收集到分析数据。\n",
                "### 当前状态",
            ]
            if ctx.get("resume_dir"):
                parts.append(f"- 📁 简历目录: `{ctx['resume_dir']}`")
            if ctx.get("resume_json"):
                r = ctx["resume_json"]
                parts.append(f"- 📄 简历: {len(r.get('sections', []))} sections")
            if ctx.get("jd_json"):
                jd = ctx["jd_json"]
                parts.append(f"- 📋 JD: {jd.get('company', '?')} - {jd.get('position', '?')}")
            if ctx.get("agent_jd_text"):
                parts.append(f"- 📋 JD 文本: 已提供 ({len(ctx['agent_jd_text'])} 字符)")
            parts.append("\n### 可能的原因\n")
            parts.append("1. `run_comprehensive_analysis` 未成功执行")
            parts.append("2. API Key 未配置或网络问题")
            parts.append("3. 简历目录不存在或 .tex 文件找不到")
            return "\n".join(parts)

        # Comprehensive analysis available
        if match:
            lines = ["## 📊 匹配分析报告\n"]

            # Scores table
            lines.append("### 📈 六维度评分\n")
            lines.append("| 维度 | 评分 | 进度 |")
            lines.append("|------|------|------|")
            for key, label in [
                ("total_score", "🎯 总匹配度"),
                ("skill_score", "💻 技能匹配"),
                ("experience_score", "💼 经验匹配"),
                ("education_score", "🎓 教育匹配"),
                ("soft_skill_score", "🤝 软技能"),
                ("culture_score", "🏢 文化匹配"),
            ]:
                score = match.get(key, 0)
                bar = "█" * max(0, int(score / 10)) + "░" * max(0, 10 - int(score / 10))
                lines.append(f"| {label} | **{score:.0f}%** | {bar} |")
            lines.append("")

            # Summary
            if match.get("summary"):
                lines.append(f"### 💡 综合评价\n\n{match['summary']}\n")

            # Skills
            matched = match.get("matched_skills", [])
            missing = match.get("missing_skills", [])
            if matched:
                lines.append(f"### ✅ 已匹配技能 ({len(matched)} 项)\n")
                lines.append(" ".join(f"`{s}`" for s in matched) + "\n")
            if missing:
                lines.append(f"### ⚠️ 缺失技能 ({len(missing)} 项)\n")
                lines.append(" ".join(f"`{s}`" for s in missing) + "\n")

            # Risks
            risks = match.get("risks", [])
            if risks:
                lines.append("### 🚨 风险点\n")
                for r in risks:
                    lines.append(f"- {r}")
                lines.append("")

            # Suggestions
            if suggestions:
                lines.append(f"### 📝 优化建议 ({len(suggestions)} 条)\n")
                for i, s in enumerate(suggestions, 1):
                    lines.append(
                        f"**{i}. [{s.get('category', '?')}] 优先级 {s.get('priority', '?')}**"
                    )
                    lines.append(f"- 原文: _{s.get('original_text', '')}_")
                    lines.append(f"- 建议: **{s.get('suggested_text', '')}**")
                    lines.append(f"- 理由: {s.get('rationale', '')}")
                    lines.append("")

            # Gap investigations
            gaps = self._collected_analyses.get("gap_investigations", [])
            if gaps:
                lines.append("### 🔍 深度差距分析\n")
                for g in gaps:
                    if isinstance(g, dict):
                        lines.append(f"- **{g.get('severity', '?')}**: {g.get('gap_strategy', '')[:200]}")
                lines.append("")

            # Next steps
            lines.append("### 📋 建议下一步\n")
            lines.append("1. 查看上述建议，标记你同意的修改")
            lines.append("2. 对缺失技能，确认你是否有未写入简历的相关经验")
            lines.append("3. Agent 可以帮你应用修改到 LaTeX 源码（需确认）")
            lines.append("4. 使用面试准备功能生成针对性的面试问题")

            return "\n".join(lines)

        # Only suggestions
        if suggestions:
            lines = ["## 📝 生成的建议\n"]
            for i, s in enumerate(suggestions, 1):
                lines.append(f"{i}. [{s.get('category', '?')}] {s.get('suggested_text', '')[:150]}")
            return "\n".join(lines)

        return "## 分析报告\n\n分析已完成，但结果格式异常。请查看控制台日志。"


# ── Helpers ─────────────────────────────────────────────


def _safe_dict(obj: any, max_depth: int = 3) -> any:
    """Make an object safe for serialization/display."""
    if max_depth <= 0:
        return "..."
    if isinstance(obj, dict):
        return {k: _safe_dict(v, max_depth - 1) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > 5:
            return [_safe_dict(x, max_depth - 1) for x in obj[:5]] + ["..."]
        return [_safe_dict(x, max_depth - 1) for x in obj]
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."
    return obj


