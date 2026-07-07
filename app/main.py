from fastapi import FastAPI
from .database import engine, Base
from . import models
from .routers import alerts, templates

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Climate Risk Advisor API")

app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(templates.router, prefix="/templates", tags=["templates"])

@app.get("/")
def root():
    return {"status": "ok"}