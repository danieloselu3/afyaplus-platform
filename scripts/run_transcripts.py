# run_transcripts.py - Deliverable 4 evidence through the authenticated agent API.
# Usage: python scripts/run_transcripts.py [base_url]  (agent_api running; writes evidence/)
# Each question is asked once; answers and trace log lines are captured verbatim.
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
LOGS = [ROOT / "logs" / n for n in ("agent_api.log", "agent.log", "mcp_server.log")]
OUT = ROOT / "evidence" / "04_agent_transcripts.md"

QUESTIONS = [
    ("A", "Multi-tool answer (coordinator)", "mercy", "logistics2026",
     "Which clinics need an amoxicillin reorder, and what route should the driver take from Kisumu Central?"),
    ("B", "Honest failure: the data cannot answer this", "mercy", "logistics2026",
     "What is the price of amoxicillin at each clinic?"),
    ("C", "Multi-step reasoning across three tools (coordinator)", "mercy", "logistics2026",
     "Homa Bay Lakeside has run out of amoxicillin. Which clinic holds the most amoxicillin, and "
     "how long would a delivery from that clinic to Homa Bay take?"),
    ("D", "Honest partial answer: a place that is not a clinic", "mercy", "logistics2026",
     "How long does a delivery take from Kisumu Central Clinic to Kisumu International Airport?"),
    ("E", "Permission rail: a viewer asks for a route", "guest", "viewonly2026",
     "What route should the driver take from Kisumu Central to visit every clinic?"),
]


def token(c: httpx.Client, user: str, password: str) -> str:
    return c.post(f"{BASE}/token", json={"username": user, "password": password}).json()["access_token"]


def trace_lines(trace_id: str) -> list[str]:
    lines = []
    for path in LOGS:
        if path.exists():
            lines += [f"{path.name}: {line}" for line in path.read_text(encoding="utf-8").splitlines()
                      if f"trace={trace_id} " in line]
    return sorted(lines, key=lambda s: s.split(": ", 1)[1][:23])


def main() -> None:
    md = [f"# Deliverable 4: agent transcripts via POST /ask-logistics",
          f"Captured {datetime.now(timezone.utc).isoformat(timespec='seconds')} against {BASE} "
          f"(gpt-4o-mini, temperature 0, recursion_limit 8). Answers are verbatim.", ""]
    total_in = total_out = 0
    with httpx.Client(timeout=120) as c:
        for key, title, user, password, question in QUESTIONS:
            headers = {"Authorization": f"Bearer {token(c, user, password)}"}
            r = c.post(f"{BASE}/ask-logistics", json={"question": question}, headers=headers)
            body = r.json()
            total_in += body.get("tokens_in", 0)
            total_out += body.get("tokens_out", 0)
            md += [f"## {key}. {title}", "",
                   f"**Request** `POST /ask-logistics` as `{user}`, HTTP **{r.status_code}**", "",
                   f"> {question}", "", "**Answer**", "", "```text", body.get("answer", json.dumps(body)), "```", "",
                   f"tools_used={body.get('tools_used')} model_calls={body.get('model_calls')} "
                   f"tokens_in={body.get('tokens_in')} tokens_out={body.get('tokens_out')} "
                   f"trace_id=`{body.get('trace_id')}`", "",
                   f"**Trace** `grep \"trace={body.get('trace_id')}\" logs/*.log`", "", "```text",
                   *trace_lines(body.get("trace_id", "?")), "```", ""]

        # Without a token, the agent never runs.
        r = c.post(f"{BASE}/ask-logistics", json={"question": QUESTIONS[0][4]})
        md += ["## F. No token", "", f"HTTP **{r.status_code}** `{r.text}`", ""]

        # Human-in-the-loop reorder rails.
        guest = {"Authorization": f"Bearer {token(c, 'guest', 'viewonly2026')}"}
        mercy = {"Authorization": f"Bearer {token(c, 'mercy', 'logistics2026')}"}
        p = c.post(f"{BASE}/reorders/propose", headers=guest,
                   json={"clinic_id": "C04", "item": "amoxicillin", "units": 50})
        pid = p.json()["id"]
        steps = [("propose as guest (viewer)", p),
                 ("confirm as guest (viewer)", c.post(f"{BASE}/reorders/{pid}/confirm", headers=guest)),
                 ("confirm as mercy (coordinator)", c.post(f"{BASE}/reorders/{pid}/confirm", headers=mercy)),
                 ("confirm AGAIN as mercy (network retry)", c.post(f"{BASE}/reorders/{pid}/confirm", headers=mercy))]
        md += ["## G. Human-in-the-loop reorder: the agent recommends, a coordinator confirms", "", "```text"]
        md += [f"{label:40s} HTTP {resp.status_code}  {resp.text}" for label, resp in steps]
        md += ["```", ""]

    # Guardrail comparison: same price question, agent run directly WITHOUT the system prompt.
    from agent import run_agent
    ablation = asyncio.run(run_agent(QUESTIONS[1][4], trace_id="ablation", system_prompt=None))
    total_in += ablation.tokens_in
    total_out += ablation.tokens_out
    md += ["## H. Guardrail comparison: question B with the system prompt removed", "",
           "Tool docstrings still state that stock counts are units with no prices.", "",
           "```text", ablation.answer, "```", "",
           f"tools_used={ablation.tools_used} model_calls={ablation.model_calls}", ""]

    cost = total_in / 1e6 * 0.15 + total_out / 1e6 * 0.60
    md += ["## Cost of this evidence run", "",
           f"tokens_in={total_in} tokens_out={total_out}, about ${cost:.4f} at gpt-4o-mini list prices "
           "($0.15 / $0.60 per million tokens)."]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT}  tokens_in={total_in} tokens_out={total_out} cost~${cost:.4f}")


if __name__ == "__main__":
    main()
