# About
This is the backend (including a frontend prototype) of the meerkat tool.

# Quick start
This is a dockerized application, so the simplest way to run it is with Docker.
Install *docker* if you have not already: [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [Mac](https://docs.docker.com/desktop/setup/install/mac-install/), [Linux](https://docs.docker.com/desktop/setup/install/linux/)

1. Clone the repository:
   ```bash
   git clone https://github.com/josh-oo/meerkat-tool.git
   cd meerkat-tool
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
The repository ships **no data and no database schema**. A fresh checkout starts all
containers successfully, but the application itself has nothing to work with until you
provide it:

- **Postgres.** The services expect three databases — `POSTGRES_DB_RESOURCES` (studies and
  reports), `POSTGRES_DB_USERS` (backend users) and `POSTGRES_DB_FRONTEND` (frontend,
  managed by Prisma). Neither the databases nor their tables are created automatically.
  Put your own `.sql`/`.sh` files into [`backend/postgres-init/`](backend/postgres-init/)
  to have them applied on the first start; see the README in that folder. Missing
  databases surface as errors at request time, and `/backend/api/readyz` shows which
  dependency is unhealthy.
- **Frontend schema.** The frontend's tables come from its Prisma migrations
   (`npx prisma migrate deploy` inside `frontend/`); they are not applied on container start.
- **Initialization.** On `docker compose up`, the one-shot `app-init` service runs before
  `logic` starts. It:
  1. Creates the Qdrant collection if it doesn't exist yet (with `EMBEDDING_MODEL_DIM`
     dimensions, cosine distance and the required payload indices). Idempotent: an existing
     collection is left untouched. The layout must stay in sync with
     `backend/tools/scripts/prepare_vectorstore.py`.
  2. Creates the data directories inside `backend/_data/backend/` (logs, PDFs, fulltexts)
     that the bind mount hides, and hands them to the unprivileged user `logic` runs as.
     Keep this list in sync when new `DATABASE_VOLUME` paths are added in `backend/logic/src/`.
  
  The script lives in [`backend/app-init/`](backend/app-init/).

On Linux, Docker creates missing bind-mount folders as `root`, which the unprivileged
Qdrant image cannot write to (`logic-init` already takes care of the logic volume).
Create them upfront if the container fails to start:
```bash
mkdir -p backend/_data/qdrant backend/_data/backend backend/_data/embeddings
sudo chown -R 1000:1000 backend/_data
```

# Configuration
All configuration lives in a single `.env` file in the repository root; every variable is
documented in [`.env.example`](.env.example). The values that must be changed before any
non-local use are `POSTGRES_PASSWORD`, `JWT_SECRET`, `BETTER_AUTH_SECRET` and
`BACKEND_API_KEY`. `OPENAI_API_KEY` is required for the agent and extraction features only.

# Services
The application is divided into multiple services to facilitate hosting it on different
machines later.

## frontend
The Next.js user interface, maintained in the `frontend/` directory of this repository.

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
start and cached in `backend/_data/embeddings/`.

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
This service hosts routines like searching for unindexed reports in meerkat to add them to
the index properly. It is not part of `docker compose up`; the scripts in `backend/tools`
are run on demand and use `BACKEND_API_URL` / `BACKEND_API_KEY` to talk to the logic service.

## qdrant / postgres / redis / docling
Vector store, relational database, task/cache backend and PDF conversion service. They run
from upstream images and need no configuration beyond the variables above.

# Rules for editing this repository
1. If you are working on this repository please create a new branch for every feature / bugfix and use meaningful prefixes.
   For example: `bugfix/embedding-model-data-type` or `feature/new-upload-button`
2. If the bugfix is done you can create a pull request, to merge it back to `main`
3. The `prod` branch is currently empty we will use it later for CI/CD as soon as we are ready for production.

# Local Development
Running the project locally (without docker) requires you to run a local vectorstore:
`docker run -p 6333:6333 -p 6334:6334 -v /backend/_data/qdrant:/qdrant/storage qdrant/qdrant`.
For the storage location (backend/_data/qdrant in this case) an absolute path is required.

# Important
In the sqlite table:  
tblStudy Dateentered and tblReport Dateentered need to be in iso format YYYY-MM-DD HH:MM:SS, use the script database/helper.py.
