from app.core.config import settings
from app.routers import api_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="praesens")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
