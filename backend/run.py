"""Run using stable settings: python /absolute/path/to/backend/run.py."""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.backend_port)
