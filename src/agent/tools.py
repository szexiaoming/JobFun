"""
Tool Registry — the agent's toolbox.

Architecture:
    The PRIMARY analysis tool is run_comprehensive_analysis, which calls
    the existing pipeline (match_engine.run_match) for a single, context-rich
    LLM call. This ensures analysis quality matches the original pipeline.

    Additional tools handle interaction (ask_user, investigate_gap),
    verification (validate_suggestion), and execution (apply_modifications).

    Each tool is a function wrapped with a schema definition so the LLM
    can decide which tool to call and with what arguments.
"""

import json
import traceback
from typing import Any, Callable, Optional

from src.agent.types import ToolCall, ToolDef, ToolResult
from src.utils.logger import logger


class ToolRegistryError(Exception):
    """Raised when a tool operation fails."""


class ToolRegistry:
    """Registry of all tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("Agent tool registered: %s", tool.name)

    def unregister(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call. Returns ToolResult (never raises)."""
        tool = self._tools.get(call.name)
        if not tool:
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=f"未知工具: '{call.name}'. 可用: {self.list_tools()}",
                summary=f"未知工具: {call.name}",
            )

        logger.info("Agent executing tool: %s(%s)", call.name, _safe_args(call.arguments))

        try:
            data = tool.handler(**call.arguments)
            return ToolResult(
                tool_name=call.name,
                success=True,
                data=data,
                summary=f"'{call.name}' 执行成功",
            )
        except TypeError as e:
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=f"参数错误: {e}",
                summary=f"参数错误: {e}",
            )
        except Exception as e:
            logger.error("Tool '%s' failed: %s\n%s", call.name, e, traceback.format_exc())
            return ToolResult(
                tool_name=call.name,
                success=False,
                error=str(e),
                summary=f"'{call.name}' 失败: {e}",
            )

    def to_openai_schema(self) -> list[dict]:
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return schemas

    def to_anthropic_schema(self) -> list[dict]:
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            })
        return schemas

    def describe_for_prompt(self) -> str:
        lines = ["## 可用工具\n"]
        for tool in self._tools.values():
            params = json.dumps(tool.parameters.get("properties", {}), ensure_ascii=False)
            lines.append(f"### {tool.name}")
            lines.append(f"{tool.description}")
            lines.append(f"参数: {params}")
            lines.append("")
        return "\n".join(lines)


# ── Singleton ────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def reset_tool_registry() -> None:
    global _registry
    _registry = None


# ── Registration ─────────────────────────────────────

