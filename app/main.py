from fastapi import FastAPI
from .database import engine, Base
from . import models
from .routers import alerts, templates, messages, feedback

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Climate Risk Advisor API")

app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(templates.router, prefix="/templates", tags=["templates"])
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])

@app.get("/")
def root():
    return {"status": "ok"}