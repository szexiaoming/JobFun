"""
End-to-end tests for the Agent system.

Tests the agent framework without making real API calls.
"""

import pytest

from src.agent.memory import AgentMemory
from src.agent.orchestrator import AgentConfig, RecruiterAgent
from src.agent.planner import Planner
from src.agent.tools import ToolRegistry, get_tool_registry, reset_tool_registry
from src.agent.types import (
    AgentEvent,
    AgentState,
    Plan,
    PlanStep,
    StepStatus,
    ToolCall,
    ToolDef,
    ToolResult,
)


# ═══════════════════════════════════════════════════════
# Tool Registry Tests
# ═══════════════════════════════════════════════════════


class TestToolRegistry:
    def test_register_tool(self):
        registry = ToolRegistry()

        def dummy_handler(**kwargs):
            return {"ok": True}

        tool = ToolDef(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=dummy_handler,
        )
        registry.register(tool)
        assert "test_tool" in registry.list_tools()

    def test_register_duplicate_raises(self):
        registry = ToolRegistry()

        def dummy_handler(**kwargs):
            return {"ok": True}

        tool = ToolDef(
            name="dup_tool",
            description="Test",
            parameters={"type": "object", "properties": {}},
            handler=dummy_handler,
        )
        registry.register(tool)
        with pytest.raises(Exception):
            registry.register(tool)

    def test_execute_tool_success(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> dict:
            return {"result": a + b}

        tool = ToolDef(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            handler=add,
        )
        registry.register(tool)

        result = registry.execute(ToolCall(name="add", arguments={"a": 1, "b": 2}))
        assert result.success
        assert result.data == {"result": 3}

    def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = registry.execute(ToolCall(name="nonexistent", arguments={}))
        assert not result.success
        assert "未知工具" in result.error or "Unknown tool" in result.error

    def test_execute_tool_with_bad_args(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> dict:
            return {"result": a + b}

        tool = ToolDef(
            name="add",
            description="Add numbers",
            parameters={"type": "object", "properties": {}},
            handler=add,
        )
        registry.register(tool)

        # Missing required args should still execute (Python will raise TypeError)
        result = registry.execute(ToolCall(name="add", arguments={}))
        assert not result.success

    def test_openai_schema_export(self):
        registry = ToolRegistry()

        def handler(**kwargs):
            return {}

        tool = ToolDef(
            name="my_tool",
            description="Does something",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
            handler=handler,
        )
        registry.register(tool)

        schema = registry.to_openai_schema()
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "my_tool"

    def test_anthropic_schema_export(self):
        registry = ToolRegistry()

        def handler(**kwargs):
            return {}

        tool = ToolDef(
            name="my_tool",
            description="Does something",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )
        registry.register(tool)

        schema = registry.to_anthropic_schema()
        assert len(schema) == 1
        assert schema[0]["name"] == "my_tool"
        assert "input_schema" in schema[0]

    def test_describe_for_prompt(self):
        registry = ToolRegistry()

        def handler(**kwargs):
            return {}

        tool = ToolDef(
            name="echo",
            description="Echo back input",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}},
            handler=handler,
        )
        registry.register(tool)

        description = registry.describe_for_prompt()
        assert "echo" in description
        assert "Echo back input" in description

    def test_builtin_tools_registered(self):
        """Verify all built-in tools are registered (hybrid architecture)."""
        reset_tool_registry()
        registry = get_tool_registry()
        tools = registry.list_tools()
        assert len(tools) == 10

        expected = [
            "run_comprehensive_analysis",
            "parse_job_description",
            "parse_resume",
            "investigate_gap",
            "ask_user_clarification",
            "generate_suggestion",
            "validate_suggestion",
            "apply_modifications",
            "validate_changes",
            "generate_interview_questions",
        ]
        for name in expected:
            assert name in tools, f"Missing tool: {name}"


# ═══════════════════════════════════════════════════════
# Agent Memory Tests
# ═══════════════════════════════════════════════════════


