import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from app.api.routes import router
from app.core.database import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="goGig Intelligent Media Processing Pipeline",
    description="Async image upload + heuristic quality/fraud analysis for field vehicle photos.",
    version="1.0.0",
    docs_url=None,
)

# Dev convenience: create tables on startup if they don't exist. A real
# production setup would use Alembic migrations instead (not implemented
# here - see README trade-offs) so schema changes are versioned and
# reversible instead of "whatever create_all() infers right now".
Base.metadata.create_all(bind=engine)

app.include_router(router, prefix="/api/v1", tags=["pipeline"])

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="API Documentation",
        swagger_css_url="/static/swagger-dark.css",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})