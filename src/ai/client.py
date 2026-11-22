"""
AI client wrapper supporting both DeepSeek (OpenAI SDK) and Anthropic (Anthropic SDK).
Switches based on AI_PROVIDER config setting.
"""

import base64
import time
from typing import Optional

from openai import OpenAI

from config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    API_RETRY_DELAY,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MAX_API_RETRIES,
    get_active_model,
    get_provider_display_name,
    supports_vision,
)
from src.utils.logger import logger


class AIClientError(Exception):
    """Raised when an AI call fails after all retries."""


class AIClient:
    def __init__(self):
        self._token_usage = {"input": 0, "output": 0}
        self._anthropic_client = None  # Lazy init for fallback

        if AI_PROVIDER == "deepseek":
            if not DEEPSEEK_API_KEY:
                raise AIClientError(
                    "DEEPSEEK_API_KEY is not set. "
                    "Copy .env.example to .env and add your DeepSeek API key."
                )
            self._client = OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
            )
            self._provider = "deepseek"
            logger.info("AI client initialized: DeepSeek @ %s", DEEPSEEK_BASE_URL)
        elif AI_PROVIDER == "anthropic":
            self._init_anthropic()
        else:
            raise AIClientError(f"Unsupported AI provider: {AI_PROVIDER}")

    def _init_anthropic(self):
        """Fallback: initialize Anthropic client."""
        import anthropic

        if not ANTHROPIC_API_KEY:
            raise AIClientError(
                "ANTHROPIC_API_KEY is not set. "
                "Copy .env.example to .env and add your API key."
            )
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._provider = "anthropic"
        logger.info("AI client initialized: Anthropic")

    # ── Public API ──────────────────────────────────

    def extract_jd_from_text(self, jd_text: str) -> dict:
        """Parse raw JD text into structured JSON."""
        from src.ai.prompts.jd_extraction import build_jd_extraction_message

        message = build_jd_extraction_message(jd_text)
        return self._call(
            model=get_active_model("structured"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.1,
        )

    def extract_resume_from_text(self, resume_text: str) -> dict:
        """Parse raw resume text into structured JSON (same schema as LaTeX parser)."""
        from src.ai.prompts.resume_extraction import build_resume_extraction_message

        message = build_resume_extraction_message(resume_text)
        return self._call(
            model=get_active_model("structured"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.1,
        )

    def extract_jd_from_image(self, image_data: bytes, media_type: str) -> dict:
        """Parse a JD screenshot/image into structured JSON via vision model."""
        if not supports_vision():
            raise AIClientError(
                f"{get_provider_display_name()} does not support image input. "
                "Set AI_PROVIDER=anthropic in .env to enable vision, "
                "or paste the JD as text instead."
            )

        from src.ai.prompts.jd_extraction import build_jd_image_message

        message = build_jd_image_message()

        if self._provider == "anthropic":
            return self._call_anthropic_vision(
                model=get_active_model("vision"),
                system=message["system"],
                user_text=message["user"],
                image_b64=base64.b64encode(image_data).decode("utf-8"),
                media_type=media_type,
            )
        else:
            raise AIClientError("Image JD extraction requires Anthropic provider")

    def match_and_suggest(
        self, jd_json: dict, resume_json: dict, rag_context: str = ""
    ) -> dict:
        """
        Score the match between a JD and a resume, and generate suggestions.
        Optionally injects RAG context (similar JDs + historical suggestions).
        """
        from src.ai.prompts.match_scoring import build_match_message

        import json
        jd_str = json.dumps(jd_json, ensure_ascii=False, indent=2)
        resume_str = json.dumps(resume_json, ensure_ascii=False, indent=2)
        message = build_match_message(jd_str, resume_str, rag_context)

        return self._call(
            model=get_active_model("reasoning"),
            system=message["system"],
            user_text=message["user"],
            temperature=0.3,
            max_tokens=8192,  # Large JSON with many suggestions needs headroom
        )

    @property
    def token_usage(self) -> dict:
        return dict(self._token_usage)

    # ── Tool-use chat (Agent) ─────────────────────────

    def chat_raw(
        self,
        system: str,
        user_text: str,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        Call the AI and return raw text — NO JSON parsing.
        Used when the expected response is natural language (reports, explanations).
        """
        from config import get_active_model

        if self._provider == "deepseek":
            return self._call_openai_raw(
                model or get_active_model("agent"), system, user_text, temperature, max_tokens
            )
        else:
            return self._call_anthropic_raw(
                model or get_active_model("agent"), system, user_text, temperature, max_tokens
            )

    def _call_openai_raw(self, model, system, user_text, temperature, max_tokens) -> str:
        """Raw text call via OpenAI SDK — no JSON extraction."""
        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_text},
                    ],
                )
                usage = response.usage
                self._token_usage["input"] += usage.prompt_tokens
                self._token_usage["output"] += usage.completion_tokens
                return response.choices[0].message.content or ""
            except Exception as e:
                error_msg = str(e)
                if "rate" in error_msg.lower() or "429" in error_msg:
                    if attempt == MAX_API_RETRIES:
                        raise
                    wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning("Rate limited. Retrying (attempt %d/%d)", attempt, MAX_API_RETRIES)
                    time.sleep(wait)
                else:
                    raise AIClientError(f"DeepSeek API error: {e}") from e
        raise AIClientError("Max retries exceeded")

    def _call_anthropic_raw(self, model, system, user_text, temperature, max_tokens) -> str:
        """Raw text call via Anthropic SDK — no JSON extraction."""
        import anthropic

        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_text}],
                )
                usage = response.usage
                self._token_usage["input"] += usage.input_tokens
                self._token_usage["output"] += usage.output_tokens
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                return text
            except anthropic.RateLimitError:
                if attempt == MAX_API_RETRIES:
                    raise
                wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning("Rate limited. Retrying (attempt %d/%d)", attempt, MAX_API_RETRIES)
                time.sleep(wait)
            except anthropic.APIError as e:
                raise AIClientError(f"Anthropic API error: {e}") from e
        raise AIClientError("Max retries exceeded")

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Send a multi-turn conversation with tool definitions.

        The model decides whether to respond with text or call a tool.

        Args:
            messages: Conversation history (role: system/user/assistant/tool)
            tools: Tool definitions in provider-native schema
            model: Model name override
            temperature: Response creativity
            max_tokens: Max response tokens

        Returns:
            {"type": "text", "content": "..."}
            or
            {"type": "tool_call", "name": "...", "arguments": {...}}
        """
        if self._provider == "deepseek":
            return self._chat_openai_with_tools(messages, tools, model, temperature, max_tokens)
        else:
            return self._chat_anthropic_with_tools(messages, tools, model, temperature, max_tokens)

    def _chat_openai_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """OpenAI-compatible function calling (DeepSeek, OpenAI, etc.)."""
        from config import get_active_model

        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model or get_active_model("agent"),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto" if tools else None,
                )
                usage = response.usage
                self._token_usage["input"] += usage.prompt_tokens
                self._token_usage["output"] += usage.completion_tokens

                msg = response.choices[0].message
                if msg.tool_calls:
                    import json
                    tc = msg.tool_calls[0]
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    return {
                        "type": "tool_call",
                        "name": tc.function.name,
                        "arguments": args,
                        "call_id": tc.id,
                    }
                return {"type": "text", "content": msg.content or ""}

            except Exception as e:
                error_msg = str(e)
                if "rate" in error_msg.lower() or "429" in error_msg:
                    if attempt == MAX_API_RETRIES:
                        raise
                    wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning("Rate limited. Retrying (attempt %d/%d)", attempt, MAX_API_RETRIES)
                    time.sleep(wait)
                else:
                    raise AIClientError(f"Tool-use chat failed: {e}") from e

        raise AIClientError("Max retries exceeded")

    def _chat_anthropic_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """Anthropic native tool use."""
        import anthropic
        from config import get_active_model

        # Separate system message from conversation
        system_msg = ""
        conversation = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                conversation.append(m)

        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=model or get_active_model("agent"),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_msg,
                    messages=conversation,
                    tools=tools if tools else None,
                )
                usage = response.usage
                self._token_usage["input"] += usage.input_tokens
                self._token_usage["output"] += usage.output_tokens

                if response.stop_reason == "tool_use":
                    for block in response.content:
                        if block.type == "tool_use":
                            return {
                                "type": "tool_call",
                                "name": block.name,
                                "arguments": block.input,
                                "call_id": block.id,
                            }
                    return {"type": "text", "content": "Tool use requested but not found in response"}

                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text
                return {"type": "text", "content": text}

            except anthropic.RateLimitError:
                if attempt == MAX_API_RETRIES:
                    raise
                wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning("Rate limited. Retrying (attempt %d/%d)", attempt, MAX_API_RETRIES)
                time.sleep(wait)
            except anthropic.APIError as e:
                raise AIClientError(f"Anthropic tool-use chat failed: {e}") from e

        raise AIClientError("Max retries exceeded")

    # ── OpenAI-style call (DeepSeek) ────────────────

    def _call(
        self,
        model: str,
        system: str,
        user_text: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """Call the AI. Dispatches to provider-specific implementation."""
        if self._provider == "deepseek":
            return self._call_openai(model, system, user_text, temperature, max_tokens)
        else:
            return self._call_anthropic(model, system, user_text, temperature, max_tokens)

    def _call_openai(
        self,
        model: str,
        system: str,
        user_text: str,
        temperature: float,
        max_tokens: int = 4096,
    ) -> dict:
        """Call DeepSeek via OpenAI SDK with retries."""
        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_text},
                    ],
                )
                usage = response.usage
                self._token_usage["input"] += usage.prompt_tokens
                self._token_usage["output"] += usage.completion_tokens

                content = response.choices[0].message.content
                return _extract_json(content)

            except Exception as e:
                error_msg = str(e)
                if "rate" in error_msg.lower() or "429" in error_msg:
                    if attempt == MAX_API_RETRIES:
                        raise
                    wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Rate limited. Retrying in %.1fs (attempt %d/%d)",
                        wait, attempt, MAX_API_RETRIES,
                    )
                    time.sleep(wait)
                else:
                    raise AIClientError(f"DeepSeek API error: {e}") from e

        raise AIClientError("Max retries exceeded")

    # ── Anthropic calls (fallback) ──────────────────

    def _call_anthropic(
        self,
        model: str,
        system: str,
        user_text: str,
        temperature: float,
        max_tokens: int = 4096,
    ) -> dict:
        """Call Anthropic Claude with retries."""
        import anthropic

        for attempt in range(1, MAX_API_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user_text}],
                )
                usage = response.usage
                self._token_usage["input"] += usage.input_tokens
                self._token_usage["output"] += usage.output_tokens
                return _extract_json(response.content[0].text)

            except anthropic.RateLimitError:
                if attempt == MAX_API_RETRIES:
                    raise
                wait = API_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning("Rate limited. Retrying (attempt %d/%d)", attempt, MAX_API_RETRIES)
                time.sleep(wait)

            except anthropic.APIError as e:
                raise AIClientError(f"Claude API error: {e}") from e

        raise AIClientError("Max retries exceeded")

    def _call_anthropic_vision(
        self,
        model: str,
        system: str,
        user_text: str,
        image_b64: str,
        media_type: str,
    ) -> dict:
        """Call Anthropic Claude with image input."""
        import anthropic

        response = self._client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.1,
            system=system,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }],
        )
        usage = response.usage
        self._token_usage["input"] += usage.input_tokens
        self._token_usage["output"] += usage.output_tokens
        return _extract_json(response.content[0].text)