def _register_builtin_tools(registry: ToolRegistry) -> None:
    from src.agent.tool_handlers import (
        apply_modifications,
        ask_user_clarification,
        generate_interview_questions,
        generate_suggestion,
        investigate_gap,
        parse_job_description,
        parse_resume,
        run_comprehensive_analysis,
        validate_changes,
        validate_suggestion,
    )

    # ═══ PRIMARY ANALYSIS ═══
    registry.register(ToolDef(
        name="run_comprehensive_analysis",
        description="【核心工具】执行全面的 JD-简历匹配分析。"
        "一次调用即可完成 6 维度评分 + 技能匹配 + 缺失技能 + 风险 + 修改建议。"
        "这是分析质量最高的工具，因为它在一次 LLM 调用中提供完整上下文。"
        "在 agent 需要了解匹配度、生成建议时，优先使用这个工具。",
        parameters={
            "type": "object",
            "properties": {
                "jd_json": {"type": "object", "description": "已解析的 JD JSON（如果有）"},
                "resume_json": {"type": "object", "description": "已解析的简历 JSON（如果有）"},
                "resume_dir": {"type": "string", "description": "简历 LaTeX 目录路径"},
                "resume_id": {"type": "integer", "description": "已保存的简历 ID"},
                "jd_text": {"type": "string", "description": "JD 原始文本"},
                "jd_id": {"type": "integer", "description": "已保存的 JD ID"},
                "jd_source_type": {
                    "type": "string",
                    "enum": ["text", "image", "pdf"],
                    "description": "JD 来源类型"
                },
            },
            "required": [],
        },
        handler=run_comprehensive_analysis,
    ))

    # ═══ DATA GATHERING ═══
    registry.register(ToolDef(
        name="parse_job_description",
        description="解析 JD 文本为结构化 JSON。当用户提供了 JD 文本但还没有结构化数据时使用。",
        parameters={
            "type": "object",
            "properties": {
                "source_type": {"type": "string", "enum": ["text", "image", "pdf"]},
                "content": {"type": "string", "description": "JD 文本内容"},
            },
            "required": ["source_type", "content"],
        },
        handler=parse_job_description,
    ))

    registry.register(ToolDef(
        name="parse_resume",
        description="解析 LaTeX 简历为结构化 JSON。当用户提供了简历目录但还没有结构化数据时使用。",
        parameters={
            "type": "object",
            "properties": {
                "resume_dir": {"type": "string", "description": "简历 LaTeX 目录路径"},
            },
            "required": ["resume_dir"],
        },
        handler=parse_resume,
    ))

    # ═══ GAP INVESTIGATION ═══
    registry.register(ToolDef(
        name="investigate_gap",
        description="深入分析综合匹配结果中发现的某个具体技能差距。"
        "判断该技能是硬性要求还是加分项，候选人是否有可迁移经验，是否需要向用户确认。"
        "在 run_comprehensive_analysis 之后使用。",
        parameters={
            "type": "object",
            "properties": {
                "missing_skill": {"type": "string", "description": "缺失的技能名称"},
                "resume_context": {"type": "string", "description": "简历中相关的内容"},
                "jd_requirement": {"type": "string", "description": "JD 中的要求描述"},
            },
            "required": ["missing_skill"],
        },
        handler=investigate_gap,
    ))

    registry.register(ToolDef(
        name="ask_user_clarification",
        description="当需要确认候选人是否有未写入简历的经验时，向用户提问。"
        "例如：'你是否用过 K8s？即使只是基础操作也可以写入简历。'",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "向用户提出的问题"},
                "context": {"type": "string", "description": "为什么问这个"},
                "options": {"type": "array", "items": {"type": "string"}, "description": "预设选项"},
            },
            "required": ["question", "context"],
        },
        handler=ask_user_clarification,
        requires_user_confirmation=True,
    ))

    # ═══ SUGGESTION & VALIDATION ═══
    registry.register(ToolDef(
        name="generate_suggestion",
        description="针对一个具体差距生成一条简历修改建议。"
        "每条建议包含 original_text、suggested_text、rationale。",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["keyword", "wording", "structure", "highlight", "de_emphasize", "quantify"],
                },
                "gap_description": {"type": "string"},
                "resume_context": {"type": "string"},
                "jd_context": {"type": "string"},
            },
            "required": ["category", "gap_description", "resume_context", "jd_context"],
        },
        handler=generate_suggestion,
    ))

    registry.register(ToolDef(
        name="validate_suggestion",
        description="安全审查：检查建议是否编造经历、篡改公司名/日期。",
        parameters={
            "type": "object",
            "properties": {
                "suggestion": {"type": "object"},
                "original_resume": {"type": "string"},
            },
            "required": ["suggestion", "original_resume"],
        },
        handler=validate_suggestion,
    ))

    # ═══ EXECUTION ═══
    registry.register(ToolDef(
        name="apply_modifications",
        description="将已确认的建议应用到 LaTeX 源码（会先创建 Git 备份）。需要用户确认。",
        parameters={
            "type": "object",
            "properties": {
                "suggestions": {"type": "array", "items": {"type": "object"}},
                "resume_dir": {"type": "string"},
            },
            "required": ["suggestions", "resume_dir"],
        },
        handler=apply_modifications,
        is_destructive=True,
        requires_user_confirmation=True,
    ))

    registry.register(ToolDef(
        name="validate_changes",
        description="修改后验证：检查 LaTeX 文件是否安全。",
        parameters={
            "type": "object",
            "properties": {
                "resume_dir": {"type": "string"},
            },
            "required": ["resume_dir"],
        },
        handler=validate_changes,
    ))

    # ═══ INTERVIEW PREP ═══
    registry.register(ToolDef(
        name="generate_interview_questions",
        description="基于匹配分析结果生成面试准备问题。",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["all", "technical", "project_deep_dive", "behavioral", "english", "system_design"],
                },
                "focus_areas": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
        handler=generate_interview_questions,
    ))

    logger.info("Registered %d agent tools (hybrid architecture)", len(registry._tools))


def _safe_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 80:
            s = s[:80] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
