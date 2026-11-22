"""Validate, transcribe, optionally retain, and remove interview audio."""

from __future__ import annotations

import io
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from openai import OpenAI

from config import (
    ALLOWED_INTERVIEW_AUDIO_EXTENSIONS,
    API_RETRY_DELAY,
    INTERVIEW_AUDIO_DIR,
    MAX_API_RETRIES,
    MAX_INTERVIEW_AUDIO_DURATION_SECONDS,
    MAX_INTERVIEW_AUDIO_SIZE_MB,
    OPENAI_API_KEY,
    OPENAI_TRANSCRIPTION_MODEL,
)


class AudioTranscriptionError(Exception):
    """Raised when audio is unsafe, unsupported, or cannot be transcribed."""


@dataclass(frozen=True)
class AudioTranscription:
    text: str
    filename: str
    content_type: str
    size_bytes: int
    duration_seconds: Optional[float]


def transcribe_interview_audio(
    audio_bytes: bytes,
    filename: str,
    content_type: str = "",
    *,
    client=None,
) -> AudioTranscription:
    """Validate an audio payload and return an in-memory transcript draft."""
    safe_name, duration = validate_interview_audio(audio_bytes, filename)
    transcription_client = client
    if transcription_client is None:
        if not OPENAI_API_KEY.strip():
            raise AudioTranscriptionError(
                "OPENAI_API_KEY is required for interview audio transcription"
            )
        transcription_client = OpenAI(api_key=OPENAI_API_KEY)

    response = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            response = transcription_client.audio.transcriptions.create(
                model=OPENAI_TRANSCRIPTION_MODEL,
                file=(safe_name, audio_bytes, content_type or "application/octet-stream"),
            )
            break
        except Exception as exc:
            if attempt == MAX_API_RETRIES:
                raise AudioTranscriptionError(
                    f"Audio transcription failed: {exc}"
                ) from exc
            time.sleep(API_RETRY_DELAY * (2 ** (attempt - 1)))

    text = str(getattr(response, "text", response) or "").strip()
    if not text:
        raise AudioTranscriptionError("Audio transcription returned empty text")
    return AudioTranscription(
        text=text,
        filename=safe_name,
        content_type=content_type or "application/octet-stream",
        size_bytes=len(audio_bytes),
        duration_seconds=duration,
    )


def validate_interview_audio(
    audio_bytes: bytes,
    filename: str,
) -> tuple[str, Optional[float]]:
    """Validate filename, extension, size, and WAV duration when available."""
    if not isinstance(audio_bytes, bytes) or not audio_bytes:
        raise AudioTranscriptionError("Audio file is empty")
    safe_name = _safe_audio_name(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_INTERVIEW_AUDIO_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_INTERVIEW_AUDIO_EXTENSIONS))
        raise AudioTranscriptionError(
            f"Unsupported audio type: {extension or 'none'}. Allowed: {allowed}"
        )
    max_bytes = MAX_INTERVIEW_AUDIO_SIZE_MB * 1024 * 1024
    if len(audio_bytes) > max_bytes:
        raise AudioTranscriptionError(
            f"Audio file is too large (maximum {MAX_INTERVIEW_AUDIO_SIZE_MB} MB)"
        )

    duration = _wav_duration_seconds(audio_bytes) if extension == ".wav" else None
    if (
        duration is not None
        and duration > MAX_INTERVIEW_AUDIO_DURATION_SECONDS
    ):
        raise AudioTranscriptionError(
            "Audio recording is too long "
            f"(maximum {MAX_INTERVIEW_AUDIO_DURATION_SECONDS // 60} minutes)"
        )
    return safe_name, duration


def save_interview_audio(
    audio_bytes: bytes,
    filename: str,
    question_id: int,
    *,
    audio_dir: Optional[Path] = None,
) -> Path:
    """Persist validated audio under an internal generated filename."""
    safe_name, _ = validate_interview_audio(audio_bytes, filename)
    root = Path(audio_dir or INTERVIEW_AUDIO_DIR).resolve()
    target_dir = (root / f"question_{int(question_id)}").resolve()
    if target_dir != root and root not in target_dir.parents:
        raise AudioTranscriptionError("Unsafe interview audio destination")
    target_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(safe_name).suffix.lower()
    destination = target_dir / f"{uuid.uuid4().hex[:12]}{extension}"
    destination.write_bytes(audio_bytes)
    return destination


def remove_interview_audio(
    path: str | Path,
    *,
    audio_dir: Optional[Path] = None,
) -> None:
    """Remove only a retained audio file inside the configured audio root."""
    root = Path(audio_dir or INTERVIEW_AUDIO_DIR).resolve()
    target = Path(path).resolve()
    if target == root or root not in target.parents:
        raise AudioTranscriptionError("Refusing to remove audio outside the configured directory")
    if target.is_file():
        target.unlink()


def _safe_audio_name(filename: str) -> str:
    normalized = str(filename or "").replace("\\", "/")
    basename = PurePosixPath(normalized).name
    if (
        not basename
        or basename in {".", ".."}
        or basename != normalized
        or "\x00" in basename
        or ":" in basename
    ):
        raise AudioTranscriptionError("Unsafe audio filename")
    return basename


def _wav_duration_seconds(audio_bytes: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as audio:
            frame_rate = audio.getframerate()
            if frame_rate <= 0:
                return None
            return round(audio.getnframes() / frame_rate, 2)
    except (wave.Error, EOFError):
        raise AudioTranscriptionError("Invalid WAV audio file")
