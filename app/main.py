from fastapi import FastAPI
from .database import engine, Base
from . import models
from .routers import alerts, auth, templates, messages, feedback, profiles, registration

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Climate Risk Advisor API")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
app.include_router(templates.router, prefix="/templates", tags=["templates"])
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
app.include_router(registration.router, prefix="/registration", tags=["registration"])

@app.get("/")
def root():
    return {"status": "ok"}