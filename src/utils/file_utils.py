"""
File operations: zip extraction, validation, path helpers.
"""

import shutil
import stat
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional

from config import ALLOWED_RESUME_EXTENSIONS, ALLOWED_JD_IMAGE_EXTENSIONS, MAX_UPLOAD_SIZE_MB
from src.utils.logger import logger


class FileError(Exception):
    """Raised when file validation or extraction fails."""


def validate_file_size(file_path: Path) -> None:
    """Check file does not exceed size limit."""
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_SIZE_MB:
        raise FileError(
            f"File too large: {size_mb:.1f}MB (max {MAX_UPLOAD_SIZE_MB}MB)"
        )


def validate_extension(file_path: Path, allowed: set[str]) -> None:
    """Check file extension is in the allowed set."""
    ext = file_path.suffix.lower()
    if ext not in allowed:
        raise FileError(f"Unsupported file type: {ext}. Allowed: {allowed}")


def extract_zip(zip_path: Path, target_dir: Path) -> list[Path]:
    """
    Extract a zip file into target_dir, returning list of extracted file paths.
    Raises FileError if zip is invalid or empty.
    """
    if not zipfile.is_zipfile(zip_path):
        raise FileError(f"Not a valid zip file: {zip_path}")

    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    max_files = 500
    max_uncompressed_bytes = MAX_UPLOAD_SIZE_MB * 5 * 1024 * 1024

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            if len(members) > max_files:
                raise FileError(
                    f"Zip contains too many entries: {len(members)} (max {max_files})"
                )

            total_size = sum(info.file_size for info in members)
            if total_size > max_uncompressed_bytes:
                limit_mb = max_uncompressed_bytes / (1024 * 1024)
                raise FileError(
                    f"Zip expands to {total_size / (1024 * 1024):.1f}MB "
                    f"(max {limit_mb:.0f}MB)"
                )

            extracted: list[Path] = []
            for info in members:
                member = _safe_zip_member(info)
                destination = (target_root / Path(*member.parts)).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise FileError(f"Unsafe path in zip: {info.filename}")

                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue

                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as source, open(destination, "wb") as output:
                    shutil.copyfileobj(source, output)
                extracted.append(destination)
    except zipfile.BadZipFile as e:
        raise FileError(f"Corrupted zip file: {e}") from e
    except OSError as e:
        raise FileError(f"Failed to extract zip: {e}") from e

    if not extracted:
        raise FileError(f"Zip file is empty: {zip_path}")

    logger.info("Extracted %d files to %s", len(extracted), target_dir)
    return extracted


def _safe_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    """Validate one zip member and return its normalized relative path."""
    normalized_name = info.filename.replace("\\", "/")
    member = PurePosixPath(normalized_name)
    unix_mode = info.external_attr >> 16

    if not normalized_name or member.is_absolute() or ".." in member.parts:
        raise FileError(f"Unsafe path in zip: {info.filename}")
    if member.parts and ":" in member.parts[0]:
        raise FileError(f"Unsafe drive path in zip: {info.filename}")
    if stat.S_ISLNK(unix_mode):
        raise FileError(f"Symbolic links are not allowed in zip: {info.filename}")

    return member


def find_main_tex(base_dir: Path) -> Path:
    """
    Locate main.tex in a LaTeX project directory.
    Checks common patterns: main.tex, root .tex, or the .tex containing \\documentclass.
    """
    # Direct match
    main = base_dir / "main.tex"
    if main.exists():
        return main

    # Search one level deep
    for tex in base_dir.glob("*.tex"):
        if tex.name.lower() == "main.tex":
            return tex

    # Fallback: find .tex with \documentclass
    for tex in base_dir.rglob("*.tex"):
        content = tex.read_text(encoding="utf-8", errors="ignore")
        if r"\documentclass" in content:
            return tex

    raise FileError(f"No main.tex found in {base_dir}")


def collect_tex_files(base_dir: Path) -> dict[str, str]:
    """
    Collect all .tex and .cls files in a LaTeX project.
    Returns {relative_path: content} dict.
    """
    files: dict[str, str] = {}
    for tex in sorted(base_dir.rglob("*.tex")):
        rel = tex.relative_to(base_dir).as_posix()
        files[rel] = tex.read_text(encoding="utf-8", errors="ignore")
    for cls in sorted(base_dir.rglob("*.cls")):
        rel = cls.relative_to(base_dir).as_posix()
        files[rel] = cls.read_text(encoding="utf-8", errors="ignore")
    return files


def save_uploaded_file(uploaded_file, target_dir: Path) -> Path:
    """
    Save a Streamlit UploadedFile to target_dir.
    Returns the saved path.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_upload_name(uploaded_file.name)
    dest = target_dir.resolve() / filename
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    logger.info("Saved uploaded file: %s", dest)
    return dest


def _safe_upload_name(filename: str) -> str:
    """Reject path components and invalid names from an uploaded filename."""
    normalized = filename.replace("\\", "/")
    basename = PurePosixPath(normalized).name
    if not basename or basename in {".", ".."} or basename != normalized:
        raise FileError(f"Unsafe uploaded filename: {filename}")
    if "\x00" in basename or ":" in basename:
        raise FileError(f"Unsafe uploaded filename: {filename}")
    return basename


def cleanup_dir(dir_path: Path) -> None:
    """Remove a directory tree if it exists."""
    if dir_path.exists():
        shutil.rmtree(dir_path)
