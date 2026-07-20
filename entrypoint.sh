#!/bin/bash
# Free-tier deployment entrypoint: runs the Celery worker AND the FastAPI
# server inside ONE container/process, instead of the two separate
# containers used in docker-compose.yml.
#
# WHY THIS EXISTS: most free hosting tiers (e.g. Render's free plan) give
# you exactly one always-on process for $0; a second "worker" service
# costs extra. Rather than pay for a second container just for a 48-hour
# assignment, the worker is started as a background process inside the
# same container that runs the API. This is a deployment-only workaround -
# the actual code (API and worker) is completely unchanged from the
# docker-compose / local setup. See README "Trade-offs" for why this
# wouldn't be the right call at real scale (no independent scaling of
# worker vs API, one crash can affect both).
set -e

echo "Starting Celery worker in background..."
celery -A app.tasks.celery_app worker --loglevel=info -c 2 &

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"