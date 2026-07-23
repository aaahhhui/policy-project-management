from fastapi import FastAPI

app = FastAPI(title="鏀垮簻绉戝垱鏀跨瓥绯荤粺", version="0.1.0")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
