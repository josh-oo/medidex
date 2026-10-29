"""The REST API head: builds a self-contained FastAPI app from this package's
own routers.
"""

import os
from contextlib import asynccontextmanager
from typing import Iterable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.background.startup import Startup

from . import auth, resources, core, projects, admin, maintenance, databases


def create_app(extra_routers: Iterable[APIRouter] = ()) -> FastAPI:
    """Build the OSS REST API app, plus any additional routers a downstream
    deployable wants mounted on top. On start it makes the schema of the
    resources database from the models (also those of the downstream build), see
    src/background/startup.py. Swapping or extending individual
    dependencies - auth checks, get_context - is done separately, via
    FastAPI's own `app.dependency_overrides` on the returned app; that's
    already the idiomatic FastAPI extension point, so it isn't duplicated
    here.
    """
    startup = Startup.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await startup.start()
        try:
            yield
        finally:
            await startup.stop()

    app = FastAPI(
        lifespan=lifespan,
        root_path="/api/v1",
        # Lets the /docs "Authorize" button drive Keycloak's authorization-code +
        # PKCE flow (see auth.py) without the client id being pasted in by hand.
        swagger_ui_init_oauth={
            "clientId": os.getenv("KEYCLOAK_CLIENT_ID", "medidex-frontend"),
            "usePkceWithAuthorizationCodeGrant": True,
        },
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # <-- allows any browser origin
        allow_credentials=False,  # must be False if allow_origins="*"
        allow_methods=["*"],      # GET, POST, PUT, DELETE, OPTIONS, etc.
        allow_headers=["*"],      # all headers allowed
    )

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(projects.router)
    app.include_router(databases.router)
    app.include_router(core.router)
    app.include_router(resources.router)
    app.include_router(maintenance.router)

    for extra_router in extra_routers:
        app.include_router(extra_router)

    return app
