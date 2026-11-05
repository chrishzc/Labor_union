ARG PYTHON_IMAGE=python:3.14-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966
FROM ${PYTHON_IMAGE}
WORKDIR /app
COPY deploy/registration/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY domains /app/domains
COPY shared_kernel /app/shared_kernel
COPY subsystems /app/subsystems
COPY api/schemas /app/api/schemas
COPY api/error_contracts.py api/registration_contracts.py api/registration_intake.py api/registration_token_verification.py /app/api/
COPY infrastructure/line/liff_token_verifier.py infrastructure/line/registration_token_verifier.py /app/infrastructure/line/
COPY infrastructure/redis /app/infrastructure/redis
# No MySQL module, MySQL driver, app settings or SQL credentials are present in this image.
USER 65532:65532
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "api.registration_intake:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
