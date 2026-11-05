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
   - API docs: http://localhost:8002/api/v1/docs
   - Readiness/health of all sub-services: http://localhost:8002/api/v1/readyz
   - Qdrant dashboard: http://localhost:6333/dashboard

# Data and databases
Every deployment starts without data. An admin creates study databases on the **Database management** page, empty
or imported from the export of another deployment.

- **Demo data.** [`deploy/data/seed/synthetic_database.zip`](deploy/data/seed/synthetic_database.zip) is a synthetic
  study database (101 studies, 220 linked reports with their PDFs) to import on the Database management page.
  [`deploy/data/seed/examples/`](deploy/data/seed/examples/) holds new reports to upload into a project of that
  database: a RIS file with some of their PDFs next to it, and the same reports as a bundle with those PDFs inside.
- **Admin account.** Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` to create an approved admin account on startup
  (`ADMIN_NAME` is optional). An existing account with that email is made an admin; its password is not changed.
- **Storage.** Postgres, Qdrant, the embedding model cache and the PDFs of the reports live in
  `deploy/data/runtime/`. The databases and the vector collection are created on the first start. There are no
  migrations: start new versions from a clean deployment and bring data over with an export and import.

# Study databases
A study database is a register of studies of its own (e.g. that of one review group), with a name, a description and
eligibility criteria: what a study needs to belong in it, each about an element of PICO or the study as a whole (the
population) or a part of it (the conditions of the population, the route of the intervention, the design of the study;
the parts are the relations annotated `criterion` in `app/backend/src/config/medidex-study.yaml`). New reports are uploaded into a *project* of one database, numbered as
its updates ("Update 7"); they are matched against and linked to the studies of that database only. A database takes
one open update at a time.

Working on an update:
1. An admin creates the update from the card of the database and assigns curators to it. The new reports come as a
   RIS or NBIB file, or as a bundle that brings their PDFs along (`<name>.medidex-update.zip`, laid out like an export:
   `update.json` with the reports and `pdfs/`). Medidex searches the PDFs a bundle does not bring, as for a RIS file.
   A bundle is uploaded in parts with tus, like an import (see below). The format of a bundle is specified in
   [`docs/update-bundle.md`](docs/update-bundle.md).
2. Each curator links the reports to their studies (or creates new studies) and commits the reports when done. Curators
   work independently and do not see each other's links.
3. Once everyone has committed a report, the admin reviews it on the review page and merges it into the database (or
   deletes it). Merged reports and the studies created for them become visible to everyone.

**Export and import.** The download button on the card of a database exports it as `<name>.medidex.zip` (the studies with their
reports and PDFs), which another deployment imports as a new database. An import is all or nothing: a file with errors
is rejected with what is wrong. Imported reports are indexed for matching in the background; until then their studies
are found by the search but not yet suggested for new reports. The file is uploaded in parts of 64 MB with the tus protocol,
so a proxy that limits the size of a request (a Cloudflare tunnel to 100 MB) does not stop large archives, and an
upload that broke off goes on where it stopped when the same file is imported again. The backend puts the parts
together in its temporary directory (`TMPDIR`), which needs room for the whole archive.

The REST API is documented at http://localhost:8002/api/v1/docs.

# Configuration
All configuration lives in a single `.env` file in the repository root; every variable is
documented in [`.env.example`](.env.example). What a study consists of (its fields, tag categories and the structure of
its arms and comparisons) is defined in [`app/backend/src/config/medidex-study.yaml`](app/backend/src/config/medidex-study.yaml).

# Services
The application is divided into multiple services to facilitate hosting it on different
machines later.

## frontend
The Vite + React user interface, in `app/frontend/`.
The original frontend code can be found in the [MaxiMittel/medidex repository](https://github.com/MaxiMittel/medidex).

## logic
The REST API (FastAPI, `app/backend/`) that the frontend calls. On startup the one-shot `app-init` service prepares
Qdrant, the data directories and Keycloak first ([`ops/app-init/init.sh`](ops/app-init/init.sh)); `logic` then creates
missing tables and indexes new reports and tags for matching in the background. It needs outbound internet access to
public APIs: OpenAlex (fulltext PDFs and references), the trial registers (registry records), and PubMed, Europe PMC
and ClinicalTrials.gov (the external records shown next to the studies of a report).

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

The container only runs with the `local-embedding` compose profile (`COMPOSE_PROFILES` in
`.env`). Any hosted, OpenAI-compatible embedding API can replace it: leave the profile out and
set `EMBEDDING_MODEL_BASE_URL`, `EMBEDDING_MODEL_API_KEY`, `EMBEDDING_MODEL_ID` (the model name the
API expects, e.g. `openai/text-embedding-3-small` on OpenRouter), its `EMBEDDING_MODEL_DIM`, a fresh
`VECTORSTORE_COLLECTION_NAME` and an empty `EMBEDDING_MODEL_HEALTH_URL` (a hosted API is not probed
by `/readyz`). `.env.example` has a commented example.

Each text is embedded in a request of its own; `EMBEDDING_MAX_CONCURRENCY` (default 4) is how many
run at once. Keep it low for the local container; a hosted API takes far more (e.g. 32), which makes
indexing an imported database that much faster. If indexing fails (e.g. a wrong API key), the
database shows why and the reason is in the backend log; it is tried again on the next start.

## qdrant / postgres / redis
Vector store, relational database and task/cache backend. They run
from upstream images and need no configuration beyond the variables above.

