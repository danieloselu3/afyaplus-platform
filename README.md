# AfyaPlus Service Platform

Moringa AI Engineering, Week 6 capstone. The platform has three parts:
- a **secured FastAPI triage service** (JWT, roles, rate limits, gpt-4o-mini),
- a **logistics MCP server** (3 tools, 2 resources),
- a **LangChain agent** behind the same authentication.

All of it is containerised and versioned. Current release: **v1.1.0**.

| Read this | For |
|---|---|
| [docs/MEMO.md](docs/MEMO.md) | One-page stakeholder memo: go / no-go |
| [docs/ENGINEERING_REPORT.md](docs/ENGINEERING_REPORT.md) | Version control, containers, trace rebuild, scaling scenario, deviations |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Branching, semantic versioning, release and conflict policy |
| [evidence/](evidence/) | Raw terminal evidence for every rubric line |

## Architecture

```text
client --POST /token--> triage-api :8000  --/triage-------> gpt-4o-mini (validated JSON)
       --Bearer JWT-->  agent-api  :8001  --/ask-logistics-> LangChain agent --MCP stdio--> logistics_mcp.py -> clinics.json
                         (both mount auth.py; every log line carries trace=<request id>)
```

## Run it

**Prerequisites:** Python 3.12, Docker Desktop, and an OpenAI key. The test suite needs no key.

```bash
cp .env.example .env          # set OPENAI_API_KEY and a long random JWT_SECRET
docker compose up -d --build  # triage on :8000, agent on :8001; both report healthy
curl localhost:8000/health
```

**Local dev:**

```bash
python -m venv venv && venv/Scripts/activate      # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                               # 50 tests, stub model, free
uvicorn triage_api:app --port 8000
uvicorn agent_api:app --port 8001
python agent.py "Which clinics need an amoxicillin reorder?"
npx @modelcontextprotocol/inspector python logistics_mcp.py   # interactive MCP testing
```

**Demo accounts.** Only bcrypt hashes are stored in `auth.py`.

| user | password | role | may use |
|---|---|---|---|
| `mercy` | `logistics2026` | coordinator | everything |
| `guest` | `viewonly2026` | viewer | `/ask-logistics` (stock tools only), `/reorders/propose`; gets **403** on `/triage` and on confirm |

## Endpoints

| Service | Endpoint | Auth | Notes |
|---|---|---|---|
| both | `GET /health` | open | `{service, version, status}` for probes |
| both | `POST /token` | open | `{username, password}` → 30-min HS256 JWT. 5 attempts per minute per client and user. |
| triage | `POST /triage` | coordinator | `{patient_message: 5–1000 chars, county: 2–40 letters}` → `{urgency, advice, model_used, handled_for, request_id}`. 5 calls per minute. Red-flag words always return `high`. Model failure → 503. |
| agent | `POST /ask-logistics` | any role | `{question: 5–500 chars}` → answer, tools used, model calls, tokens, `trace_id`. Viewer: stock tools only. |
| agent | `POST /reorders/propose` | any role | Creates a proposal. Nothing moves yet. |
| agent | `POST /reorders/{id}/confirm` | coordinator | Human-in-the-loop gate. Idempotent. |

## Rubric → evidence

| Criterion | Where |
|---|---|
| **Secure API (25)** | `triage_api.py`, `auth.py`. [01_secure_api_curl.txt](evidence/01_secure_api_curl.txt) shows 200, 401 (no, garbage, and wrong-password tokens), 403 (viewer), 422 (short, missing, non-JSON, extra field), 429 and 503. Server logs: [01_secure_api_server_logs.txt](evidence/01_secure_api_server_logs.txt). |
| **Containerisation (15)** | `Dockerfile`, `Dockerfile.agent`, `.dockerignore`. Cache demo: [02_docker_build.txt](evidence/02_docker_build.txt). Runtime secrets, secret-absence proof and size (266 MB): [02_docker_runtime.txt](evidence/02_docker_runtime.txt). Tags `v1.0.0` / `v1.1.0` match the image tags. |
| **MCP server (25)** | `logistics_mcp.py`. Inspector CLI with 5 deliberately invalid calls: [03_mcp_inspector_cli.txt](evidence/03_mcp_inspector_cli.txt). 18 tests, including an in-memory MCP client session. |
| **Agent (20)** | `agent.py`, `agent_api.py`. Multi-tool answers (A, C) and honest failures (B, D, E): [04_agent_transcripts.md](evidence/04_agent_transcripts.md). A defect found and fixed: [04_agent_scope_bug_before_fix.txt](evidence/04_agent_scope_bug_before_fix.txt). |
| **Report (15)** | Merge conflict: [06_merge_conflict.txt](evidence/06_merge_conflict.txt). [CONTRIBUTING.md](CONTRIBUTING.md). Trace rebuild: [report §4](docs/ENGINEERING_REPORT.md#4-observability-one-agent-request-rebuilt-from-the-logs). [Memo](docs/MEMO.md). |

## Fallbacks declared
- **None of the brief's fallback paths were needed.** Docker Desktop, OpenAI and the MCP Inspector all ran locally.
- **MCP Inspector evidence** is captured with the Inspector's **CLI mode** (text transcript) rather than browser screenshots. The same tool and protocol produce evidence that diffs in git.
- **Kubernetes** is limited to the read-only `deployment.yaml` plus the written scaling scenario (report §5). No cluster was used.
- **Stub model.** `TRIAGE_BACKEND=stub` switches triage to the course's deterministic model. It's used by the tests and CI, never for the evidence.

## Cost
- **Build total:** about **$0.005** of gpt-4o-mini (8 triage calls and 16 agent runs, about 29k tokens), counted from the services' own token log lines.
- **Per request:** each agent answer logs its own `model_calls`, `tokens_in` and `tokens_out`. A typical two-tool answer is 2–3 model calls, about 2–3k tokens, roughly $0.0005.