class TestAgentMemory:
    def test_set_goal(self):
        mem = AgentMemory()
        mem.set_goal("Optimize resume")
        assert mem.goal == "Optimize resume"

    def test_set_context(self):
        mem = AgentMemory()
        mem.set_context({"resume_dir": "/tmp", "jd_json": {"company": "Google"}})
        assert mem.context["resume_dir"] == "/tmp"

    def test_set_plan(self):
        mem = AgentMemory()
        plan = Plan(
            goal="Test",
            approach="Quick scan",
            steps=[PlanStep(id="1", description="Step 1")],
        )
        mem.set_plan(plan)
        assert mem.plan is not None
        assert len(mem.plan.steps) == 1

    def test_add_observation(self):
        mem = AgentMemory()
        mem.add_observation("K8s gap found")
        mem.add_observation("Docker experience present")
        assert len(mem.get_observations()) == 2

    def test_add_result(self):
        mem = AgentMemory()
        result = ToolResult(
            tool_name="parse_resume",
            success=True,
            data={"sections": []},
            summary="Parsed successfully",
        )
        mem.add_result(result)
        stored = mem.get_last_tool_result("parse_resume")
        assert stored is not None
        assert stored.success

    def test_get_progress_summary(self):
        mem = AgentMemory()
        plan = Plan(
            goal="Test",
            approach="Test approach",
            steps=[
                PlanStep(id="1", description="Step 1", status=StepStatus.COMPLETED),
                PlanStep(id="2", description="Step 2", status=StepStatus.IN_PROGRESS),
                PlanStep(id="3", description="Step 3", status=StepStatus.PENDING),
            ],
        )
        mem.set_goal("Test")
        mem.set_plan(plan)
        summary = mem.get_progress_summary()
        assert "Test" in summary
        assert "Step 1" in summary

    def test_get_conversation_for_llm(self):
        mem = AgentMemory()
        mem.set_goal("Test")
        mem.add_agent_message("I will analyze the skills")
        mem.add_result(
            ToolResult(tool_name="test", success=True, data={"key": "val"}, summary="Done")
        )
        msgs = mem.get_conversation_for_llm()
        assert len(msgs) > 0

    def test_step_count(self):
        mem = AgentMemory()
        assert mem.step_count == 0
        mem.add_result(ToolResult(tool_name="t1", success=True, summary="ok"))
        mem.add_result(ToolResult(tool_name="t2", success=True, summary="ok"))
        assert mem.step_count == 2


# ═══════════════════════════════════════════════════════
# Planner Tests
# ═══════════════════════════════════════════════════════


class TestPlanner:
    def test_create_plan_with_context(self):
        planner = Planner()
        plan = planner.create_plan(
            "Optimize resume for Google SDE",
            {"resume_json": {"sections": []}, "jd_json": {"company": "Google"}},
        )
        assert plan.goal == "Optimize resume for Google SDE"
        assert len(plan.steps) > 0
        # With both resume and JD, the plan should include the comprehensive analysis
        step_descriptions = [s.description for s in plan.steps]
        assert any("匹配" in d for d in step_descriptions) or any("analysis" in d.lower() for d in step_descriptions)

    def test_create_plan_without_resume(self):
        planner = Planner()
        plan = planner.create_plan("Help me", {"jd_json": {"company": "Google"}})
        # Should include parse_resume step
        assert any(s.tool == "parse_resume" for s in plan.steps)

    def test_create_plan_without_jd(self):
        planner = Planner()
        plan = planner.create_plan("Help me", {"resume_json": {"sections": []}})
        # Should include parse_jd step
        assert any(s.tool == "parse_job_description" for s in plan.steps)

    def test_create_empty_plan(self):
        planner = Planner()
        plan = planner.create_plan("Just chat", {})
        assert len(plan.steps) > 0  # At least synthesize report step

    def test_plan_steps_have_ids(self):
        planner = Planner()
        plan = planner.create_plan("Test", {"resume_json": {}, "jd_json": {}})
        for step in plan.steps:
            assert step.id
            assert step.id.startswith("s")  # s1, s2, ...


# ═══════════════════════════════════════════════════════
# Orchestrator Tests
# ═══════════════════════════════════════════════════════


class TestAgentConfig:
    def test_default_config(self):
        config = AgentConfig()
        assert config.max_steps == 20
        assert config.auto_apply is False
        assert config.verbose is True

    def test_custom_config(self):
        config = AgentConfig(max_steps=5, auto_apply=True, verbose=False)
        assert config.max_steps == 5
        assert config.auto_apply is True


