# DataPilot

DataPilot is an AI-powered, multi-agent data analysis platform. It combines
controlled Pandas/NumPy analytical tools with CrewAI orchestration and a
React/Vite user interface. The LLM coordinates analysis and explains verified
results; it does not perform numerical calculations.

## Phase 1 status

Phase 1 establishes the architecture and project scaffold only. It does not
implement FastAPI endpoints, database access, dataset ingestion, analytical
tools, CrewAI agents, LLM integration, visualization generation, or frontend
features. Those are intentionally deferred to later phases and require approval
before work begins.

Created in this phase:

- Architecture and workflow documentation in [`docs/architecture.md`](docs/architecture.md)
- Backend Python package and tool configuration
- Frontend Vite/TypeScript package configuration
- Environment-variable and ignore-file templates
- Initial test and source directory boundaries

## Planned repository layout

```text
backend/
  app/
    api/                 HTTP routes and dependency wiring
    agents/              CrewAI agents and task definitions
    analytics/           Controlled analytical tool registry
    core/                Settings, logging, and cross-cutting concerns
    db/                  SQLAlchemy models, sessions, and migrations
    ingestion/           Upload validation and dataset storage
    schemas/             Pydantic request/response models
    workflows/           Query planning and orchestration
  tests/
frontend/
  src/
    components/
    pages/
    services/
    types/
  tsconfig.json
docs/
```

## Local setup

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` for local configuration. The backend will load
local environment files through `python-dotenv`/Pydantic settings; environment
variables supplied by the deployment environment remain authoritative. Never
commit `.env` or credentials. Database and application startup instructions
will be added in Phase 2.

## Technology boundaries

- FastAPI is the HTTP boundary.
- Uvicorn is the development/ASGI server.
- Pydantic validates external input and structured workflow results.
- SQLAlchemy/Alembic own persistence from Phase 2 onward.
- CrewAI is the orchestration framework; LangChain and LangGraph are not the
  primary orchestration layer.
- Analytical execution is limited to registered Python functions. LLM output
  cannot execute arbitrary Python.
- Gemini is a replaceable provider behind an LLM adapter, using the
  `google-genai` SDK.
- Frontend application code is TypeScript/TSX; Plotly charts use
  `react-plotly.js`.
