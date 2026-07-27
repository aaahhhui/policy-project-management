from fastapi import FastAPI

from app.modules.auth.router import router as auth_router
from app.modules.collection.router import router as collection_router
from app.modules.policies.router import router as policies_router
from app.modules.profiles.router import router as profiles_router
from app.modules.sources.router import router as sources_router

app = FastAPI(title="鏀垮簻绉戝垱鏀跨瓥绯荤粺", version="0.1.0")


app.include_router(auth_router)
app.include_router(collection_router)
app.include_router(policies_router)
app.include_router(profiles_router)
app.include_router(sources_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
