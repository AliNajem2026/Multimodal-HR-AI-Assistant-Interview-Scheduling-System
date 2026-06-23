from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import engine, Base
from app.routers import scheduler

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Multimodal HR AI Assistant",
    version="2.0.0",
    description="Agentic interview scheduling powered by Claude AI + Google Calendar"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scheduler.router)

@app.get("/")
def health_check():
    return {"system_status": "Operational", "engine": "LangChain + Claude AI + Google Calendar"}
