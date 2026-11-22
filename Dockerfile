# Streamlit demo image. The organiser's sample data is NOT baked in: mount your data/ directory at run time.
#   docker build -t followthefake .
#   docker run --rm -p 8501:8501 --env-file .env -v "%cd%/data:/app/data" followthefake      (Windows cmd)
#   docker run --rm -p 8501:8501 --env-file .env -v "$PWD/data:/app/data" followthefake      (Linux/macOS)
# Without --env-file the demo still works for sample cases; analysing new material needs GEMINI_API_KEY.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY schemas ./schemas
COPY prompts ./prompts
COPY config ./config
COPY src ./src
COPY data/gold/groups.json ./data/gold/groups.json

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "src/ads/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
