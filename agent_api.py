# agent_api.py - the logistics agent behind an authenticated API.
# Reuses the Deliverable 1 auth module unchanged. The agent recommends; people decide:
# the only world-changing action (a reorder) needs a human coordinator to confirm it.
import asyncio
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

import agent as agent_module
from auth import auth_router, current_user, require_role
from config import VERSION, get_logger
from logistics_mcp import VALID_IDS, VALID_ITEMS
from observability import add_request_logging
from rate_limit import check_rate_limit

SERVICE = "agent-api"
AGENT_TIMEOUT_SECONDS = 90
log = get_logger("agent_api", "agent_api.log")

app = FastAPI(title="AfyaPlus Logistics Agent API", version=VERSION,
              description="Ask logistics questions. The agent recommends; people decide.")
add_request_logging(app, log)
app.include_router(auth_router)          # the same /token door as the triage service


# ---------- models ----------

class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=5, max_length=500,
                          examples=["Which clinics need an amoxicillin reorder?"])


class AskResponse(BaseModel):
    answer: str
    status: Literal["answered", "step_limit"]
    trace_id: str
    asked_by: str
    role: str
    tools_used: list[str]
    model_calls: int
    tokens_in: int
    tokens_out: int


class ReorderProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clinic_id: Literal[tuple(VALID_IDS)]            # type: ignore[valid-type]
    item: Literal[tuple(VALID_ITEMS)]               # type: ignore[valid-type]
    units: int = Field(gt=0, le=500)


class Reorder(BaseModel):
    id: str
    status: Literal["proposed", "confirmed"]
    clinic_id: str
    item: str
    units: int
    proposed_by: str
    proposed_at: str
    confirmed_by: str | None = None
    confirmed_at: str | None = None


PROPOSALS: dict[str, dict] = {}       # lab-grade store; production uses a database


# ---------- endpoints ----------

@app.get("/health")
def health():
    """Unprotected liveness probe."""
    return {"service": SERVICE, "version": VERSION, "status": "ok"}


@app.post("/ask-logistics", response_model=AskResponse,
          responses={401: {"description": "Missing, invalid or expired token"},
                     429: {"description": "More than 10 questions per minute"},
                     503: {"description": "The model or tool server is unavailable"}})
async def ask_logistics(body: AskRequest, request: Request, user: dict = Depends(current_user)):
    """Ask the logistics agent a question. Viewers get stock look-ups only;
    coordinators also get route planning and delivery estimates."""
    check_rate_limit(f"ask:{user['sub']}", max_requests=10)
    trace_id = request.state.trace_id
    started = time.perf_counter()
    run, outcome = None, "error"
    try:
        run = await asyncio.wait_for(
            agent_module.run_agent(body.question, trace_id=trace_id, role=user["role"]),
            timeout=AGENT_TIMEOUT_SECONDS)
        outcome = run.status
    except Exception as exc:          # model, network, MCP process or timeout
        log.error("trace=%s agent_error=%s", trace_id, type(exc).__name__)
        raise HTTPException(status_code=503,
                            detail=f"The logistics agent is unavailable. Quote trace id {trace_id}.")
    finally:
        # One metadata-only line per request: never the question text itself.
        ms = int((time.perf_counter() - started) * 1000)
        log.info("trace=%s user=%s role=%s outcome=%s ms=%s question_chars=%s "
                 "model_calls=%s tokens_in=%s tokens_out=%s tools=%s",
                 trace_id, user["sub"], user["role"], outcome, ms, len(body.question),
                 run.model_calls if run else 0, run.tokens_in if run else 0,
                 run.tokens_out if run else 0, ",".join(run.tools_used) if run else "")
    return AskResponse(answer=run.answer, status=run.status, trace_id=trace_id,
                       asked_by=user["sub"], role=user["role"], tools_used=run.tools_used,
                       model_calls=run.model_calls, tokens_in=run.tokens_in, tokens_out=run.tokens_out)


@app.post("/reorders/propose", response_model=Reorder, status_code=201)
def propose_reorder(body: ReorderProposal, request: Request, user: dict = Depends(current_user)):
    """Create a reorder proposal. Nothing moves until a coordinator confirms it."""
    pid = uuid4().hex[:12]
    PROPOSALS[pid] = {"id": pid, "status": "proposed", **body.model_dump(),
                      "proposed_by": user["sub"],
                      "proposed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    log.info("trace=%s reorder_proposed id=%s by=%s", request.state.trace_id, pid, user["sub"])
    return PROPOSALS[pid]


@app.post("/reorders/{proposal_id}/confirm", response_model=Reorder)
def confirm_reorder(proposal_id: str, request: Request,
                    user: dict = Depends(require_role("coordinator"))):
    """The human button. Coordinator only (403 otherwise). Idempotent: confirming
    twice returns the original confirmation unchanged. The role check runs first so
    non-coordinators cannot probe which proposal ids exist."""
    proposal = PROPOSALS.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="No proposal with that id.")
    if proposal["status"] == "confirmed":
        return proposal                 # the retry rail: same request, same result, no second action
    proposal.update(status="confirmed", confirmed_by=user["sub"],
                    confirmed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    log.info("trace=%s reorder_confirmed id=%s by=%s", request.state.trace_id, proposal_id, user["sub"])
    return proposal
