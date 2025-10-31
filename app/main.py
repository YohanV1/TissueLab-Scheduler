from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .api_jobs import router as jobs_router
from .api_workflows import router as workflows_router
from .api_files import router as files_router


def create_app() -> FastAPI:
    app = FastAPI(title="Scheduler API", version="0.1.0")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(jobs_router)
    app.include_router(workflows_router)
    app.include_router(files_router)

    # Serve static UI at /ui
    app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")

    return app


app = create_app()


