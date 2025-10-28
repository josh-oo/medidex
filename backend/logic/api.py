from fastapi import FastAPI, Depends

from src import auth, logic, resources

# Initialize FastAPI
app = FastAPI(root_path="/api")
app.include_router(auth.router)
app.include_router(logic.router)
app.include_router(resources.router)

@app.get("/readyz", tags=["health"], summary="Readiness probe")
def check():
    return "Ready"