FROM node:24-bookworm-slim AS frontend
WORKDIR /frontend
COPY ui_react/package*.json ./
RUN npm ci
COPY ui_react/ ./
RUN npm run build
WORKDIR /previous
COPY previous_ui/package*.json ./
RUN npm ci
COPY previous_ui/ ./
RUN npm run build

FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt pyproject.toml .python-version ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app && adduser --system --uid 1000 --ingroup app app
COPY api/ api/
COPY config/ config/
COPY db/ db/
COPY domains/ domains/
COPY infrastructure/ infrastructure/
COPY line/ line/
COPY scripts/ scripts/
COPY shared_kernel/ shared_kernel/
COPY subsystems/ subsystems/
COPY validation/ validation/
COPY document/line/ document/line/
COPY ui_react/package.json ui_react/package.json
COPY deployment/nas-test/web-setup/ /opt/nas/setup/
COPY nas-setup-style.css /opt/nas/setup/style.css
COPY db/fresh_schema/labor_union_fresh_current.sql /opt/nas/init/10-fresh-schema.sql
COPY deployment/nas/20-lock-legacy-app.sql /opt/nas/init/20-restrict-app.sql
COPY deployment/nas/mysql-client.cnf /opt/nas/init/mysql-client.cnf
COPY deployment/nas-test/99-ready.sh /opt/nas/init/99-ready.sh
COPY --from=frontend /frontend/dist /tmp/current-dist
COPY --from=frontend /previous/dist /tmp/previous-dist
ARG SOURCE_REF
ARG PREVIOUS_SOURCE_REF
ARG API_REVISION
RUN python -m scripts.build_react_admin_artifact --build --skip-frontend-build \
      --source /tmp/current-dist --output /opt/react-admin/current \
      --source-ref "$SOURCE_REF" --api-compatibility-revision "$API_REVISION" \
    && python -m scripts.build_react_admin_artifact --build --skip-frontend-build \
      --source /tmp/previous-dist --output /opt/react-admin/previous \
      --source-ref "$PREVIOUS_SOURCE_REF" --api-compatibility-revision "$API_REVISION" \
    && rm -rf /tmp/current-dist /tmp/previous-dist \
    && find /opt/react-admin -type d -exec chmod 755 {} + \
    && find /opt/react-admin -type f -exec chmod 644 {} +
CMD ["python", "-m", "scripts.nas_security_runtime", "management-api"]
