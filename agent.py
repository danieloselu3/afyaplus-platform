# agent.py - a LangChain agent (gpt-4o-mini) that uses the logistics MCP server's tools.
# One MCP server process per request, started with TRACE_ID in its environment,
# so every tool log line carries the same id as the API request that caused it.
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError

from config import LOG_DIR, OPENAI_MODEL, get_logger

log = get_logger("agent", "agent.log")
HERE = Path(__file__).parent

RECURSION_LIMIT = 8            # loop budget: a confused agent fails fast and cheap
ROLE_TOOLS = {                 # permission rail: which tools each JWT role may use
    "coordinator": {"check_stock", "plan_delivery_route", "get_delivery_eta"},
    "viewer": {"check_stock"},
}

SYSTEM_PROMPT = """You are the AfyaPlus logistics assistant for clinic supply coordinators in western Kenya.
Answer ONLY from what your tools return. The tools cover five partner clinics: stock UNITS on hand
of amoxicillin, ORS sachets and malaria kits; delivery route planning; and delivery time estimates.
If the tools cannot answer all or part of a question (for example prices, costs, suppliers, expiry
dates, patient information, or places that are not partner clinics), say plainly which data is
missing and why, then offer what you CAN answer. Never estimate, assume or invent values.
When you give a time estimate, mention the distance and that it assumes the tool's average speed.
Only make network-wide claims ("no clinics", "all clinics") from a result whose
clinics_included covers all clinics. A clinic's name is not a county filter.
Quote clinic names and numbers exactly as the tools return them, and keep answers short.
You recommend; people decide. You cannot place orders or dispatch drivers."""

ROLE_NOTES = {
    "coordinator": "The user is a coordinator: all logistics tools are available.",
    "viewer": ("The user has the VIEWER role: only stock look-ups are available. Route planning "
               "and delivery estimates need the coordinator role; say so if they are asked for."),
}


@dataclass
class AgentRun:
    answer: str
    status: str                                   # "answered" | "step_limit"
    tools_used: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


def _mcp_client(trace_id: str) -> MultiServerMCPClient:
    return MultiServerMCPClient({
        "logistics": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(HERE / "logistics_mcp.py")],
            "cwd": str(HERE),
            # The stdio client passes only a minimal default environment, so name what the server needs.
            "env": {"TRACE_ID": trace_id, "LOG_DIR": str(LOG_DIR), "PYTHONUNBUFFERED": "1"},
        }
    })


def _summarise(messages: list, run: AgentRun) -> None:
    """Roll up cost and build a readable step list from the agent's message history."""
    for msg in messages:
        if isinstance(msg, AIMessage):
            run.model_calls += 1
            usage = msg.usage_metadata or {}
            run.tokens_in += usage.get("input_tokens", 0)
            run.tokens_out += usage.get("output_tokens", 0)
            for call in msg.tool_calls:
                run.tools_used.append(call["name"])
                run.steps.append({"act": call["name"], "args": call["args"]})
        elif isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, list):          # MCP content blocks -> their text
                content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
            run.steps.append({"observe": msg.name, "result": str(content)[:600]})


async def run_agent(question: str, trace_id: str, role: str = "coordinator",
                    history: list | None = None, system_prompt: str | None = SYSTEM_PROMPT) -> AgentRun:
    """Answer one question with the MCP tools this role may use. Raises on model/network failure."""
    client = _mcp_client(trace_id)
    async with client.session("logistics") as session:
        tools = [t for t in await load_mcp_tools(session) if t.name in ROLE_TOOLS[role]]
        model = ChatOpenAI(model=OPENAI_MODEL, temperature=0, timeout=30, max_retries=1,
                           api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"{system_prompt}\n{ROLE_NOTES[role]}" if system_prompt else None
        agent = create_agent(model, tools, system_prompt=prompt)
        messages = [*(history or []), ("user", question)]
        log.info("trace=%s agent_start role=%s tools=%s", trace_id, role, sorted(t.name for t in tools))
        try:
            state = await agent.ainvoke({"messages": messages},
                                        {"recursion_limit": RECURSION_LIMIT})
            final = state["messages"][-1]
            run = AgentRun(answer=final.content, status="answered")
            _summarise(state["messages"][len(messages):], run)
        except GraphRecursionError:
            run = AgentRun(answer="I ran out of reasoning steps before finding a reliable answer. "
                                  "Please ask a narrower question.", status="step_limit")
    for i, step in enumerate(s for s in run.steps if "act" in s):
        log.info("trace=%s step=%s tool_call=%s args=%s", trace_id, i + 1, step["act"],
                 json.dumps(step["args"])[:200])
    log.info("trace=%s agent_end status=%s model_calls=%s tokens_in=%s tokens_out=%s",
             trace_id, run.status, run.model_calls, run.tokens_in, run.tokens_out)
    return run


if __name__ == "__main__":
    # Lab 2 style smoke test: python agent.py "your question"
    q = " ".join(sys.argv[1:]) or ("Which clinics need an amoxicillin reorder, and what route "
                                   "should the driver take from Kisumu Central?")
    result = asyncio.run(run_agent(q, trace_id="cli"))
    print(json.dumps(result.__dict__, indent=2))
