FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .
EXPOSE 8000
# Render (and most hosts) inject $PORT; fall back to 8000 locally.
# --app-dir backend puts the backend package on sys.path so main.py's
# sibling imports (extract, cims, compare, watermark) resolve.
CMD uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}
