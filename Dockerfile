FROM python:3.14.9-slim@sha256:b347e2dcbc7f0b6f9fb7182e9da6a187fb10ae715e0692518c1aed0eec94a700

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CONTROLLED_FILE_STORAGE_ROOT=/data/controlled-files

WORKDIR /app

COPY requirements.txt pyproject.toml .python-version ./
RUN python -m pip install --no-cache-dir "pip>=26.2.2" \
    && python -m pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data/controlled-files \
    && chown app:app /data/controlled-files

COPY --chown=app:app . .

USER app

VOLUME ["/data/controlled-files"]

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
