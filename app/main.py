import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
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

# Allow browser-based frontends (like the upload page) to call this API
# from any origin, since it's served from a different address than this
# backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    base_html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="API Documentation",
    )
    # Inject our dark theme CSS in addition to (not instead of) Swagger's
    # own stylesheet, so the base layout still renders correctly.
    injected = base_html.body.decode("utf-8").replace(
        "</head>",
        '<link rel="stylesheet" href="/static/swagger-dark.css"></head>',
    )
    return HTMLResponse(content=injected)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})