# DataPilot

DataPilot is an AI-powered, multi-agent data analysis platform. It combines
controlled Pandas/NumPy analytical tools with CrewAI orchestration and a
React/Vite user interface. The LLM coordinates analysis and explains verified
results; it does not perform numerical calculations.

## Phase 1 status

Phase 3 implements the backend dataset ingestion and deterministic profiling
foundation. Dataset upload, storage, metadata, profiling, preview, listing,
ownership checks, and deletion are available through the FastAPI API. Analytical
tools, CrewAI agents, LLM integration, visualization generation, and frontend
features remain deferred.

Created in this phase:

- Architecture and workflow documentation in [`docs/architecture.md`](docs/architecture.md)
- Backend Python package and tool configuration
- Frontend Vite/TypeScript package configuration
- Environment-variable and ignore-file templates
- Initial test and source directory boundaries
- Dataset ingestion, profiling, and ownership-aware API endpoints

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
- Uploaded dataset bytes are stored under the configured backend-only
  `STORAGE_DIR`, never in PostgreSQL or the publicly served frontend.
- Profiling is deterministic and performed by Pandas; configured row, column,
  file-size, and preview limits protect memory and request resources.
