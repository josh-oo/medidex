# About
Medidex is an application designed to streamline report-trial linkage (also known as publication-trial linkage or "studification").
Maintaining study-based registers—databases of relevant clinical trials for specific medical domains (e.g., lung cancer, mental health, ...)—requires continuously screening new publications and manually linking them to their parent studies.
Medidex facilitates the linking phase of this workflow. For every newly entered report, the tool automatically provides a targeted candidate list of relevant parent studies, reducing manual effort and enabling junior researchers to achieve the same high-quality linking as senior experts.

# Quick start
This is a dockerized application, so the simplest way to run it is with Docker.
Install *docker* if you have not already: [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [Mac](https://docs.docker.com/desktop/setup/install/mac-install/), [Linux](https://docs.docker.com/desktop/setup/install/linux/)

1. Clone the repository:
   ```bash
   git clone https://github.com/josh-oo/medidex.git
   cd medidex
   ```
2. Create your environment file and adjust the values marked `CHANGE ME`:
   ```bash
   cp .env.example .env
   ```
   Every variable has a working local default, so the stack also starts unedited — but do
   not expose it to anyone else with the example secrets in place.
3. Start everything:
   ```bash
   docker compose up
   ```
   The first run builds the images and downloads the embedding model, so it takes a while.
4. Once the containers are up:
   - Frontend: http://localhost:3000
   - API docs: http://localhost:8002/backend/api/docs
   - Readiness/health of all sub-services: http://localhost:8002/backend/api/readyz
   - Qdrant dashboard: http://localhost:6333/dashboard

# Data and databases
The repository ships a deterministic synthetic study/report dataset for local deployments.
On first startup, `app-init` creates the resource tables used by the study/report adapters
when absent and loads 100 studies with an uneven set of 210 linked reports. Existing resource data is left
unchanged. Production deployments can omit the `deploy/data/seed/` mount if they provision their own
resource schema and data:

- **Postgres.** The services expect three databases — `POSTGRES_DB_RESOURCES` (studies and
    reports), `POSTGRES_DB_LANGGRAPH` (agent checkpoints) and `POSTGRES_DB_KEYCLOAK` (Keycloak).
    The databases are created automatically on the first start; see
    [`ops/app-init/postgres-init.sh`](ops/app-init/postgres-init.sh) for details. The demo resource seed
    lives in [`deploy/data/seed/`](deploy/data/seed/) and is loaded by `app-init` only when the resource
    database is empty. Docker-mounted runtime state lives in `deploy/data/runtime/`.
- **Admin account.** Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` to create an
    approved admin account automatically on frontend startup. The seed is idempotent;
    an existing account with that email is promoted to admin without changing its
    password. `ADMIN_NAME` is optional and defaults to `Administrator` (used as the
    first name; if it has no space, the last name defaults to `User`).
- **Initialization.** On `docker compose up`, the one-shot `app-init` service prepares
    PostgreSQL, Qdrant, the logic data volume, and the seeded vectors before `logic` starts.
    The initialization chain:
  1. Creates the Qdrant collection if it doesn't exist yet (with `EMBEDDING_MODEL_DIM`
     dimensions, cosine distance and the required payload indices). Idempotent: an existing
     collection is left untouched. The layout must stay in sync with
    `ops/app-init/init.sh`.
   2. Creates the data directories inside `deploy/data/runtime/backend/` (logs, PDFs, fulltexts)
     that the bind mount hides, and hands them to the unprivileged user `logic` runs as.
     Keep this list in sync when new `DATABASE_VOLUME` paths are added in `app/backend/src/`.
   3. Embeds all reports and intervention, condition, and outcome tags with the
        configured embedding service, then upserts them into Qdrant using `curl`, `jq`, and
        `psql`. It writes an idempotence marker under
       `deploy/data/runtime/backend/resources/` and skips re-embedding on later starts unless that
        marker is removed.
  
  The script lives in [`ops/app-init/`](ops/app-init/).

- **Testing with Dummy Data.** You can use the files located under `deploy/data/seed/examples/` as dummy data to test the system (provided it was already initialized with the default seed data).

# Configuration
All configuration lives in a single `.env` file in the repository root; every variable is
documented in [`.env.example`](.env.example). The values that must be changed before any
non-local use are `POSTGRES_PASSWORD`, `JWT_SECRET`, `BETTER_AUTH_SECRET` and
`BACKEND_API_KEY`. `OPENAI_API_KEY` is required for the agent and extraction features only.

# Services
The application is divided into multiple services to facilitate hosting it on different
machines later.

## frontend
The Vite + React user interface, maintained in the `app/frontend/` directory of this repository.
The original frontend code can be found in the [MaxiMittel/medidex repository](https://github.com/MaxiMittel/medidex).

## logic
This service manages the incoming requests from the frontend and calls the appropriate
sub-services in the backend.

## embedding
This service transforms plain text into vector embeddings. It runs HuggingFace
[text-embeddings-inference](https://github.com/huggingface/text-embeddings-inference) and
exposes an OpenAI-compatible API, which the logic service reaches through
`EMBEDDING_MODEL_BASE_URL`. The model is selected with `EMBEDDING_MODEL_ID` and
`EMBEDDING_MODEL_REVISION` and defaults to [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
(1024 dimensions, 8192 token context); it is downloaded from the HuggingFace Hub on first
start and cached in `deploy/data/runtime/embeddings/`.

`EMBEDDING_MAX_BATCH_TOKENS` (default 2048) caps the tokens per batch and is the main
driver of this container's memory use: on a stock Docker Desktop VM (~8 GB) bge-m3 is
killed during warm-up at 4096. Inputs longer than the cap are truncated, so raise it
together with the VM's memory if you embed long full texts.

Pointing it at a different model means
re-indexing: update `EMBEDDING_MODEL_DIM` and use a fresh `VECTORSTORE_COLLECTION_NAME`,
because vectors from different models are not comparable. Set `HF_TOKEN` only if you point it at a gated or
private model. Currently this service runs on CPU; depending on the workload it might make
sense to move it to a GPU machine later.

## tools
This service hosts routines like searching for unindexed reports in the backend to add them to
the index properly. It is not part of `docker compose up`; the scripts in `ops/tools`
are run on demand and use `BACKEND_API_URL` / `BACKEND_API_KEY` to talk to the logic service.

## qdrant / postgres / redis / docling
Vector store, relational database, task/cache backend and PDF conversion service. They run
from upstream images and need no configuration beyond the variables above.

