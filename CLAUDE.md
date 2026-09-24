# Medidex

Report-trial linkage ("studification"): given a newly entered report, surface candidate
parent studies so a researcher can link them. Full product description in [README.md](README.md).

## Layout

- `app/` — the two services that make up the product.
  - `app/backend/` — FastAPI service (container name `logic`), built from `app/backend/Dockerfile`.
    - `src/` — the actual application: `src/api/` (routers), `src/services/`, `src/database/`
      (SQLModel models + repositories), `src/utils/`.
    - `agent/` — LangGraph report-evaluation agent, mounted into the same FastAPI app via
      `agent.router` in `main.py`. Historically a separate demo service (see its own
      module docstrings); now just another router package, not a separate deployable.
    - `main.py` — FastAPI entrypoint; wires up `src/api/*` and `agent/agent.py` routers.
  - `app/frontend/` — Vite + React SPA (container name `frontend`), served by nginx in
    production. Talks to Keycloak and the backend directly from the browser — there is no
    server-side rendering or backend-for-frontend layer.
    - `src/routes/auth/` — unauthenticated pages (login, register, pending-approval).
    - `src/routes/main/` — authenticated app shell and pages (`layout.tsx` = the shared
      shell), routed by `src/router.tsx`. Folder names here are plain labels, not
      framework convention — actual route paths and dynamic params (`:projectId`, etc.)
      are declared explicitly in `router.tsx` via react-router.
- `ops/` — supporting tooling, not part of the running product.
  - `ops/app-init/` — one-shot container that runs once on `docker compose up` before
    `logic` starts: creates the Qdrant collection, prepares the backend's data volume,
    seeds/embeds demo data. See `ops/app-init/init.sh`.
    `postgres-init.sh` in the same folder is separate: it's mounted as the `postgres`
    container's own init script, run by the Postgres image itself on first start.
  - `ops/tools/` — offline scripts (dataset prep, vectorstore prep, backend evaluation),
    run manually against a running stack; not started by `docker compose up`.
- `deploy/` — infrastructure config, not application code.
  - `deploy/keycloak/` — realm definition (`realm-medidex.json`) and custom login theme,
    mounted into the `keycloak` container.
  - `deploy/data/seed/` — versioned demo dataset loaded by `app-init` on first start.
  - `deploy/data/runtime/` — gitignored, Docker-managed runtime state (Qdrant storage,
    embedding cache, backend data volume, Postgres backups). Never edit by hand.
- `docker-compose.yml` / `.env(.example)` — the orchestration entrypoint, at the repo root
  since `docker compose up` is meant to run from there. Both `app/backend` and
  `ops/app-init` build with the **repo root** as Docker build context (so `app/backend/Dockerfile`
  can `COPY ops/app-init/data/placeholder.pdf`); `app/frontend` builds with its own directory
  as context since it's self-contained.

## Working here

- This is a service boundary, not a monolith: `app/backend` and `app/frontend` never import
  from each other. They only talk over HTTP, matching the env vars in `.env.example`
  (`VITE_BACKEND_API_URL` client-side, `KEYCLOAK_*` on both sides).
- Auth is Keycloak-only. The frontend never talks OIDC directly — `keycloak-js` runs entirely
  in the browser; the backend validates the resulting bearer tokens.
- Changing `DATABASE_VOLUME` paths in `app/backend/src/` means updating the directory
  bootstrap list in `ops/app-init/init.sh` too (called out in its comments).
- No CI is configured in this repo yet — validate backend changes by running the FastAPI
  service, frontend changes with `npm run build` / `npm run lint` in `app/frontend`.
