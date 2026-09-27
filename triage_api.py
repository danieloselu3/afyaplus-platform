# triage_api.py - the secured AfyaPlus triage service
import time
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from auth import TOKEN_MINUTES, check_password, create_token, require_role
from config import TRIAGE_BACKEND, VERSION, get_logger
from rate_limit import check_rate_limit
from triage_model import ModelUnavailable, triage_model

SERVICE = "triage-api"
log = get_logger("triage_api", "triage_api.log")
audit = get_logger("audit", "audit.log")

app = FastAPI(title="AfyaPlus Triage API", version=VERSION)


# ---------- the agreement: typed request and response models ----------

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    patient_message: str = Field(min_length=5, max_length=1000,
                                 examples=["I have chest pain and feel dizzy"])
    county: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z '\-]+$",
                        examples=["Kisumu"])


class TriageResponse(BaseModel):
    urgency: Literal["low", "medium", "high"]
    advice: str
    model_used: str
    handled_for: str
    request_id: str


class HealthResponse(BaseModel):
    service: str
    version: str
    status: Literal["ok"]
    model_backend: str


# ---------- one log line per request, with an id the caller can quote ----------

@app.middleware("http")
async def request_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:8]
    request.state.request_id = request_id
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        ms = int((time.perf_counter() - started) * 1000)
        log.info("request_id=%s method=%s path=%s status=%s ms=%s",
                 request_id, request.method, request.url.path, status, ms)


def write_audit_line(request_id: str, username: str, county: str, urgency: str) -> None:
    """Who asked, when, where, and what came back. Never the message text."""
    audit.info("request_id=%s user=%s county=%s urgency=%s",
               request_id, username, county, urgency)


# ---------- endpoints ----------

@app.get("/health", response_model=HealthResponse)
def health():
    """Unprotected liveness probe for load balancers and Kubernetes."""
    return {"service": SERVICE, "version": VERSION, "status": "ok", "model_backend": TRIAGE_BACKEND}


@app.post("/token", response_model=TokenResponse)
def login(body: LoginRequest, request: Request):
    # Throttle guessing: key on client address + attempted username (callers have no token yet).
    client = request.client.host if request.client else "unknown"
    check_rate_limit(f"login:{client}:{body.username}", max_requests=5)
    if not check_password(body.username, body.password):
        log.warning("login_failed user=%s client=%s", body.username, client)
        raise HTTPException(status_code=401, detail="Wrong username or password.",
                            headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": create_token(body.username), "expires_in": TOKEN_MINUTES * 60}


@app.post("/triage", response_model=TriageResponse,
          responses={401: {"description": "Missing, invalid or expired token"},
                     403: {"description": "Authenticated, but role is not coordinator"},
                     429: {"description": "More than 5 triage calls per minute"},
                     503: {"description": "The AI model is unavailable"}})
def triage(body: TriageRequest, request: Request, background: BackgroundTasks,
           user: dict = Depends(require_role("coordinator"))):
    check_rate_limit(f"triage:{user['sub']}", max_requests=5)
    request_id = request.state.request_id
    try:
        result = triage_model(body.patient_message, body.county)
    except ModelUnavailable as exc:
        log.error("request_id=%s model_error=%s", request_id, exc)
        raise HTTPException(status_code=503, detail="The AI model is unavailable. Try again shortly.")
    log.info("request_id=%s model=%s tokens_in=%s tokens_out=%s",
             request_id, result["model_used"], result["tokens_in"], result["tokens_out"])
    background.add_task(write_audit_line, request_id, user["sub"], body.county, result["urgency"])
    return TriageResponse(urgency=result["urgency"], advice=result["advice"],
                          model_used=result["model_used"], handled_for=user["sub"],
                          request_id=request_id)
