"""Security tests for uploaded files and zip extraction."""

import io
import zipfile

import pytest

from src.utils.file_utils import FileError, extract_zip, save_uploaded_file


class FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return self._data


def test_extract_zip_rejects_parent_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../outside.txt", "do not write")

    with pytest.raises(FileError, match="Unsafe path"):
        extract_zip(archive, tmp_path / "target")

    assert not (tmp_path / "outside.txt").exists()


def test_extract_zip_rejects_windows_style_traversal(tmp_path):
    archive = tmp_path / "unsafe-windows.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("..\\outside.txt", "do not write")

    with pytest.raises(FileError, match="Unsafe path"):
        extract_zip(archive, tmp_path / "target")


def test_extract_zip_allows_normal_project(tmp_path):
    archive = tmp_path / "resume.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("main.tex", "\\documentclass{article}")
        zf.writestr("sections/experience.tex", "Experience")

    files = extract_zip(archive, tmp_path / "target")

    assert len(files) == 2
    assert (tmp_path / "target" / "main.tex").exists()
    assert (tmp_path / "target" / "sections" / "experience.tex").exists()


def test_save_uploaded_file_rejects_path_components(tmp_path):
    upload = FakeUpload("../resume.zip", b"payload")

    with pytest.raises(FileError, match="Unsafe uploaded filename"):
        save_uploaded_file(upload, tmp_path)


def test_save_uploaded_file_uses_plain_filename(tmp_path):
    upload = FakeUpload("resume.zip", b"payload")

    saved = save_uploaded_file(upload, tmp_path)

    assert saved == tmp_path.resolve() / "resume.zip"
    assert saved.read_bytes() == b"payload"
