from fastapi import FastAPI

app = FastAPI(title="clinic-crm")


@app.get("/health")
async def health():
    return {"status": "ok"}
