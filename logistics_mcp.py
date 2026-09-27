# logistics_mcp.py - the AfyaPlus logistics MCP server.
# Three read-only tools and two resources over clinics.json. Production habits:
# input checking, errors returned as instructive data, one log line per call
# carrying the caller's trace id (TRACE_ID env var, set per request by the agent).
import functools
import inspect
import json
import math
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config import get_logger

log = get_logger("logistics_mcp", "mcp_server.log")
TRACE_ID = os.getenv("TRACE_ID", "-")

mcp = FastMCP("afyaplus-logistics")

with open(Path(__file__).parent / "clinics.json", encoding="utf-8") as f:
    CLINICS = json.load(f)["clinics"]

VALID_ITEMS = ["amoxicillin", "ors_sachets", "malaria_kits"]
VALID_IDS = [c["id"] for c in CLINICS]
VALID_COUNTIES = sorted({c["county"] for c in CLINICS})
REORDER_THRESHOLD = 10
ASSUMED_SPEED_KMH = 40
_BY_ID = {c["id"]: c for c in CLINICS}


def error(message: str, **extra) -> str:
    """Errors are data: a JSON object the agent can read and correct itself from."""
    return json.dumps({"error": message, **extra})


def logged(fn):
    """Write exactly one log line per call: trace, tool, arguments, outcome, time."""
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        outcome = "exception"
        try:
            result = fn(*args, **kwargs)
            outcome = "error" if result.startswith('{"error"') else "ok"
            return result
        finally:
            ms = int((time.perf_counter() - started) * 1000)
            bound = signature.bind_partial(*args, **kwargs).arguments
            shown = " ".join(f"{k}={str(v)[:60]!r}" for k, v in bound.items())
            log.info("trace=%s tool=%s %s outcome=%s ms=%s", TRACE_ID, fn.__name__, shown, outcome, ms)
    return wrapper


