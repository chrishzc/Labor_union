"""Private fixed LINE verification relay. It accepts no URL, SQL or approval operation."""
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
import requests

from infrastructure.line.liff_token_verifier import VERIFY_ID_TOKEN_URL


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return JSONResponse(status_code=422, content={"error": "invalid_verification_request"})


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=1, max_length=4096)
    client_id: str = Field(min_length=1, max_length=100)


@app.post("/verify")
def verify(payload: VerificationRequest):
    if payload.client_id != os.environ.get("LINE_LOGIN_CHANNEL_ID"):
        return JSONResponse(status_code=400, content={"error": "invalid_client"})
    try:
        response = requests.post(VERIFY_ID_TOKEN_URL, data=payload.model_dump(), timeout=8)
        claims = response.json()
    except (requests.RequestException, ValueError):
        return JSONResponse(status_code=503, content={"error": "verification_unavailable"})
    if response.status_code != 200:
        return JSONResponse(status_code=400, content={"error": "invalid_token"})
    # Do not relay profile/PII claims the verifier does not use.
    return {key: claims[key] for key in ("iss", "sub", "aud", "exp") if key in claims}