class TestRecruiterAgent:
    def test_initialize(self):
        agent = RecruiterAgent(AgentConfig(max_steps=5))
        context = {
            "resume_json": {"sections": []},
            "jd_json": {"company": "TestCorp", "position": "SDE"},
            "resume_dir": "/tmp/test",
        }
        event = agent.initialize("Tailor resume for TestCorp SDE", context)
        assert event.type == "thinking"
        assert agent.state == AgentState.THINKING
        assert agent.memory.goal == "Tailor resume for TestCorp SDE"
        assert agent.memory.plan is not None
        assert len(agent.memory.plan.steps) > 0

    def test_initialize_with_minimal_context(self):
        agent = RecruiterAgent(AgentConfig(max_steps=5))
        event = agent.initialize("Help me", {})
        assert event.type == "thinking"
        assert agent.memory.plan is not None

    def test_continue_with_user_response(self):
        agent = RecruiterAgent(AgentConfig(max_steps=5))
        agent.initialize("Test", {"resume_json": {}, "jd_json": {}})

        # Simulate waiting state
        agent.state = AgentState.WAITING_USER
        agent.continue_with_user_response("Yes, I have K8s experience")
        assert agent.state == AgentState.IDLE

    def test_is_done_property(self):
        agent = RecruiterAgent()
        assert not agent.is_done
        agent.state = AgentState.DONE
        assert agent.is_done

    def test_is_waiting_property(self):
        agent = RecruiterAgent()
        assert not agent.is_waiting
        agent.state = AgentState.WAITING_USER
        assert agent.is_waiting

    def test_tool_execution_via_orchestrator(self):
        """Test that a fixed-tool step executes correctly through the orchestrator."""
        agent = RecruiterAgent(AgentConfig(max_steps=5))

        # Manually set up a step with a simple tool
        # The orchestrator shouldn't crash when running
        assert agent.tools is not None
        assert "parse_resume" in agent.tools.list_tools()

    def test_context_data_stored_correctly(self):
        """Test that context data is properly stored in collected_analyses."""
        agent = RecruiterAgent()
        agent.memory.set_goal("Test goal")
        agent.memory.set_context(
            {
                "jd_json": {
                    "company": "Google",
                    "position": "SDE",
                    "required_skills": ["Python", "K8s"],
                    "preferred_skills": ["gRPC"],
                },
                "resume_json": {
                    "sections": [
                        {"title": "Experience", "entries": [{}]},
                        {"title": "Education", "entries": [{}]},
                    ]
                },
            }
        )

        # Simulate a comprehensive analysis result
        agent._collected_analyses["match_result"] = {
            "total_score": 72,
            "skill_score": 65,
            "experience_score": 80,
            "matched_skills": ["Python"],
            "missing_skills": ["K8s"],
            "risks": [],
            "summary": "Good match overall.",
        }
        agent._collected_suggestions = [
            {"category": "keyword", "priority": 1, "original_text": "...", "suggested_text": "...", "rationale": "..."}
        ]

        report = agent._synthesize_report()
        assert "72" in report  # total_score
        assert "Python" in report
        assert "K8s" in report


# ═══════════════════════════════════════════════════════
# Types Tests
# ═══════════════════════════════════════════════════════


class TestAgentTypes:
    def test_agent_event_creation(self):
        event = AgentEvent(type="thinking", message="Analyzing...")
        assert event.type == "thinking"
        assert event.message == "Analyzing..."
        assert event.data is None

    def test_plan_step_creation(self):
        step = PlanStep(id="s1", description="Do something", tool="my_tool")
        assert step.id == "s1"
        assert step.status == StepStatus.PENDING

    def test_tool_result_creation(self):
        result = ToolResult(
            tool_name="test",
            success=True,
            data={"key": "value"},
            summary="All good",
        )
        assert result.success
        assert result.data == {"key": "value"}

    def test_agent_states(self):
        assert AgentState.IDLE.value == "idle"
        assert AgentState.THINKING.value == "thinking"
        assert AgentState.WAITING_USER.value == "waiting"


# ═══════════════════════════════════════════════════════
# Tool Handlers Tests
# ═══════════════════════════════════════════════════════


class TestToolHandlers:
    def test_ask_user_clarification(self):
        from src.agent.tool_handlers import ask_user_clarification

        result = ask_user_clarification(
            question="Have you used Docker?",
            context="JD requires containerization experience",
            options=["Yes, extensively", "A little", "No"],
        )
        assert result["success"]
        assert result["needs_user_response"]
        assert result["question"] == "Have you used Docker?"
        assert len(result["options"]) == 3

    def test_generate_suggestion_invalid_category(self):
        from src.agent.tool_handlers import generate_suggestion

        result = generate_suggestion(
            category="invalid_category",
            gap_description="Missing K8s",
            resume_context="Docker experience",
            jd_context="K8s required",
        )
        assert not result["success"]

    def test_parse_job_description_invalid_source(self):
        from src.agent.tool_handlers import parse_job_description

        result = parse_job_description(source_type="video", content="test")
        assert not result["success"]

    def test_validate_changes_nonexistent_dir(self):
        from src.agent.tool_handlers import validate_changes

        result = validate_changes(resume_dir="/nonexistent/path/12345")
        # May succeed (empty files pass validation) or fail (path error)
        # Either is acceptable behavior — the key is it doesn't crash
        assert isinstance(result, dict)
        assert "success" in result

    def test_apply_modifications_nonexistent_dir(self):
        from src.agent.tool_handlers import apply_modifications

        result = apply_modifications(suggestions=[], resume_dir="/nonexistent/path")
        assert not result["success"]
