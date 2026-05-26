from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import auth, resources, core, agents, projects
from src.api import maintenance
from src_agent import agent
from src.database.sessions import init_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs ON STARTUP
    # It creates tables if they do not exist
    await init_db()
    yield

# Initialize FastAPI
app = FastAPI(root_path="/backend/api", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # <-- allows any browser origin
    allow_credentials=False,  # must be False if allow_origins="*"
    allow_methods=["*"],      # GET, POST, PUT, DELETE, OPTIONS, etc.
    allow_headers=["*"],      # all headers allowed
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(core.router)
app.include_router(resources.router)
app.include_router(maintenance.router)
app.include_router(agent.router) #TODO remove this later
app.include_router(agents.router)