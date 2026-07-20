FROM python:3.12-slim

# tesseract-ocr: needed for plate OCR check
# libgl1 / libglib2.0-0: OpenCV's runtime deps (headless build still needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Local docker-compose overrides this `command:` per-service (api vs
# worker run separately - see docker-compose.yml). This default CMD is
# what free-tier single-container hosts (Render free web service) use:
# it runs both processes together. See entrypoint.sh for why.
CMD ["/app/entrypoint.sh"]