"""The REST API head: builds a self-contained FastAPI app from this package's
own routers. Has no knowledge of mcp_server - see app/backend/main.py for how
this app and the MCP head get combined into one deployable process.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, resources, core, agents, projects, admin, maintenance
from .genai_evaluation import agent as agent_service


def create_app() -> FastAPI:
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
    app.include_router(agent_service.router)  # TODO remove this later
    app.include_router(agents.router)

    return app
