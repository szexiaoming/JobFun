"""Static dependency guards for the Phase 4 service boundary."""

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIRS = (
    PROJECT_ROOT / "src" / "core",
    PROJECT_ROOT / "src" / "ai",
    PROJECT_ROOT / "src" / "agent",
    PROJECT_ROOT / "src" / "db",
    PROJECT_ROOT / "src" / "services",
    PROJECT_ROOT / "src" / "repositories",
)


def _python_files(*directories: Path):
    for directory in directories:
        if directory.exists():
            yield from directory.rglob("*.py")


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _violations(directories: tuple[Path, ...], forbidden: set[str]) -> list[str]:
    violations = []
    for path in _python_files(*directories):
        imported = _import_roots(path)
        blocked = sorted(imported & forbidden)
        if blocked:
            relative = path.relative_to(PROJECT_ROOT)
            violations.append(f"{relative}: {', '.join(blocked)}")
    return violations


def test_backend_layers_do_not_depend_on_presentation_code():
    violations = _violations(BACKEND_DIRS, {"streamlit", "ui", "app"})
    assert violations == [], "Presentation dependencies crossed inward: " + "; ".join(violations)


def test_core_and_data_layers_remain_transport_agnostic():
    violations = _violations(BACKEND_DIRS, {"fastapi", "starlette"})
    assert violations == [], "HTTP framework leaked into reusable backend: " + "; ".join(violations)


def test_future_api_adapter_cannot_import_streamlit_or_ui():
    api_dir = PROJECT_ROOT / "src" / "api"
    violations = _violations((api_dir,), {"streamlit", "ui"})
    assert violations == [], "API adapter depends on Streamlit UI: " + "; ".join(violations)


def test_api_routes_do_not_import_database_or_sqlite_adapters():
    route_dir = PROJECT_ROOT / "src" / "api" / "routes"
    violations = []
    for path in _python_files(route_dir):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(("src.db", "src.repositories.sqlite")):
                    violations.append(str(path.relative_to(PROJECT_ROOT)))
    assert violations == [], "API routes bypass service boundaries: " + "; ".join(violations)
