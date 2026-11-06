# DataPilot architecture

## Objective

DataPilot accepts CSV/XLSX datasets, executes verified analysis through a
controlled Python tool registry, and presents evidence-based answers and
visualizations through a React client.

The architecture is deliberately split into phases. Phase 1 defines
boundaries; it does not implement runtime behavior.

## System boundaries

```text
React/Vite client
        |
        | HTTPS/JSON, multipart upload, session-scoped resources
        v
FastAPI API
  |-- request validation and authorization boundary
  |-- dataset/session service
  |-- analysis workflow service
  |
  +--> controlled analytical tools (Pandas, NumPy, SciPy)
  +--> CrewAI orchestration
  |      |--> Data Profiler
  |      |--> Statistical Analyst
  |      |--> Visualization Analyst
  |      `--> Insight Analyst
  |
  +--> file storage (dataset bytes; outside PostgreSQL)
  `--> PostgreSQL (metadata, sessions, messages, execution records)
```

## Planned directory responsibilities

- `backend/app/api`: versioned HTTP routes, dependency injection, and error
  translation.
- `backend/app/schemas`: Pydantic contracts shared by API and workflow layers.
- `backend/app/core`: settings loaded from environment variables, logging, and
  security-related cross-cutting policies.
- `backend/app/db`: SQLAlchemy models/session management and Alembic revisions.
- `backend/app/ingestion`: file type/size/shape validation, safe storage, and
  dataset context creation, metadata extraction, and previews.
- `backend/app/analytics`: registered, deterministic analytical functions and
  their input/output schemas. This layer never accepts arbitrary generated
  Python.
- `backend/app/agents`: CrewAI agent and task definitions, kept separate from
  analytical execution.
- `backend/app/workflows`: query understanding, agent selection, tool argument
  validation, execution, result validation, and response assembly.
- `backend/tests`: unit, integration, workflow, and numerical correctness
  tests.
- `frontend/src/services`: typed API client and upload/chat transport.

## Dataset ownership and authorization

Every dataset has an explicit owner identity (a user identifier in
authenticated deployments) and may optionally be associated with an analysis
session for context. A session identifier is a correlation/context key only;
it is never an authorization credential.

Every dataset, session, message, execution, and file-storage operation must
perform an ownership/authorization check against the authenticated principal
before reading or mutating data. Resource lookups must combine the resource
identifier with the owner predicate and must not reveal whether another
owner's identifier exists. Storage keys are generated server-side and are
never accepted as client authorization input.

Authentication is deferred during local single-user development only. In that
mode, a configured development principal is injected by the backend and all
authorization checks still run against that principal. This mode must be
explicitly enabled through environment configuration, must not be used in
production, and does not make session IDs trusted.

## Dataset ingestion and profiling

The upload API accepts only CSV and XLSX multipart files. The backend streams
the upload to a generated temporary file while enforcing `MAX_UPLOAD_SIZE_BYTES`,
then validates both the extension and content signature/parser result. XLSX
files must be ZIP-based Office documents; CSV structure is checked before
Pandas parsing. User filenames are retained only as display metadata and never
used as filesystem paths.

Stored files use UUID-generated names under the configured backend-only
`STORAGE_DIR`. PostgreSQL stores the relative storage key and metadata, not raw
dataset contents. The service profiles a validated file deterministically with
Pandas, recording dimensions, column data types, missing counts, duplicate-row
count, and memory usage. `MAX_DATASET_ROWS`, `MAX_DATASET_COLUMNS`, and
`MAX_PREVIEW_ROWS` provide practical resource limits. Preview reads are
paginated at the API boundary, although profiling currently loads the validated
dataset into a Pandas DataFrame.

## CrewAI coordination

The workflow service will first classify the user question and build a small
execution plan. It will select only the required agents:

1. **Data Profiler** supplies structure, quality, and metadata context.
2. **Statistical Analyst** requests registered statistical tools and interprets
   their verified outputs.
3. **Visualization Analyst** chooses a chart specification when a visual is
   requested or materially improves the answer.
4. **Insight Analyst** turns validated results into concise, evidence-linked
   findings and recommendations.

CrewAI agents may request only named operations from the analytical registry.
They do not invoke analytical Python directly. Every request goes through the
backend workflow, where the operation name is allow-listed, arguments are
validated with Pydantic, the dataset ownership check is repeated, and the
operation runs against the isolated dataset context. Execution is recorded
with its validated inputs, status, duration, and structured result. Agents
receive no unrestricted Python, shell, filesystem, or database access.

Agent selection is a lightweight planning step based on the question and
available dataset metadata. The workflow selects the smallest useful set:
for example, a summary question can use the Statistical Analyst without
starting Visualization or Insight tasks, while a chart request adds the
Visualization Analyst. Results are reused as task context, preventing
duplicate profiling and unnecessary LLM calls. A deterministic tool can be
used directly when no agent interpretation is required.

## Analytical tool boundary

The registry will expose named functions such as `get_dataset_profile`,
`get_summary_statistics`, `get_missing_values`, `detect_outliers`,
`group_by_analysis`, `get_correlation`, `get_time_trends`, `filter_dataset`,
`compare_categories`, and `generate_chart`.

Every tool will define:

- a typed input contract and column/type validation;
- a typed structured output;
- missing-value and empty-result behavior;
- explicit errors for invalid arguments;
- resource/time limits appropriate to the operation.

