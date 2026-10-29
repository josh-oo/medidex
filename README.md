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
The repository ships a deterministic synthetic study/report dataset for local deployments,
[`deploy/data/seed/synthetic_database.zip`](deploy/data/seed/synthetic_database.zip) (101 studies with an uneven
set of 220 linked reports and their PDFs). On startup the backend only creates the tables of the resources database
when they are absent; it loads no data. Every deployment starts without a study database, and an admin creates one
or imports one on the Database management page, e.g. the demo database:

- **Postgres.** The services expect three databases — `POSTGRES_DB_RESOURCES` (studies and
    reports), `POSTGRES_DB_LANGGRAPH` (agent checkpoints) and `POSTGRES_DB_KEYCLOAK` (Keycloak).
    The databases are created automatically on the first start; see
    [`ops/app-init/postgres-init.sh`](ops/app-init/postgres-init.sh) for details. Docker-mounted runtime
    state lives in `deploy/data/runtime/`.
- **Resource schema.** The models are the schema: on every start the backend creates the tables of
    `app/backend/src/database/models.py` (and of the models of a downstream build) that do not exist yet
    (`src/database/schema.py`). There are no migrations; a deployment starts from a clean database, and data from
    elsewhere comes in through the database import.
- **PDFs.** The fulltext PDF of a report is the file `resources/report_pdfs/<report id>.pdf` of the data volume
    (`src/utils/pdfs.py`). Whether a report has one is read from that folder, not stored; a report without one can be
    marked "Not Available" (`report.no_pdf`), and then counts as having one.
