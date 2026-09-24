# Frontend

Vite + React SPA, built to static files and served by nginx (see `Dockerfile`,
`nginx.conf`). Pure client-side: it talks to Keycloak (via `keycloak-js`) and the backend
directly from the browser. There is no server-side rendering and no backend-for-frontend —
this used to be a Next.js app (see `README.md`'s history note); that migration is done, and
nothing here should reintroduce Next.js conventions (file-based routing, route groups,
server components, etc.).

## Routing

All routes are declared explicitly in `src/router.tsx` using `react-router-dom`. Folder
names under `src/routes/` are plain organizational labels, not routing config — renaming or
nesting a folder does nothing on its own; the actual paths and `:param` segments are
whatever `router.tsx` says.

- `src/routes/auth/` — login, register, pending-approval. Rendered outside the authenticated
  shell.
- `src/routes/main/` — everything behind `RootLayout` (`src/routes/main/layout.tsx`):
  dashboard, pdf-upload, projects, review, settings, user-management. Each area's `projectId`
  / `reportId` folders correspond to `:projectId` / `:reportId` route params, not to a
  Next.js dynamic-segment convention.

## Structure

- `src/components/ui/` — shadcn/ui components (`components.json` controls generation) plus
  hand-written composites (`report-view/`, `study-view/`, `upload/`).
- `src/lib/api/` — one module per backend resource area, all going through
  `src/lib/api/apiClient.ts`.
- `src/lib/client/keycloak.ts` — the single `keycloak-js` instance; auth state flows from
  here via `src/hooks/use-auth.ts` and `src/components/auth/*-guard.tsx`.
- `src/context/` — React context providers used across more than one route area (e.g.
  `details-sheet-context.tsx`, shared by both `routes/main/projects` and
  `routes/main/review`, plus some `components/ui/study-view` components).
- `src/globals.css` — the one global stylesheet, imported once from `main.tsx`.
- Build-time env (`VITE_*`) is baked into the static bundle at build time, not read at
  runtime — see the `ARG`/`ENV` pairs in `Dockerfile` and the root `docker-compose.yml`'s
  `frontend.build.args`. Changing one of these requires a rebuild, not just a container
  restart.

## Working here

- Validate changes with `npm run build` (type-checks via `tsc -b` then bundles) and
  `npm run lint` from this directory.