def distance_km(a: dict, b: dict) -> float:
    """Rough straight-line distance between two clinics in kilometres."""
    dx = (a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    dy = (a["lat"] - b["lat"]) * 110.57
    return round(math.sqrt(dx * dx + dy * dy), 1)


def _clinic(clinic_id: str) -> dict | None:
    return _BY_ID.get(str(clinic_id).strip().upper())


# ------------------------------ tools ------------------------------

@mcp.tool()
@logged
def check_stock(item: str, county: str | None = None) -> str:
    """Report how many UNITS of one medical item each AfyaPlus clinic has on hand.

    Args:
        item: one of "amoxicillin", "ors_sachets", "malaria_kits" (exact names).
        county: optional county filter, e.g. "Kisumu". Omit for all clinics.

    Returns JSON {"item", "reorder_threshold", "stock": [{"clinic_id", "clinic",
    "county", "units", "reorder_needed"}]}. reorder_needed is true when units < 10.
    Counts are units on hand only: this data has NO prices, costs, suppliers,
    expiry dates, consumption history or staff information.
    Unknown item or county returns {"error": ..., "valid_values": [...]}.
    """
    item_key = str(item).strip().lower()
    if item_key not in VALID_ITEMS:
        return error(f"Unknown item '{item}'.", valid_values=VALID_ITEMS)
    rows = CLINICS
    if county:
        match = next((c for c in VALID_COUNTIES if c.lower() == county.strip().lower()), None)
        if match is None:
            return error(f"Unknown county '{county}'.", valid_values=VALID_COUNTIES)
        rows = [c for c in CLINICS if c["county"] == match]
    return json.dumps({
        "item": item_key,
        "reorder_threshold": REORDER_THRESHOLD,
        "stock": [{"clinic_id": c["id"], "clinic": c["name"], "county": c["county"],
                   "units": c["stock"][item_key],
                   "reorder_needed": c["stock"][item_key] < REORDER_THRESHOLD}
                  for c in rows],
    })


@mcp.tool()
@logged
def plan_delivery_route(start_clinic_id: str, stop_clinic_ids: list[str] | None = None) -> str:
    """Plan a delivery route that starts at one clinic and visits the other stops.

    Uses the nearest-neighbour rule (always drive to the closest unvisited stop next)
    on straight-line distances. This is quick decision support, NOT a guaranteed-
    shortest route and NOT road distance.

    Args:
        start_clinic_id: clinic id where the driver starts, e.g. "C01".
        stop_clinic_ids: optional list of clinic ids to visit, e.g. ["C02", "C04"].
            Omit to visit every clinic. The start clinic is ignored if repeated here.

    Returns JSON {"route": [{"clinic_id", "clinic", "leg_km"}], "total_km", "method"}.
    Unknown ids return {"error": ..., "valid_values": [...]}.
    """
    start = _clinic(start_clinic_id)
    if start is None:
        return error(f"Unknown clinic id '{start_clinic_id}'.", valid_values=VALID_IDS)
    if stop_clinic_ids is None:
        stops = [c for c in CLINICS if c["id"] != start["id"]]
    else:
        unknown = [s for s in stop_clinic_ids if _clinic(s) is None]
        if unknown:
            return error(f"Unknown clinic id(s) {unknown}.", valid_values=VALID_IDS)
        stops = list({_clinic(s)["id"]: _clinic(s) for s in stop_clinic_ids
                      if _clinic(s)["id"] != start["id"]}.values())
        if not stops:
            return error("No stops to visit besides the start clinic.",
                         hint="Pass at least one other clinic id, or omit stop_clinic_ids.")
    route = [{"clinic_id": start["id"], "clinic": start["name"], "leg_km": 0.0}]
    here, remaining, total = start, stops, 0.0
    while remaining:
        nearest = min(remaining, key=lambda c: distance_km(here, c))
        leg = distance_km(here, nearest)
        total += leg
        route.append({"clinic_id": nearest["id"], "clinic": nearest["name"], "leg_km": leg})
        remaining.remove(nearest)
        here = nearest
    return json.dumps({"route": route, "total_km": round(total, 1),
                       "method": "nearest-neighbour heuristic on straight-line distance"})


@mcp.tool()
@logged
def get_delivery_eta(from_clinic_id: str, to_clinic_id: str) -> str:
    """Estimate distance and driving time between two clinics.

    Straight-line kilometres at an ASSUMED average of 40 km/h on regional roads,
    rounded to the nearest 5 minutes. A planning estimate, not a commitment:
    weather, road class and traffic are not modelled.

    Args:
        from_clinic_id: clinic id, e.g. "C01".
        to_clinic_id: a different clinic id, e.g. "C04".

    Returns JSON {"from", "to", "distance_km", "eta_minutes", "assumed_speed_kmh"}.
    Unknown or identical ids return {"error": ...}.
    """
    a, b = _clinic(from_clinic_id), _clinic(to_clinic_id)
    if a is None or b is None:
        bad = from_clinic_id if a is None else to_clinic_id
        return error(f"Unknown clinic id '{bad}'. Only clinics can be routed between.",
                     valid_values=VALID_IDS)
    if a["id"] == b["id"]:
        return error("from_clinic_id and to_clinic_id are the same clinic.")
    km = distance_km(a, b)
    minutes = int(5 * round(km / ASSUMED_SPEED_KMH * 60 / 5))
    return json.dumps({"from": a["name"], "to": b["name"], "distance_km": km,
                       "eta_minutes": minutes, "assumed_speed_kmh": ASSUMED_SPEED_KMH})


# ---------------------------- resources ----------------------------

@mcp.resource("clinics://directory", mime_type="application/json")
@logged
def clinic_directory() -> str:
    """Read-only directory of all AfyaPlus partner clinics: id, name, county."""
    return json.dumps([{"id": c["id"], "name": c["name"], "county": c["county"]} for c in CLINICS])


@mcp.resource("clinics://{clinic_id}", mime_type="application/json")
@logged
def clinic_record(clinic_id: str) -> str:
    """Full read-only record for one clinic: coordinates and stock units."""
    c = _clinic(clinic_id)
    if c is None:
        return error(f"Unknown clinic id '{clinic_id}'.", valid_values=VALID_IDS)
    return json.dumps(c)


if __name__ == "__main__":
    mcp.run()          # stdio transport: stdout is the protocol, logs go to stderr + file
