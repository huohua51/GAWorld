# GAWorld — Agentic City Simulator

## Project Overview

Multi-agent LLM-powered city simulation platform. Agents with profiles live in a map, interact, form relationships, participate in an economy, and generate emergent social behavior.

**Tech stack:** Python 3.11+ (simulator + dashboard), vanilla JS + Chart.js 4.x (frontend), no build tools for dashboard.

**Key modules:**
- `generative_city_sim.py` — main entrypoint, agent loop, LLM routing, action scheduling
- `dashboard_server.py` — `http.server`-based dashboard with REST API and static file serving
- `economy_module.py` — agent economy (ledger, markets)
- `environment.py` — environment events engine
- `gaworld/` — cross-cutting concerns (typed config, logging, IO, core agent dataclass)

## Architecture

### Simulator → CSV/JSON output → Dashboard

```
Simulator (Python) → output/{economy, memory, logs, plots}/*.csv, *.json
                          ↓
Dashboard (Python http.server + vanilla JS)
  ├── REST API:   /api/agents, /api/economy, /api/state-history, /api/run
  └── Frontend:   site/dashboard/ (index.html, app.js, charts.js, styles.css)
```

- Dashboard is a single-file Python server (`dashboard_server.py`) using `http.server`
- Frontend is vanilla JS + Chart.js 4.x (loaded from CDN)
- All data comes from CSV/JSON files in `output/` — no database
- No build step required for frontend

## Development Workflow

Follow this workflow sequence for all feature work:

```
brainstorming → writing-plans → grill-with-docs → 
subagent-driven-development → test-driven-development → 
code-review → security-review → finishing-a-development-branch
```

- **brainstorming** — clarify requirements, explore approaches, write spec
- **writing-plans** — create implementation plan with task breakdown
- **grill-with-docs** — research existing solutions, docs, APIs before implementation
- **subagent-driven-development** — dispatch fresh subagent per task with two-stage review
- **test-driven-development** — write tests first (RED→GREEN→IMPROVE), 80%+ coverage
- **code-review** — review all changes for correctness, patterns, maintainability
- **security-review** — check for injection, secrets, XSS, path traversal
- **finishing-a-development-branch** — final commit, changelog, PR prep

### Debugging

Use **diagnose** skill when troubleshooting failures.

## Commands

```bash
# Run simulation
python generative_city_sim.py run

# Start dashboard (dev)
python dashboard_server.py --port 8767

# Run tests
python -m pytest tests/ -q --tb=short

# Lint & format
ruff check .
ruff format --check .
black . --check

# Type check (strict on gaworld/ tree)
mypy gaworld
```

## Coding Conventions

- **Python:** PEP 8, `snake_case`, 4-space indent, line length 110
- **JS:** vanilla JS, `camelCase`, no framework
- **CSS:** kebab-case class names, custom properties for tokens
- **Tests:** pytest, `test_*.py` naming, AAA pattern, mock LLM calls
- **API response format:** `{"success": bool, "data": ..., "error": ...}`
- **Dashboard API:** `/api/` routes in `dashboard_server.py`, JSON responses
- **Files:** < 800 lines per file, < 50 lines per function

## Key Project Rules

- **No hardcoded secrets** — use env vars (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)
- **Dashboard is local-only** — no auth, CORS, CSRF needed for dev tool
- **output/ is generated** — keep out of git commits
- **New code** goes in `gaworld/` package when it's a cross-cutting concern
- **Legacy modules** stay in the flat root layout until explicitly migrated
