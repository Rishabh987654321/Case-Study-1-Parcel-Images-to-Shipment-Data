# AGENTS.md: Working rules for the coding agent

## Project
Prozo EIR take-home, **Case Study 1: Parcel Images to Shipment Data**. A web app where a warehouse user bulk-uploads parcel photos (hundreds). The system reads the courier label on each photo and returns one structured record per image (AWB/tracking number, weight, dimensions) or an honest status flag. The whole batch is downloadable as CSV.

Cases 2 and 3 are separate apps built later. Do not build them now.

## Non-negotiables
1. **A wrong extraction is worse than a flag.** When evidence is weak, abstain and flag. Never guess or "fix" digits without validation.
2. **Free only.** No paid APIs and no required API keys. The default path runs fully locally. Optional enhancements (local Ollama model, CLIP) are off by default and must degrade gracefully.
3. **Runs from a clean clone in under 15 minutes** with documented commands for Windows and macOS/Linux.
4. **The author must be able to explain and live-edit every line.** Prefer simple, readable code to clever abstractions. Small modules, clear names, comments that explain *why*.
5. **Large batches never freeze the UI.** Work runs in the background; the user can leave and return to results.
6. **Bad input never crashes the app** (corrupt, empty, wrong type, oversized, nonsense): clear message, no stack trace to the client.
7. **No secrets in the repo.** Provide `.env.example` only.
8. **Do not invent facts about the dataset or courier label formats.** Inspect the real images first (Phase 0) and record what you saw in `docs/dataset-notes.md`.

## Source of truth (read before coding)
`docs/architecture.md`, `docs/flag_taxonomy.md`, `docs/data_model.md`, `docs/api.md`, `docs/design.md`, `docs/phases.md`, `docs/evaluation.md`.
If a doc conflicts with reality, update the doc in the same change and say so in your report.

## Workflow
- Work **one phase at a time** (`docs/phases.md`). Do not start the next phase until told.
- At phase start: give your plan in 10 bullets or fewer, plus assumptions and questions.
- At phase end: run the tests and the phase's acceptance checks, then report briefly: what was built, how to run and verify, what is deferred, risks.
- Ask instead of guessing when a decision would change the architecture, the API or the flag taxonomy.
- Make small commits with clear messages.
- Never remove or weaken a test to make it pass.

## Stack and conventions
- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 with SQLite (WAL), pytest, ruff. Type hints on public functions.
- Pipeline code (`backend/app/pipeline/`) is pure Python with no web imports, so it runs from the CLI and from workers.
- Frontend: React + TypeScript + Vite, TanStack Query, Tailwind CSS. No heavy UI library.
- Pin dependency versions in `requirements.txt` and `package.json` lockfile.
- Configuration through environment variables read in one place (`config.py`); thresholds are named constants with defaults, not magic numbers.
- Logging: standard `logging`, structured enough to debug; never log full OCR text of labels at INFO level.
- Errors: use the JSON shape in `docs/api.md`; keep stack traces in logs.
- File handling: validate by content, use generated ids, never trust client file names.

## Definition of done (every phase)
- Code runs from a clean virtual environment using the commands in the README.
- Tests for the new code exist and pass (`pytest` for backend).
- `ruff` is clean.
- Docs touched by the change are updated.
- The phase report is written.
