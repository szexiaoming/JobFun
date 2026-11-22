# AGENTS.md

This file describes the current JobFun repository for coding agents.

## Product guardrail

JobFun is an evidence-first job application assistant. AI may reorganize or improve wording only from evidence supplied by the user. It must never invent employers, projects, dates, skills, results, or interview experiences.

## Current architecture

- `web/`: Next.js PWA and same-origin BFF. Read `web/AGENTS.md` before changing it, and use the installed Next.js documentation under `web/node_modules/next/dist/docs/` for framework behavior.
- `src/api/`: FastAPI HTTP layer, bearer-token authentication, dependency wiring, health routes, and operational commands.
- `src/services/`: application services and ownership-aware workflows.
- `src/repositories/`: persistence boundaries for SQLite and PostgreSQL adapters.
- `src/db/`: dataclass models and database adapters. Models are plain dataclasses, not an ORM.
- `src/storage/`: private local and S3-compatible object storage adapters.
- `src/core/`, `src/agent/`, `src/ai/`: evidence matching, orchestration, and model-provider integrations.
- `ui/` and `app.py`: legacy Streamlit client, which must continue to pass regression tests while the Next.js client is developed.

The application supports DeepSeek and Anthropic for language tasks, plus OpenAI speech-to-text for the optional interview transcription path. Do not hardcode credentials or model prompts in business logic.

## Engineering rules

- Keep FastAPI routes thin; call application services rather than generic database CRUD.
- Enforce user ownership on the server. Do not trust browser IDs, query parameters, or hidden fields.
- Keep bearer tokens in the same-origin BFF/HttpOnly cookie flow; never expose them to browser scripts.
- Store uploaded files privately. Public responses must not include object keys, server paths, credentials, raw provider errors, or another user's data.
- Every write endpoint must preserve idempotency and the existing status transitions.
- Put prompt templates under `src/ai/prompts/`.
- Keep database changes compatible with both SQLite and PostgreSQL; update dataclass table allowlists and adapter contract tests together.
- Preserve unrelated user changes and keep each iteration scoped to its documented goal in `docs/careerpilot-development-plan.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Set-Location web
npm run check
```

The optional live PostgreSQL contract test is skipped unless `TEST_POSTGRES_DSN` points to an isolated test database. Browser preview is local only unless the user explicitly requests publishing or deployment.

## Key documents

- `docs/careerpilot-development-plan.md`: iteration history and next planned work.
- `docs/phase4-service-architecture.md`: service boundaries and migration decisions.
- `docs/operations-runbook.md`: health checks, workers, cleanup jobs, alerts, and release gates.
- `docs/staging-release-rehearsal.md`: isolated PostgreSQL/S3 rehearsal procedure.