No agent will be given unrestricted Python, shell, filesystem, or database
access.

Phase 4 implements this boundary without agents: the registry maps stable tool
names to Pydantic input models and fixed Python callables. The analytical
service loads only an already-authorized dataset, dispatches through the
registry, bounds result payloads stored in `analytical_executions`, and records
status and duration. Unknown names, invalid columns, operators, aggregations,
chart types, and limits fail with controlled validation errors.

The current API exposes `GET /api/v1/analytics/tools` for registry discovery
and `POST /api/v1/datasets/{dataset_id}/analytics` for execution. The latter
reuses the ownership dependency and accepts only a tool name plus a validated
parameters object; clients never provide filesystem paths or executable code.

## Frontend-backend communication

- REST/JSON API under `/api/v1` for datasets, sessions, analysis requests,
  results, and chart specifications.
- `multipart/form-data` for CSV/XLSX uploads.
- A session identifier groups datasets, messages, and executions, but never
  authorizes access; ownership checks apply to every resource request.
- The frontend renders server-provided structured results and Plotly-compatible
  chart specifications; it does not calculate authoritative metrics.
- Long-running analysis uses a job resource with polling initially. A
  streaming transport can be added later without changing analytical
  contracts.
- API errors use a consistent structured shape with a human-readable message,
  machine-readable code, and request correlation identifier.

## Background analysis lifecycle

The initial design uses an application-managed job record and a simple
background execution mechanism; it does not introduce a broker, worker
cluster, or other infrastructure prematurely.

1. **Create:** an authorized client submits a question and dataset/session
   context. The API validates the request, creates a job with `queued` status,
   and returns its identifier.
2. **Execute:** the application claims the queued job, records `started_at`,
   runs planning, agent selection, validated tool calls, and result
   validation, then records execution references.
3. **Track:** the job transitions through `queued`, `running`, `succeeded`,
   `failed`, or `cancelled`; timestamps, error code/details, and a correlation
   identifier are retained. State transitions are explicit and idempotent.
4. **Retrieve:** an authorized client polls the job resource. Successful jobs
   expose structured answer/result references and chart specifications; failed
   jobs expose a safe structured error without internal secrets.

The job's dataset/session ownership is checked at creation, execution, and
retrieval. A later deployment can replace the execution mechanism behind the
same job contract if measured workload requires it.

## Initial database entities

Database work begins in Phase 2. The initial model boundaries are:

- `users`: optional identity and ownership boundary.
- `datasets`: owner/session association, original filename, storage reference,
  size, format, row/column counts, and lifecycle status.
- `dataset_metadata`: columns, inferred types, profile summary, and schema
  version for a dataset.
- `analysis_sessions`: dataset context, status, timestamps, and workflow
  metadata.
- `conversation_messages`: user prompts and assistant responses associated
  with an analysis session.
- `analytical_executions`: tool/agent name, validated arguments, status,
  structured result reference, error details, and timing.

Large dataset bytes remain in controlled file storage; PostgreSQL stores
metadata and references.

The `analysis_jobs` entity is also planned for background lifecycle state,
status timestamps, correlation ID, and result/error references.

## Baseline evaluation strategy

The evaluation suite will use small versioned datasets with known expected
answers and labeled natural-language questions:

- **Analytical numerical correctness:** compare tool outputs to independently
  calculated expected values, including missing values, duplicates, grouping,
  correlations, and outliers within defined tolerances.
- **Agent tool-selection accuracy:** measure whether the minimal required
  registered operations and agents are selected for labeled questions, and
  whether invalid operations are rejected.
- **Single-agent versus multi-agent comparison:** run equivalent questions
  through the smallest single-agent plan and the required multi-agent plan,
  comparing correctness, unnecessary calls, completeness, and response quality.
- **Execution latency:** record end-to-end and per-tool/per-agent durations,
  reported as median and tail percentiles on the evaluation environment.
- **Workflow success rate:** measure completed valid jobs versus failed,
  rejected, or invalid-result jobs across repeated evaluation runs.

These are baseline measurements, not claims of improvement. Results will be
added with the relevant tests in the later testing/evaluation phase.

## Risks and dependencies

- **LLM nondeterminism:** constrain outputs with schemas, validate every tool
  request, and keep calculations deterministic.
- **Untrusted uploads:** enforce extension/content checks, size and shape
  limits, safe generated storage names, and isolated dataset contexts.
- **Resource exhaustion:** cap rows/columns, bound expensive operations, and
  add execution timeouts before enabling broad uploads.
- **Data leakage:** pass only relevant metadata/results to the LLM and enforce
  ownership checks on every dataset/session query; session IDs alone never
  authorize access.
- **Provider coupling:** use an internal LLM adapter so Gemini can be replaced.
- **CrewAI evolution:** pin compatible versions and keep agent definitions
  behind the workflow boundary.
- **Database/file consistency:** model explicit lifecycle states and clean up
  orphaned files through a later maintenance process.
- **Chart safety:** return validated chart specifications rather than arbitrary
  HTML or executable JavaScript.

## Phase gates

Phase 2 may begin only after approval. It will add FastAPI foundation and
database setup, with migrations and API smoke tests. Each later phase should
preserve the boundaries above and add focused tests before expanding scope.
