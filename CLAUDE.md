# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI JobFun is a personal project — an AI-powered job application assistant. Users upload Overleaf LaTeX resumes and job descriptions; the system analyzes match scores, suggests wording improvements, and (with user approval) modifies LaTeX source to generate tailored PDFs.

**Core principle**: AI must never fabricate experiences, projects, or skills. It only optimizes phrasing and emphasis.

## Tech Stack

- **Language**: Python 3.11+
- **UI**: Streamlit (single-machine, no auth)
- **AI**: Claude API via `anthropic` SDK (models: Haiku for extraction, Opus for reasoning, Sonnet for balanced tasks)
- **Vector DB**: ChromaDB (Phase 2+, local persistence)
- **Relational DB**: SQLite via `sqlite3` (zero-config, single file at `data/sqlite/jobfun.db`)
- **Version Control**: GitPython for LaTeX modification history
- **PDF**: pdflatex / xelatex (system dependency, not pip)

## Development Phases

See `docs/development-plan.md` for full details. Summary:

| Phase | What | Key Files |
|-------|------|-----------|
| 1 — MVP | Upload resume + JD → match score + suggestions (read-only) | `src/core/jd_parser.py`, `src/core/latex_parser.py`, `src/core/match_engine.py` |
| 2 — RAG | ChromaDB vector storage, similar JD retrieval, suggestion reuse | `src/core/retriever.py`, `src/db/chroma_client.py` |
| 3 — LaTeX Mod | Apply suggestions to .tex files with Git versioning and safety validation | `src/core/latex_modifier.py`, `src/latex/validator.py`, `src/utils/git_utils.py` |
| 4 — PDF | Compile LaTeX → PDF, auto-fix compile errors | `src/core/pdf_compiler.py`, `src/latex/compiler.py` |
| 5 — Tracker | Kanban board, interview question generator, analytics dashboard | `src/core/progress_manager.py`, `src/core/interview_generator.py` |

## Key Architecture Decisions

### LaTeX Handling

LaTeX is parsed heuristically (not a full compiler). An AST-like structure extracts sections → entries → bullets. Modifications target entry/bullet granularity only — never preamble, cls files, or macros.

```
LaTeX files → Parser → {sections: [{title, entries: [{header, bullets}]}]}
```

### Safety Constraints (multi-layer, Phase 3+)

1. **Prompt layer**: System prompt hard-constrains "no fabrication"
2. **Validation layer**: Post-modification checks — company names, dates, and entry count must not change
3. **Git layer**: Every modification is a commit; revert available at any time
4. **User confirmation**: Diff displayed before final commit

### JD Input

Three input modes, all first-class:
- **Text paste** → Claude API extraction
- **Image upload** → Claude Vision (OCR + extraction in one call)
- **PDF upload** → PyPDF2 text extraction → Claude API (Phase v0.3+)

All normalize to a unified JD structured JSON schema (see `docs/product-design.md` §2.1).

### Claude Model Selection

| Task | Model | Why |
|------|-------|-----|
| JD extraction (text) | Haiku | Fast, cheap, structured output via Tool Use |
| JD extraction (image) | Sonnet | Vision capability required |
| Match scoring | Opus + Thinking | Deep multi-dimensional reasoning |
| Suggestions | Sonnet | Balanced quality/cost |
| LaTeX editing | Opus | Needs precise LaTeX understanding |
| Interview questions | Sonnet | Structured generation |

## Project Conventions

- All new code in `src/`, all UI in `ui/`, all AI prompts in `src/ai/prompts/`
- Prompt templates are Python files returning formatted strings — never hardcode prompts in business logic
- Database models use Python dataclasses, not ORM
- Streamlit pages are separate modules under `ui/`; `app.py` only handles routing
- LaTeX parsing utilities live in `src/latex/`, not `src/core/`

## Custom Slash Commands

Four Claude Code custom commands planned (`.claude/commands/`):

| Command | Purpose | Active After |
|---------|---------|-------------|
| `/analyze` | Upload resume + JD → match report | Phase 1 |
| `/suggest` | Generate more/focused suggestions | Phase 1 |
| `/apply` | Execute LaTeX modifications | Phase 3 |
| `/prep` | Generate interview questions | Phase 5 |

## Running the Project

```bash
# Install dependencies (cumulative by phase)
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY

# Launch web UI
streamlit run app.py

# Launch the Phase 4 API skeleton (development only)
uvicorn src.api.app:app --reload

# Issue a local bearer token for an existing user (shown once)
python -m src.api.provision_token --user-id 1 --days 30

# Process queued AI jobs in a separate local worker
python -m src.api.run_jobs --limit 10

# Run tests
pytest tests/ -v
pytest tests/test_match_engine.py -v  # single file

# Phase 4: check LaTeX compiler availability
pdflatex --version || echo "Install TeX Live or MiKTeX"
```

## Important Files

- `docs/product-design.md` — Complete product spec, architecture, DB schema, wireframes
- `docs/development-plan.md` — Phase-by-phase breakdown with files, deps, I/O, test strategy
- `docs/phase4-service-architecture.md` — Service boundaries, ownership rules, and API migration sequence
- `config.py` — All paths, API config, constants (to be created in Phase 1)
