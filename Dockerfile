# Demo image: web panel by default, Streamlit demo and every CLI command available too.
# The organiser's sample data is NOT baked in: mount your data/ directory at run time.
#
#   docker compose up --build                      # web panel on http://127.0.0.1:8000 (see docker-compose.yml)
#
# or without compose:
#   docker build -t fakefreak .
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v "$PWD/data:/app/data" fakefreak       (Linux/macOS)
#   docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v "%cd%/data:/app/data" fakefreak       (Windows cmd)
# Without --env-file everything works on the cases already in data/; analysing new material needs GEMINI_API_KEY.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONPATH=/app/src \
    ADS_HOST=0.0.0.0 \
    ADS_PORT=8000
WORKDIR /app

# Pinned versions (requirements.lock, generated from requirements.txt): the image builds the same every time.
COPY requirements.lock .
RUN pip install -r requirements.lock

COPY schemas ./schemas
COPY prompts ./prompts
COPY config ./config
COPY src ./src
COPY data/gold/groups.json ./data/gold/groups.json

# Unprivileged user. The cache (LLM responses, image fingerprints) is world-writable so the container also works
# when it is started with another uid (docker-compose.yml: ADS_UID / ADS_GID).
RUN useradd --uid 1000 --create-home app \
    && mkdir -p data/cases data/raw .cache \
    && chown -R app:app data .cache \
    && chmod 1777 .cache
USER app
WORKDIR /app/src

EXPOSE 8000 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/status' % os.environ.get('ADS_PORT', '8000'), timeout=4)" || exit 1
CMD ["python", "-m", "ads.web.server"]
