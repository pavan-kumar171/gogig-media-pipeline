import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.api.routes import router
from app.core.database import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="goGig Intelligent Media Processing Pipeline",
    description="Async image upload + heuristic quality/fraud analysis for field vehicle photos.",
    version="1.0.0",
)

# Dev convenience: create tables on startup if they don't exist. A real
# production setup would use Alembic migrations instead (not implemented
# here - see README trade-offs) so schema changes are versioned and
# reversible instead of "whatever create_all() infers right now".
Base.metadata.create_all(bind=engine)

app.include_router(router, prefix="/api/v1", tags=["pipeline"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
