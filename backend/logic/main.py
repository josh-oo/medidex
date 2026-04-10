from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import auth, resources, core, agents
from src.api import maintenance
from src_agent import agent

# Initialize FastAPI
app = FastAPI(root_path="/backend/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # <-- allows any browser origin
    allow_credentials=False,  # must be False if allow_origins="*"
    allow_methods=["*"],      # GET, POST, PUT, DELETE, OPTIONS, etc.
    allow_headers=["*"],      # all headers allowed
)

app.include_router(auth.router)
app.include_router(core.router)
app.include_router(resources.router)
app.include_router(maintenance.router)
app.include_router(agent.router) #TODO remove this later
app.include_router(agents.router)