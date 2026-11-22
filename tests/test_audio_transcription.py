"""Tests for safe interview audio validation, transcription, and retention."""

import io
import wave
from types import SimpleNamespace

import pytest

from src.core.audio_transcription import (
    AudioTranscriptionError,
    remove_interview_audio,
    save_interview_audio,
    transcribe_interview_audio,
    validate_interview_audio,
)


def _wav_bytes(*, duration_seconds=1, frame_rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(1)
        audio.setframerate(frame_rate)
        audio.writeframes(b"\x80" * int(duration_seconds * frame_rate))
    return buffer.getvalue()


class FakeTranscriptions:
    def __init__(self, text="Confirmed transcript"):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


class FakeAudioClient:
    def __init__(self, text="Confirmed transcript"):
        self.transcriptions = FakeTranscriptions(text)
        self.audio = SimpleNamespace(transcriptions=self.transcriptions)


def test_wav_validation_returns_safe_name_and_duration():
    safe_name, duration = validate_interview_audio(
        _wav_bytes(duration_seconds=2),
        "answer.wav",
    )

    assert safe_name == "answer.wav"
    assert duration == 2.0


@pytest.mark.parametrize(
    ("filename", "error"),
    [
        ("../answer.wav", "Unsafe audio filename"),
        ("answer.exe", "Unsupported audio type"),
    ],
)
def test_unsafe_or_unsupported_audio_is_rejected(filename, error):
    with pytest.raises(AudioTranscriptionError, match=error):
        validate_interview_audio(_wav_bytes(), filename)


def test_empty_and_oversized_audio_are_rejected(monkeypatch):
    with pytest.raises(AudioTranscriptionError, match="empty"):
        validate_interview_audio(b"", "answer.wav")

    monkeypatch.setattr("src.core.audio_transcription.MAX_INTERVIEW_AUDIO_SIZE_MB", 0)
    with pytest.raises(AudioTranscriptionError, match="too large"):
        validate_interview_audio(_wav_bytes(), "answer.wav")


def test_browser_wav_duration_limit_is_enforced():
    with pytest.raises(AudioTranscriptionError, match="too long"):
        validate_interview_audio(
            _wav_bytes(duration_seconds=301, frame_rate=1),
            "long.wav",
        )


def test_transcription_uses_configured_model_and_keeps_audio_in_memory():
    client = FakeAudioClient("这是可编辑的转写草稿。")
    audio = _wav_bytes()

    result = transcribe_interview_audio(
        audio,
        "answer.wav",
        "audio/wav",
        client=client,
    )

    assert result.text == "这是可编辑的转写草稿。"
    assert result.size_bytes == len(audio)
    call = client.transcriptions.calls[0]
    assert call["model"]
    assert call["file"] == ("answer.wav", audio, "audio/wav")


def test_empty_transcription_is_rejected():
    with pytest.raises(AudioTranscriptionError, match="empty text"):
        transcribe_interview_audio(
            _wav_bytes(),
            "answer.wav",
            "audio/wav",
            client=FakeAudioClient("   "),
        )


def test_audio_is_saved_under_generated_name_and_can_be_removed(tmp_path):
    root = tmp_path / "audio"
    audio = _wav_bytes()

    path = save_interview_audio(
        audio,
        "candidate-answer.wav",
        17,
        audio_dir=root,
    )

    assert path.parent == (root / "question_17").resolve()
    assert path.name != "candidate-answer.wav"
    assert path.suffix == ".wav"
    assert path.read_bytes() == audio
    remove_interview_audio(path, audio_dir=root)
    assert not path.exists()


def test_audio_removal_refuses_paths_outside_configured_root(tmp_path):
    outside = tmp_path / "outside.wav"
    outside.write_bytes(_wav_bytes())

    with pytest.raises(AudioTranscriptionError, match="outside"):
        remove_interview_audio(outside, audio_dir=tmp_path / "audio")

    assert outside.exists()
