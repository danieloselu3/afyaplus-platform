import asyncio
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

import logistics_mcp as m
from config import LOG_DIR


# ---------- tool functions called directly (fastest check, no protocol) ----------

def test_check_stock_flags_reorders():
    data = json.loads(m.check_stock("amoxicillin"))
    reorder = {r["clinic_id"] for r in data["stock"] if r["reorder_needed"]}
    assert reorder == {"C02", "C04"}


def test_check_stock_normalises_and_filters_by_county():
    data = json.loads(m.check_stock("  Malaria_Kits ", county="kisumu"))
    assert data["item"] == "malaria_kits"
    assert [r["clinic_id"] for r in data["stock"]] == ["C01", "C05"]


def test_check_stock_states_its_scope():
    # Regression: the agent once generalised a county subset to the whole network.
    assert json.loads(m.check_stock("amoxicillin"))["clinics_included"] == "all 5 clinics"
    subset = json.loads(m.check_stock("amoxicillin", county="Kisumu"))["clinics_included"]
    assert subset == "2 of 5 clinics (county=Kisumu only)"


@pytest.mark.parametrize("call,valid", [
    (lambda: m.check_stock("bandages"), m.VALID_ITEMS),
    (lambda: m.check_stock("amoxicillin", county="Nairobi"), m.VALID_COUNTIES),
    (lambda: m.plan_delivery_route("C99"), m.VALID_IDS),
    (lambda: m.plan_delivery_route("C01", ["C02", "X7"]), m.VALID_IDS),
    (lambda: m.get_delivery_eta("C01", "airport"), m.VALID_IDS),
])
def test_invalid_input_returns_error_as_data_with_valid_values(call, valid):
    data = json.loads(call())
    assert "error" in data
    assert data["valid_values"] == valid


def test_route_matches_the_lab_total():
    data = json.loads(m.plan_delivery_route("C01"))
    assert [s["clinic_id"] for s in data["route"]] == ["C01", "C05", "C02", "C04", "C03"]
    assert data["total_km"] == 135.1


def test_route_with_chosen_stops_and_duplicate_start_ignored():
    data = json.loads(m.plan_delivery_route("c01", ["C04", "C02", "C01", "C02"]))
    assert [s["clinic_id"] for s in data["route"]] == ["C01", "C02", "C04"]


def test_route_with_no_real_stops_is_an_error():
    assert "error" in json.loads(m.plan_delivery_route("C01", ["C01"]))


def test_eta_c01_to_c04():
    data = json.loads(m.get_delivery_eta("C01", "C04"))
    assert data["distance_km"] == 59.3
    assert data["eta_minutes"] == 90 and data["assumed_speed_kmh"] == 40


def test_eta_same_clinic_is_an_error():
    assert "error" in json.loads(m.get_delivery_eta("C03", "C03"))


def test_one_log_line_per_call():
    log_file = LOG_DIR / "mcp_server.log"
    before = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []
    m.check_stock("amoxicillin")
    m.check_stock("bandages")
    lines = log_file.read_text(encoding="utf-8").splitlines()[len(before):]
    assert len(lines) == 2
    assert "tool=check_stock item='amoxicillin' outcome=ok" in lines[0]
    assert "outcome=error" in lines[1]


# ---------- the same server over the real MCP protocol (what an agent sees) ----------

async def _session_run(fn):
    async with create_connected_server_and_client_session(m.mcp._mcp_server) as session:
        return await fn(session)


def test_protocol_lists_tools_and_resources():
    async def go(s):
        tools = await s.list_tools()
        resources = await s.list_resources()
        templates = await s.list_resource_templates()
        return tools, resources, templates
    tools, resources, templates = asyncio.run(_session_run(go))
    assert {t.name for t in tools.tools} == {"check_stock", "plan_delivery_route", "get_delivery_eta"}
    assert all("Returns JSON" in t.description for t in tools.tools)
    assert [str(r.uri) for r in resources.resources] == ["clinics://directory"]
    assert [t.uriTemplate for t in templates.resourceTemplates] == ["clinics://{clinic_id}"]


def test_protocol_reads_resources():
    async def go(s):
        return (await s.read_resource("clinics://directory"),
                await s.read_resource("clinics://C04"))
    directory, record = asyncio.run(_session_run(go))
    assert len(json.loads(directory.contents[0].text)) == 5
    assert json.loads(record.contents[0].text)["stock"]["amoxicillin"] == 0


def test_protocol_invalid_value_comes_back_as_data():
    async def go(s):
        return await s.call_tool("check_stock", {"item": "bandages"})
    result = asyncio.run(_session_run(go))
    assert not result.isError
    assert json.loads(result.content[0].text)["valid_values"] == m.VALID_ITEMS


def test_protocol_wrong_argument_shape_does_not_crash_server():
    async def go(s):
        missing = await s.call_tool("get_delivery_eta", {"from_clinic_id": "C01"})
        still_alive = await s.call_tool("check_stock", {"item": "ors_sachets"})
        return missing, still_alive
    missing, still_alive = asyncio.run(_session_run(go))
    assert missing.isError and "to_clinic_id" in missing.content[0].text
    assert not still_alive.isError