# ── Singleton ────────────────────────────────────────

_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


def reset_ai_client() -> None:
    global _ai_client
    _ai_client = None


# ── Helpers ─────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extract JSON from AI response, handling markdown fences, thinking text, malformed JSON, and truncation."""
    import json
    import re

    text = text.strip()

    # Step 1: Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove opening fence (```json or ```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Step 2: Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Step 3: Extract JSON block — find outermost {}
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        json_candidate = text[start:end]
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

        # Step 4: Try to repair common JSON issues
        try:
            repaired = _repair_json(json_candidate)
            return json.loads(repaired)
        except (json.JSONDecodeError, Exception):
            pass

        # Step 4b: Try to fix truncated JSON by closing unclosed brackets
        try:
            repaired = _repair_truncated_json(json_candidate)
            return json.loads(repaired)
        except (json.JSONDecodeError, Exception):
            pass

    # Step 5: Last resort — try to find any {...} in the text
    matches = list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text))
    for m in matches:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            continue

    raise AIClientError(
        "Failed to parse JSON from response. The AI response may have been truncated "
        f"(try increasing max_tokens). First 500 chars: {text[:500]}"
    )


def _repair_json(text: str) -> str:
    """Attempt to repair common JSON formatting errors from LLM output."""
    import re

    # Remove trailing commas before } or ]
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)

    # Fix missing commas between string values on separate lines
    # (common LLM error: unquoted newlines in JSON strings)
    # This is best-effort

    # Remove any leading text before the first {
    start = text.find("{")
    if start > 0:
        text = text[start:]

    return text


def _repair_truncated_json(text: str) -> str:
    """Attempt to recover partial JSON by balancing unclosed brackets/braces."""
    # Count opening vs closing
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    # Check if we're inside an unclosed string
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    # If inside a string, close it first
    if in_string:
        text += '"'

    # Close unclosed brackets in correct order
    text += "]" * open_brackets
    text += "}" * open_braces

    return text
