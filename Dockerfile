FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    CONTROLLED_FILE_STORAGE_ROOT=/data/controlled-files

WORKDIR /app

COPY requirements.txt pyproject.toml .python-version ./
RUN python -m pip install --no-cache-dir --upgrade pip \
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
