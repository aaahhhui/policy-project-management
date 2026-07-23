from fastapi import FastAPI

from app.modules.auth.router import router as auth_router

app = FastAPI(title="鏀垮簻绉戝垱鏀跨瓥绯荤粺", version="0.1.0")


app.include_router(auth_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
