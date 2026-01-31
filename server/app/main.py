from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.main import api_router
from app.auth.router import auth_router
from app.core.database.database import create_db_and_tables
from app.core.config import ORIGINS
from app.core.config import initialize_tables_dataset

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    initialize_tables_dataset()
    yield

app = FastAPI(title="R2R API Backend", version="1.0.0", lifespan=lifespan)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "API Backend"}

app.include_router(auth_router)
app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
