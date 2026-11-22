"""
Global configuration for AI JobFun.
Reads from environment variables with sensible defaults.

Supports two AI providers:
  - deepseek (default): DeepSeek API via OpenAI SDK
  - anthropic: Anthropic Claude API via Anthropic SDK (vision support)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", DATA_DIR / "sqlite" / "jobfun.db"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", DATA_DIR / "uploads"))
RESUME_DIR = Path(os.getenv("RESUME_DIR", DATA_DIR / "resumes"))
INTERVIEW_AUDIO_DIR = Path(
    os.getenv("INTERVIEW_AUDIO_DIR", DATA_DIR / "interview_audio")
)
OBJECT_STORAGE_DIR = Path(
    os.getenv("OBJECT_STORAGE_DIR", DATA_DIR / "objects")
)

# ── Service persistence adapters ─────────────────────
DATABASE_BACKEND = os.getenv("DATABASE_BACKEND", "sqlite").strip().lower()
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "").strip()
OBJECT_STORAGE_BACKEND = os.getenv("OBJECT_STORAGE_BACKEND", "local").strip().lower()
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_REGION = os.getenv("S3_REGION", "").strip()
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip()
S3_KMS_KEY_ID = os.getenv("S3_KMS_KEY_ID", "").strip()

# ── Operations and alerting ───────────────────────────
LOG_FORMAT = os.getenv("JOBFUN_LOG_FORMAT", "text").strip().lower()
WORKER_NAME = os.getenv("JOBFUN_WORKER_NAME", "default").strip() or "default"
WORKER_HEARTBEAT_MAX_AGE_SECONDS = int(
    os.getenv("JOBFUN_WORKER_HEARTBEAT_MAX_AGE_SECONDS", "120")
)
WORKER_QUEUE_MAX_AGE_SECONDS = int(
    os.getenv("JOBFUN_WORKER_QUEUE_MAX_AGE_SECONDS", "300")
)
WORKER_RUNNING_STALE_SECONDS = int(
    os.getenv("JOBFUN_WORKER_RUNNING_STALE_SECONDS", "900")
)
ALERT_WEBHOOK_URL = os.getenv("JOBFUN_ALERT_WEBHOOK_URL", "").strip()
ALERT_WEBHOOK_BEARER_TOKEN = os.getenv(
    "JOBFUN_ALERT_WEBHOOK_BEARER_TOKEN", ""
).strip()
ALERT_WEBHOOK_TIMEOUT_SECONDS = float(
    os.getenv("JOBFUN_ALERT_WEBHOOK_TIMEOUT_SECONDS", "5")
)

# ── AI Provider ────────────────────────────────────────
# "deepseek" or "anthropic"
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")

# ── DeepSeek (OpenAI-compatible) ───────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# DeepSeek model selection by capability
DEEPSEEK_MODEL_FAST = os.getenv("DEEPSEEK_MODEL_FAST", "deepseek-chat")
DEEPSEEK_MODEL_REASONING = os.getenv("DEEPSEEK_MODEL_REASONING", "deepseek-reasoner")

# ── Anthropic (optional, for vision support) ───────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# ── Speech-to-text (independent OpenAI capability) ─────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TRANSCRIPTION_MODEL = os.getenv(
    "OPENAI_TRANSCRIPTION_MODEL",
    "gpt-transcribe",
)
MAX_INTERVIEW_AUDIO_SIZE_MB = 10
MAX_INTERVIEW_AUDIO_DURATION_SECONDS = 300
RETAINED_AUDIO_MAX_DAYS = int(os.getenv("JOBFUN_RETAINED_AUDIO_MAX_DAYS", "30"))
AUDIO_CLEANUP_MAX_AGE_HOURS = int(
    os.getenv("JOBFUN_AUDIO_CLEANUP_MAX_AGE_HOURS", "36")
)
AUDIO_CLEANUP_STALE_SECONDS = int(
    os.getenv("JOBFUN_AUDIO_CLEANUP_STALE_SECONDS", "1800")
)
AUDIO_CLEANUP_FAILURE_THRESHOLD = int(
    os.getenv("JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD", "2")
)
MAINTENANCE_HISTORY_MAX_ROWS = int(
    os.getenv("JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS", "90")
)
MAINTENANCE_EXPORT_ACTIVE_KEY_ID = os.getenv(
    "JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID", ""
).strip()
MAINTENANCE_EXPORT_HMAC_KEYS_JSON = os.getenv(
    "JOBFUN_MAINTENANCE_EXPORT_HMAC_KEYS_JSON", ""
).strip()
ALLOWED_INTERVIEW_AUDIO_EXTENSIONS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"
}

SUPPORTED_AI_PROVIDERS = {"deepseek", "anthropic"}
AI_CAPABILITIES = {"structured", "reasoning", "vision", "agent", "evaluation"}
_CAPABILITY_ALIASES = {"fast": "structured"}
_PROVIDER_DISPLAY_NAMES = {
    "deepseek": "DeepSeek",
    "anthropic": "Anthropic Claude",
}

# ── Rate Limiting ──────────────────────────────────────
MAX_API_RETRIES = 3
API_RETRY_DELAY = 2.0  # seconds

# ── File Upload ────────────────────────────────────────
MAX_UPLOAD_SIZE_MB = 50
MAX_DATA_EXPORT_SIZE_MB = int(os.getenv("MAX_DATA_EXPORT_SIZE_MB", "250"))
ALLOWED_RESUME_EXTENSIONS = {".zip", ".txt", ".pdf"}
ALLOWED_JD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def ensure_dirs() -> None:
    """Create all required runtime directories."""
    for d in [
        DATA_DIR,
        SQLITE_PATH.parent,
        UPLOAD_DIR,
        RESUME_DIR,
        INTERVIEW_AUDIO_DIR,
        OBJECT_STORAGE_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def get_provider_display_name(provider: str | None = None) -> str:
    """Return a user-facing provider name without exposing credentials."""
    selected = (provider or AI_PROVIDER).strip().lower()
    return _PROVIDER_DISPLAY_NAMES.get(selected, selected or "Unknown AI")


def supports_capability(capability: str, provider: str | None = None) -> bool:
    """Return whether a provider supports a configured AI capability."""
    selected = (provider or AI_PROVIDER).strip().lower()
    normalized = _CAPABILITY_ALIASES.get(capability, capability)
    if selected not in SUPPORTED_AI_PROVIDERS or normalized not in AI_CAPABILITIES:
        return False
    return not (normalized == "vision" and selected == "deepseek")


def get_active_model(capability: str = "structured") -> str:
    """Resolve one capability to a model for the configured provider."""
    provider = AI_PROVIDER.strip().lower()
    normalized = _CAPABILITY_ALIASES.get(capability, capability)

    if provider not in SUPPORTED_AI_PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {AI_PROVIDER}")
    if normalized not in AI_CAPABILITIES:
        raise ValueError(f"Unknown AI capability: {capability}")
    if not supports_capability(normalized, provider):
        raise ValueError(
            f"{get_provider_display_name(provider)} does not support "
            f"the '{normalized}' capability"
        )

    if provider == "deepseek":
        if normalized == "reasoning":
            return DEEPSEEK_MODEL_REASONING
        return DEEPSEEK_MODEL_FAST

    # Anthropic currently uses one configurable model for every capability.
    # The routing API lets individual capability models be introduced later
    # without changing business code.
    return ANTHROPIC_MODEL


def get_ai_runtime_label(capability: str = "structured") -> str:
    """Return a concise provider/model label for diagnostics and settings UI."""
    return f"{get_provider_display_name()} · {get_active_model(capability)}"


def supports_vision() -> bool:
    """Check if the current provider supports image input."""
    return supports_capability("vision")


def is_transcription_configured() -> bool:
    """Return whether the independent OpenAI transcription key is available."""
    return bool(OPENAI_API_KEY.strip())


def get_transcription_runtime_label() -> str:
    """Return the configured speech-to-text provider and model."""
    return f"OpenAI · {OPENAI_TRANSCRIPTION_MODEL}"
