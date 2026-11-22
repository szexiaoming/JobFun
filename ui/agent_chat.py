"""
Agent Chat Interface — conversational AI Agent experience.

Replaces the traditional "upload → click → view results" flow with
a chat-like interaction where the Agent:
- Shows its thinking process
- Decides which tools to call
- Asks the user questions when needed
- Presents results incrementally
"""

import json
import time
from typing import Optional

import streamlit as st

from config import ensure_dirs
from src.agent.orchestrator import AgentConfig, RecruiterAgent
from src.agent.types import AgentEvent, AgentState


# ── Session State Keys ────────────────────────────────
AGENT_KEY = "agent_instance"
AGENT_EVENTS_KEY = "agent_events"
AGENT_MESSAGES_KEY = "agent_messages"
AGENT_READY_KEY = "agent_ready"
AGENT_RUNNING_KEY = "agent_running"


def init_agent_session() -> None:
    """Initialize agent-related session state."""
    defaults = {
        AGENT_KEY: None,
        AGENT_EVENTS_KEY: [],
        AGENT_MESSAGES_KEY: [],
        AGENT_READY_KEY: False,
        AGENT_RUNNING_KEY: False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def get_or_create_agent() -> RecruiterAgent:
    """Get existing agent or create a new one."""
    if st.session_state[AGENT_KEY] is None:
        config = AgentConfig(
            max_steps=15,
            auto_apply=False,  # Always require user confirmation
            verbose=True,
        )
        st.session_state[AGENT_KEY] = RecruiterAgent(config)
    return st.session_state[AGENT_KEY]


def render_agent_page() -> None:
    """
    Main agent chat page.

    Layout:
    ┌──────────────────────────────────────┬─────────────────┐
    │                                      │   📋 上下文面板   │
    │         💬 Agent 对话区              │  - 简历信息      │
    │                                      │  - JD 信息       │
    │  Agent: 你好！我准备帮你分析...       │  - 匹配进度      │
    │  User:  帮我优化简历匹配 Google SDE  │                 │
    │  Agent: 🧠 正在分析技能匹配...       │                 │
    │                                      │                 │
    ├──────────────────────────────────────┤                 │
    │  📝 输入框                            │                 │
    └──────────────────────────────────────┴─────────────────┘
    """
    ensure_dirs()
    init_agent_session()

    st.title("🤖 Agent 求职助手")
    st.caption("AI Agent 会自主分析你的简历和 JD，主动向你提问，逐步生成优化方案")

    # ── Two-column layout ──
    col_chat, col_context = st.columns([3, 1])

    with col_context:
        render_context_panel()

    with col_chat:
        # Setup section (if not yet configured)
        if not st.session_state[AGENT_READY_KEY]:
            render_setup_section()
        else:
            render_chat_section()


def render_setup_section() -> None:
    """Initial setup: configure resume and JD before starting the agent."""
    st.markdown("### ⚙️ 开始前准备")

    # Resume selection
    st.markdown("#### 📄 选择简历")
    _render_resume_selector()

    # JD input
    st.markdown("#### 📋 输入 JD")

    jd_mode = st.radio("JD 输入方式", ["📝 文本粘贴", "🖼️ 图片上传", "📄 PDF 上传"], horizontal=True)

    if "📝" in jd_mode:
        jd_text = st.text_area(
            "粘贴 JD 内容",
            height=200,
            placeholder="将职位描述的全文粘贴到这里...",
            key="agent_jd_text_widget",
        )
        if jd_text:
            st.session_state["agent_jd_text"] = jd_text
            st.session_state["agent_jd_type"] = "text"

    elif "🖼️" in jd_mode:
        jd_image = st.file_uploader("上传 JD 截图", type=["png", "jpg", "jpeg", "webp"], key="agent_jd_image_widget")
        if jd_image:
            import base64
            st.session_state["agent_jd_image"] = base64.b64encode(jd_image.read()).decode()
            st.session_state["agent_jd_type"] = "image"
            st.image(jd_image, width=300, caption="JD 预览")

    else:
        jd_pdf = st.file_uploader("上传 JD PDF", type=["pdf"], key="agent_jd_pdf_widget")
        if jd_pdf:
            st.session_state["agent_jd_pdf"] = jd_pdf
            st.session_state["agent_jd_type"] = "pdf"

    # Goal input
    st.markdown("#### 🎯 你的目标")
    goal = st.text_input(
        "告诉 Agent 你想做什么",
        placeholder="例如：帮我对标 Google Cloud SDE 岗位优化简历",
        key="agent_goal",
    )

    # Start button
    if st.button("🚀 启动 Agent", type="primary", use_container_width=True, disabled=not _can_start()):
        _initialize_agent(goal)


def _can_start() -> bool:
    """Check if the minimum requirements are met to start the agent."""
    has_resume = bool(
        st.session_state.get("resume")
        or st.session_state.get("resume_json")
        or st.session_state.get("agent_resume_dir")
    )
    has_jd = bool(
        st.session_state.get("agent_jd_text")
        or st.session_state.get("agent_jd_image")
        or st.session_state.get("agent_jd_pdf")
    )
    has_goal = bool(st.session_state.get("agent_goal", "").strip())
    return has_resume and has_jd and has_goal


def _render_resume_selector() -> None:
    """Let the user pick which resume to use."""
    # Option 1: Use currently loaded resume
    if st.session_state.get("resume"):
        resume = st.session_state["resume"]
        st.success(f"✅ 已加载: **{resume.name}** (v{resume.base_version})")
        st.session_state["agent_resume_dir"] = resume.latex_path
        return

    # Option 2: Select from database
    try:
        from src.db.sqlite_client import get_db
        db = get_db()
        rows = db.list("resumes", limit=20)
        if rows:
            resume_names = {f"{r['name']} (v{r['base_version']})": r for r in rows}
            selected = st.selectbox("从已上传的简历中选择", list(resume_names.keys()))
            if selected and st.button("加载"):
                r = resume_names[selected]
                st.session_state["agent_resume_dir"] = r["latex_path"]
                st.rerun()
            return
    except Exception:
        pass

    # Option 3: Manual path
    resume_dir = st.text_input(
        "或输入简历 LaTeX 目录路径",
        placeholder="D:/resumes/my-resume/",
        key="agent_resume_path",
    )
    if resume_dir:
        from pathlib import Path
        if Path(resume_dir).exists():
            st.session_state["agent_resume_dir"] = resume_dir
            st.success(f"✅ 路径有效: {resume_dir}")
        else:
            st.error("路径不存在")


def _initialize_agent(goal: str) -> None:
    """Initialize the agent with the configured resume and JD."""
    # Build context
    resume = st.session_state.get("resume")
    jd = st.session_state.get("jd")
    context = {
        "resume_dir": st.session_state.get("agent_resume_dir", ""),
        "resume_json": st.session_state.get("resume_json", {}),
        "resume_id": getattr(resume, "id", 0) or 0,
        "jd_text": st.session_state.get("agent_jd_text", ""),
        "jd_source_type": st.session_state.get("agent_jd_type", "text"),
        "jd_json": st.session_state.get("jd_json", {}),
        "jd_id": getattr(jd, "id", 0) or 0,
    }

    agent = get_or_create_agent()
    init_event = agent.initialize(goal, context)

    st.session_state[AGENT_READY_KEY] = True
    st.session_state[AGENT_MESSAGES_KEY] = [
        {"role": "assistant", "content": f"收到！我的分析策略：\n\n{init_event.message}"}
    ]

    # Auto-run the first step
    st.session_state[AGENT_RUNNING_KEY] = True
    st.rerun()


def render_chat_section() -> None:
    """Render the chat interface with agent interaction."""
    # Chat message history
    for msg in st.session_state[AGENT_MESSAGES_KEY]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("suggestions"):
                _render_suggestion_cards(msg["suggestions"])
            if msg.get("events"):
                _render_agent_events(msg["events"])

    # Auto-run agent steps
    if st.session_state[AGENT_RUNNING_KEY]:
        _run_agent_steps()

    # User input
    if st.session_state.get("agent_is_waiting"):
        st.info("👆 Agent 在等你回复上面的问题")

    if prompt := st.chat_input("回复 Agent（或输入新指令）...", key="agent_chat_input"):
        # Add user message
        st.session_state[AGENT_MESSAGES_KEY].append({"role": "user", "content": prompt})

        # If agent was waiting, feed the response
        agent = get_or_create_agent()
        if agent.is_waiting:
            agent.continue_with_user_response(prompt)
            st.session_state[AGENT_RUNNING_KEY] = True
        else:
            # New instruction — re-initialize
            context = _get_current_context()
            agent.initialize(prompt, context)
            st.session_state[AGENT_RUNNING_KEY] = True

        st.rerun()


def _run_agent_steps() -> None:
    """
    Execute agent steps one at a time, rendering events as they come.

    In Streamlit, we can't yield mid-render, so we accumulate events
    and render them all at once after the agent pauses.
    """
    agent = get_or_create_agent()

    if agent.is_done:
        st.session_state[AGENT_RUNNING_KEY] = False
        st.session_state["agent_is_waiting"] = False
        return

    events_buffer = []
    messages_to_add = []

    try:
        for event in agent.run_step_by_step():
            events_buffer.append(event)

            if event.type == "ask_user":
                # Agent needs user input — pause
                question = event.data.get("question", event.message) if event.data else event.message
                context_text = event.data.get("context", "") if event.data else ""
                options = event.data.get("options", []) if event.data else []

                msg = f"### 🤔 {question}\n\n{context_text}"
                if options:
                    msg += "\n\n" + "\n".join(f"- {o}" for o in options)

                messages_to_add.append({"role": "assistant", "content": msg, "events": events_buffer})
                st.session_state[AGENT_RUNNING_KEY] = False
                st.session_state["agent_is_waiting"] = True
                st.session_state[AGENT_MESSAGES_KEY].extend(messages_to_add)
                st.rerun()

            if event.type == "done":
                # Agent finished
                messages_to_add.append({
                    "role": "assistant",
                    "content": event.message,
                    "suggestions": (event.data or {}).get("suggestions", []),
                    "events": events_buffer,
                })
                st.session_state[AGENT_RUNNING_KEY] = False
                st.session_state["agent_is_waiting"] = False
                st.session_state[AGENT_MESSAGES_KEY].extend(messages_to_add)
                st.rerun()

            if event.type == "error":
                messages_to_add.append({
                    "role": "assistant",
                    "content": f"⚠️ {event.message}",
                    "events": events_buffer,
                })

        # If we get here without done/ask_user, store any pending messages
        if messages_to_add:
            st.session_state[AGENT_MESSAGES_KEY].extend(messages_to_add)
            st.rerun()

    except Exception as e:
        st.session_state[AGENT_RUNNING_KEY] = False
        st.session_state[AGENT_MESSAGES_KEY].append({
            "role": "assistant",
            "content": f"❌ Agent 运行出错: {e}",
        })
        st.rerun()


def render_context_panel() -> None:
    """Right sidebar: show current context."""
    st.markdown("### 📋 上下文")

    # Resume info
    st.markdown("**📄 简历**")
    if st.session_state.get("resume"):
        r = st.session_state["resume"]
        st.success(f"{r.name} v{r.base_version}")
    elif st.session_state.get("agent_resume_dir"):
        st.info(st.session_state["agent_resume_dir"][:40])
    else:
        st.warning("未选择简历")

    # JD info
    st.markdown("**📋 JD**")
    jd_text = st.session_state.get("agent_jd_text", "")
    if jd_text:
        st.info(jd_text[:100] + "..." if len(jd_text) > 100 else jd_text)
    elif st.session_state.get("agent_jd_image"):
        st.info("📷 JD 图片已上传")
    else:
        st.warning("未输入 JD")

    # Agent status
    st.markdown("**🤖 Agent 状态**")
    agent = st.session_state.get(AGENT_KEY)
    if agent:
        status_icon = {
            AgentState.IDLE: "⏸️ 空闲",
            AgentState.THINKING: "🧠 思考中",
            AgentState.ACTING: "🔧 执行中",
            AgentState.WAITING_USER: "⏳ 等待你",
            AgentState.DONE: "✅ 完成",
            AgentState.ERROR: "❌ 错误",
        }
        st.caption(status_icon.get(agent.state, "未知"))

        # Progress
        if agent.memory.plan:
            completed = sum(
                1 for s in agent.memory.plan.steps if s.status.value == "completed"
            )
            total = len(agent.memory.plan.steps)
            if total > 0:
                st.progress(completed / total, text=f"步骤 {completed}/{total}")

        # Recent observations
        obs = agent.memory.get_observations()
        if obs:
            st.markdown("**🔍 发现**")
            for o in obs[-3:]:
                st.caption(f"• {o[:80]}")
    else:
        st.caption("未启动")

    # Quick actions
    st.divider()
    if st.button("🔄 重新开始", use_container_width=True):
        _reset_agent()
    if st.button("🏠 回到首页", use_container_width=True):
        st.session_state["page"] = "home"
        st.rerun()


def _render_suggestion_cards(suggestions: list) -> None:
    """Render suggestion cards with accept/reject buttons."""
    for i, sug in enumerate(suggestions):
        with st.container(border=True):
            cols = st.columns([1, 8, 1])
            with cols[0]:
                st.caption(f"#{i+1}")
                st.caption(f"`{sug.get('category', '?')}`")
            with cols[1]:
                st.markdown(f"**原文**: {sug.get('original_text', '')}")
                st.markdown(f"**建议**: {sug.get('suggested_text', '')}")
                st.caption(f"💡 {sug.get('rationale', '')}")
            with cols[2]:
                if st.button("✅", key=f"accept_{i}"):
                    st.session_state.setdefault("accepted_suggestions", []).append(sug)
                    st.toast("已接受")
                if st.button("❌", key=f"reject_{i}"):
                    st.toast("已拒绝")


def _render_agent_events(events: list) -> None:
    """Render agent thinking/execution events in a collapsed expander."""
    if not events:
        return

    with st.expander("🔍 查看 Agent 执行过程", expanded=False):
        for event in events:
            icon = {
                "thinking": "🧠",
                "step_start": "📌",
                "step_end": "✅",
                "tool_call": "🔧",
                "tool_result": "📊",
                "ask_user": "🤔",
                "warning": "⚠️",
                "error": "❌",
                "done": "🎉",
            }.get(event.type, "•")

            st.caption(f"{icon} {event.message[:150]}")


def _get_current_context() -> dict:
    """Reconstruct context from session state."""
    resume = st.session_state.get("resume")
    jd = st.session_state.get("jd")
    return {
        "resume_dir": st.session_state.get("agent_resume_dir", ""),
        "resume_json": st.session_state.get("resume_json", {}),
        "resume_id": getattr(resume, "id", 0) or 0,
        "jd_text": st.session_state.get("agent_jd_text", ""),
        "jd_source_type": st.session_state.get("agent_jd_type", "text"),
        "jd_json": st.session_state.get("jd_json", {}),
        "jd_id": getattr(jd, "id", 0) or 0,
    }


def _reset_agent() -> None:
    """Reset the agent entirely."""
    st.session_state[AGENT_KEY] = None
    st.session_state[AGENT_EVENTS_KEY] = []
    st.session_state[AGENT_MESSAGES_KEY] = []
    st.session_state[AGENT_READY_KEY] = False
    st.session_state[AGENT_RUNNING_KEY] = False
    st.session_state["agent_is_waiting"] = False
    st.rerun()
