# Backend (`logic` service)

FastAPI service. Built from `Dockerfile` with the **repo root** as Docker build context
(see the root `CLAUDE.md` for why) — don't assume paths inside the Dockerfile are relative
to this directory.

## Structure

- `main.py` — app entrypoint; registers every router from `src/api/` plus `agent/agent.py`.
- `src/api/` — HTTP routers (one module per resource area: `auth`, `admin`, `projects`,
  `core`, `resources`, `maintenance`, `agents`).
- `src/services/` — business logic called by the routers.
- `src/database/` — SQLModel models (`models.py`) and repositories (one per resource,
  under `database/repositories/`).
- `src/utils/` — shared helpers (DTOs, parsers, logging).
- `agent/` — the LangGraph-based report/study evaluation agent. Imported into `main.py` as
  `from agent import agent as agent_service`, then `agent_service.router`. It predates being
  folded into this service (see module docstrings referencing a standalone "AI Demo Server");
  treat it as a normal subpackage now, not a separate deployable.
- `requirements.txt` — single dependency set for the whole image (covers both `src/` and
  `agent/`; there is no separate requirements file for `agent/`).

## Conventions

- Auth: Keycloak bearer tokens, validated per-request; see `src/api/auth.py`. The
  `KEYCLOAK_ADMIN_CLIENT_ID`/`SECRET` service-account credentials (Keycloak Admin REST API
  access) are used from `src/api/admin.py` only — never exposed to the frontend.
- `DATABASE_VOLUME` (mounted at `/data` in the container) is where PDFs, extracted
  fulltexts and logs live. If you add a new subpath under it, update the directory-creation
  list in `ops/app-init/init.sh` — the bind mount hides whatever the image itself creates.
- Vector ids in Qdrant follow a deterministic scheme (`transform_to_uuid()` in
  `src/services/vectorstore.py`); `ops/app-init` relies on that scheme to reconcile Qdrant
  with Postgres on every start, so don't change it without checking that script.
