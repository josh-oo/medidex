"""The REST API head: builds a self-contained FastAPI app from this package's
own routers.
"""

import os
from typing import Iterable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, resources, core, projects, admin, maintenance


def create_app(extra_routers: Iterable[APIRouter] = ()) -> FastAPI:
    """Build the OSS REST API app, plus any additional routers a downstream
    deployable wants mounted on top (e.g. an enterprise build adding its own
    endpoints without forking this package). Swapping or extending individual
    dependencies - auth checks, get_context - is done separately, via
    FastAPI's own `app.dependency_overrides` on the returned app; that's
    already the idiomatic FastAPI extension point, so it isn't duplicated
    here.
    """
    app = FastAPI(
        root_path="/backend/api",
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
    app.include_router(core.router)
    app.include_router(resources.router)
    app.include_router(maintenance.router)

    for extra_router in extra_routers:
        app.include_router(extra_router)

    return app
