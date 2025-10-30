from fastapi import FastAPI
from .api_jobs import router as jobs_router


def create_app() -> FastAPI:
    app = FastAPI(title="Scheduler API", version="0.1.0")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(jobs_router)

    return app


app = create_app()


