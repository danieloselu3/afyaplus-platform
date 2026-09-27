# triage_api.py - the secured AfyaPlus triage service
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from auth import auth_router, require_role
from config import TRIAGE_BACKEND, VERSION, get_logger
from observability import add_request_logging
from rate_limit import check_rate_limit
from triage_model import ModelUnavailable, triage_model

SERVICE = "triage-api"
log = get_logger("triage_api", "triage_api.log")
audit = get_logger("audit", "audit.log")

app = FastAPI(title="AfyaPlus Triage API", version=VERSION)
add_request_logging(app, log)
app.include_router(auth_router)          # POST /token, shared with the agent API


# ---------- the agreement: typed request and response models ----------

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


def write_audit_line(trace_id: str, username: str, county: str, urgency: str) -> None:
    """Who asked, when, where, and what came back. Never the message text."""
    audit.info("trace=%s user=%s county=%s urgency=%s", trace_id, username, county, urgency)


# ---------- endpoints ----------

@app.get("/health", response_model=HealthResponse)
def health():
    """Unprotected liveness probe for load balancers and Kubernetes."""
    return {"service": SERVICE, "version": VERSION, "status": "ok", "model_backend": TRIAGE_BACKEND}


@app.post("/triage", response_model=TriageResponse,
          responses={401: {"description": "Missing, invalid or expired token"},
                     403: {"description": "Authenticated, but role is not coordinator"},
                     429: {"description": "More than 5 triage calls per minute"},
                     503: {"description": "The AI model is unavailable"}})
def triage(body: TriageRequest, request: Request, background: BackgroundTasks,
           user: dict = Depends(require_role("coordinator"))):
    check_rate_limit(f"triage:{user['sub']}", max_requests=5)
    trace_id = request.state.trace_id
    try:
        result = triage_model(body.patient_message, body.county)
    except ModelUnavailable as exc:
        log.error("trace=%s model_error=%s", trace_id, exc)
        raise HTTPException(status_code=503, detail="The AI model is unavailable. Try again shortly.")
    log.info("trace=%s model=%s tokens_in=%s tokens_out=%s",
             trace_id, result["model_used"], result["tokens_in"], result["tokens_out"])
    background.add_task(write_audit_line, trace_id, user["sub"], body.county, result["urgency"])
    return TriageResponse(urgency=result["urgency"], advice=result["advice"],
                          model_used=result["model_used"], handled_for=user["sub"],
                          request_id=trace_id)