- **Study databases.** The resource database holds any number of *study databases*
    (`study_database`: a name, a description and eligibility criteria), e.g. the registers of
    different review groups, numbered by integer ids. Every study and every project belongs to one. There is
    no default database: each deployment brings its own, which admins create on the Database management page,
    empty or imported from the export of another one (see [Study databases](#study-databases)); the demo
    database is one such import. A project's reports are only matched against, linked to and turn into
    studies of its own database, and study short names are unique within a database.
- **Admin account.** Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` to create an
    approved admin account automatically on frontend startup. The seed is idempotent;
    an existing account with that email is promoted to admin without changing its
    password. `ADMIN_NAME` is optional and defaults to `Administrator` (used as the
    first name; if it has no space, the last name defaults to `User`).
- **Testing with dummy data.** [`deploy/data/seed/examples/`](deploy/data/seed/examples/) holds new reports (a RIS
    file and some of their PDFs) to upload into a project of the imported demo database.
- **Initialization.** On `docker compose up`, the one-shot `app-init` service prepares Qdrant, the
    logic data volume and Keycloak before `logic` starts; it never touches postgres. Its chain
    ([`ops/app-init/init.sh`](ops/app-init/init.sh)):
  1. Creates the Qdrant collection if it doesn't exist yet (with `EMBEDDING_MODEL_DIM`
     dimensions, cosine distance and the required payload indices). Idempotent: an existing
     collection is left untouched.
  2. Creates the data directories inside `deploy/data/runtime/backend/` (logs, PDFs of the reports, fulltexts)
     that the bind mount hides and hands them to the unprivileged user `logic` runs as. Keep this list in
     sync when new `DATABASE_VOLUME` paths are added in `app/backend/src/`.
  3. Grants the Keycloak service account its roles and creates the optional admin account.

  Then `logic` itself, on every start ([`src/background/startup.py`](app/backend/src/background/startup.py)),
  before it serves: creates the schema (see "Resource schema"). In the background it then syncs the vectorstore:
  every report and intervention, condition and outcome tag without a point is embedded (in batches) and
  added, points of deleted rows are removed (`MaintenanceService.sync_vectorstore`). Until that is done,
  new reports are matched against fewer studies; it continues on the next start if interrupted.

# Study databases
A study database is a collection of studies of its own, with a name, an optional description and eligibility
criteria (required free text: which studies belong in it). The Database management page shows one tab per database
with its projects; its details dialog shows the eligibility criteria, and admins edit name, description and criteria
there and create new projects into the shown database. The REST API:

| Endpoint | Who | What |
| --- | --- | --- |
| `GET /databases` | any user | the databases with their number of studies and reports |
| `POST /databases` | admin | a new, empty database (`name`, `description`, `eligibilityCriteria`) |
| `POST /databases/import` | admin | a new database from an exported one with its PDFs (multipart: `file` (.zip or .json), `name`, `description`, `eligibilityCriteria`) |
| `PATCH /databases/{id}` | admin | rename a database or change its description or eligibility criteria |
| `GET /databases/{id}/export` | admin | the database as a zip archive (`database.json` and the PDFs of its reports) |
| `POST /projects` | admin | requires the `databaseId` of the project |
| `PUT /studies?databaseId=…` | any user | a study without a report, in the given database |
| `GET /studies?q=…&databases=…` | any user | the study search, in the given databases (all without) |
| `GET /{category}?databases=…`, `GET /countries?databases=…` | any user | the tags used by the studies of the given databases (the whole vocabulary without) |

**Exchange format.** An export is a zip archive, `<name>.medidex.zip`, that an import reads back unchanged
(`app/backend/src/utils/archive.py`): `database.json` (`DatabaseExport` in `app/backend/src/utils/dto.py`) and
the PDFs of its reports under `pdfs/`, each named by the `pdf` of its report. An import also takes the same
layout unpacked into a directory or a `database.json` alone, without PDFs. Each study has its
fields of the study ontology, its graph with the tags by name (see "The study ontology"), the names of its tags
per category kept in a table, and its reports:

```json
{
  "format": "medidex-database",
  "version": 1,
  "name": "Paediatric asthma trials",
  "description": "…",
  "eligibilityCriteria": "…",
  "studies": [
    {
      "shortName": "ASTHMA-KIDS-01",
      "status": "Closed",
      "trialId": "ISRCTN12345678",
      "numberParticipants": null,
      "duration": null,
      "countries": ["Germany"],
      "graph": { "nodes": [{ "id": "arm1", "kind": "arm", "value": null }], "edges": [] },
      "tags": { "interventions": ["Montelukast"], "conditions": ["Asthma"] },
      "createdAt": "2021-03-01 00:00:00",
      "reports": [{ "title": "…", "year": 2021, "authors": ["A. Author"], "abstract": "…", "doi": "10.…", "pdf": "pdfs/17.pdf" }]
    }
  ]
}
```

An import is all or nothing: a file with an unknown study status, a malformed graph, two studies of the same
short name, an unknown tag category or a PDF it names but does not contain is rejected with what is wrong. The
PDFs are stored under the ids the reports get in the importing deployment. Unknown tag names become new tags. A
report listed under several studies (same DOI, or same title and year) is imported once. Imported studies are
visible to every scope, like those of the seed. Their reports are added to the vectorstore in the background, and
until then the studies are found by the search but not yet suggested for new reports.
[`deploy/data/seed/synthetic_database.zip`](deploy/data/seed/synthetic_database.zip), the demo database, is one
to try it with.

# Configuration
All configuration lives in a single `.env` file in the repository root; every variable is
documented in [`.env.example`](.env.example).

# Services
The application is divided into multiple services to facilitate hosting it on different
machines later.

## frontend
The Vite + React user interface, maintained in the `app/frontend/` directory of this repository.
The original frontend code can be found in the [MaxiMittel/medidex repository](https://github.com/MaxiMittel/medidex).

## logic
This service manages the incoming requests from the frontend and calls the appropriate
sub-services in the backend.

### The study ontology
What a study consists of is defined once, as a [LinkML](https://linkml.io) schema:
[`app/backend/src/config/medidex-study.yaml`](app/backend/src/config/medidex-study.yaml). The fields of a study,
its tag categories, the entities and relations of its graph (arms, populations, outcomes and their values), the study
DTOs, `GET /study-schema` and the frontend views are all derived from it (`src/utils/studyconfig.py`); its header
explains how the classes and annotations are read. Graphs stored under the names from before the ontology
(`comparison`, `interventions`, ...) are converted when they are read (`src/utils/graph.py`).

A downstream deployable extends the ontology without editing it: it imports the schema for new classes and slots, and
keeps annotations of its own (e.g. instructions for an extraction) in a separate file keyed by the names of this one.

OWL for reasoners is generated, not kept in git (`linkml` is a development dependency only):

```bash
pip install linkml
gen-owl --no-use-native-uris app/backend/src/config/medidex-study.yaml > medidex-study.owl.ttl
```

`--no-use-native-uris` uses the `slot_uri` of the tag categories, so e.g. the conditions of a study and those of a
population are the same property, `mdx:has_condition`.

## Scopes

Everyone who edits works in a **scope** of their own and does not interact with the others. A scope is the id the
edit is recorded under (`user_id` of the request):

| Scope | Id | Who |
|---|---|---|
| user | the Keycloak user id | a person working in the web UI |
| MediBot | `bot` | the project automation |
| MCP client | `<client name> (mcp)` | an MCP client acting for the project's administrator (downstream builds) |

- **Links.** The link of a report to a study is recorded per scope (`study_report_added.created_by`; in the
  vector store under `temporary.<scope>`), so everyone sees their own links.
- **Studies.** A study created in a scope (`study_added.created_by`) is only visible to that scope - in search,
  candidates, details and for linking - until a reviewer confirms a link to it, from then on it is visible to
  everyone. Studies of the seed data (no `study_added` record) are visible to everyone. Admins (reviewers) see
  every scope's studies (`RequestContext.is_admin`); an MCP client acting for an admin does not.
- **Projects.** A scope needs access to the project: it is assigned to it (`project_assignee`, any string is a
  valid assignee), which is also what shows its progress among the assignees of the project (Curation page). Reviewing the edits of the scopes
  finishes the project.
- **Not scoped.** PDFs and their upload are global: a PDF found for a report is the PDF of the report.

Implemented in `StudyRepository._visible()` and `LinkageService` (a study that is not visible cannot be linked).

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

## qdrant / postgres / redis
Vector store, relational database and task/cache backend. They run
from upstream images and need no configuration beyond the variables above.

