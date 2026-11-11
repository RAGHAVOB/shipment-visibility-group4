"""Deterministic, synthetic shipment event engine for the Streamlit demonstration.

This module makes no network calls. It is a teaching simulation, not an AWS
implementation, authentication mechanism or source of DHL shipment data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)
RANK = {"MANIFESTED": 1, "PICKED_UP": 2, "IN_TRANSIT": 3, "AT_HUB": 4,
        "OUT_FOR_DELIVERY": 5, "DELIVERED": 6}
SOURCES = ("Carrier A", "Warehouse W1", "Supplier S1", "Customer POD")
DATA_DIR = Path(__file__).resolve().parent / "data"


def parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_data() -> dict:
    return json.loads((DATA_DIR / "synthetic_events.json").read_text(encoding="utf-8"))


def create_state() -> dict:
    seed = seed_data()
    state = {"now": iso(NOW), "shipments": [], "accepted": [], "duplicates": [],
             "quarantine": [], "outbox": [], "exceptions": [], "seen": set(),
             "source_health": {}, "audit": [], "buffer": [], "last_good": None}
    for row in seed["shipments"]:
        state["shipments"].append({**deepcopy(row), "status": "UNKNOWN",
                                 "last_event_at": None, "last_visible_at": None,
                                 "location": "", "events": []})
    for source in SOURCES:
        state["source_health"][source] = {"online": True, "heartbeat": iso(NOW - timedelta(minutes=2))}
    for event in seed["events"]:
        ingest(state, event)
    refresh_exceptions(state)
    return state


def audit(state: dict, action: str, detail: str, event: dict | None = None) -> None:
    entry = {"action": action, "detail": detail}
    if event:
        entry.update({"event_id": event.get("event_id", "UNKNOWN"),
                      "tenant_id": event.get("tenant_id", "UNKNOWN")})
    state["audit"].append(entry)


def ingest(state: dict, event: dict) -> dict:
    e = deepcopy(event)
    required = ("schema_version", "event_id", "source_event_id", "shipment_id", "tenant_id",
                "source", "event_type", "status", "occurred_at", "ingested_at", "visible_at")
    missing = [field for field in required if not e.get(field)]
    shipment = next((s for s in state["shipments"]
                     if s["id"] == e.get("shipment_id") and s["tenant"] == e.get("tenant_id")), None)
    failure = None
    if missing:
        failure = "Missing required fields: " + ", ".join(missing)
    elif e["schema_version"] != "1.0":
        failure = "Unsupported schema version"
    elif shipment is None:
        failure = "Unknown shipment or tenant mismatch"
    elif e["source"] not in SOURCES:
        failure = "Unregistered source"
    elif e["event_type"] not in ("MILESTONE", "EXCEPTION") or e["status"] not in RANK:
        failure = "Unknown event type or status"
    else:
        try:
            occurred, ingested, visible = (parse_time(e[k]) for k in
                                           ("occurred_at", "ingested_at", "visible_at"))
            if visible < ingested:
                failure = "Visibility precedes ingestion"
            elif occurred > ingested + timedelta(minutes=5):
                failure = "Event clock exceeds five minute skew tolerance"
        except (ValueError, TypeError, AttributeError):
            failure = "Invalid timestamp or missing timezone"
        if e["event_type"] == "EXCEPTION" and not e.get("reason"):
            failure = "Exception reason missing"
    if failure:
        e["validation_error"] = failure
        state["quarantine"].append(e)
        audit(state, "QUARANTINED", failure, e)
        return {"result": "quarantined", "reason": failure}
    key = (e["tenant_id"], e["source"], e["source_event_id"])
    if key in state["seen"]:
        state["duplicates"].append(e)
        audit(state, "DUPLICATE_SUPPRESSED", " | ".join(key), e)
        return {"result": "duplicate"}
    state["seen"].add(key)
    older = bool(shipment["last_event_at"] and parse_time(e["occurred_at"]) < parse_time(shipment["last_event_at"]))
    regression = RANK[e["status"]] < RANK.get(shipment["status"], 0)
    effect = "HISTORY_ONLY_OLDER_EVENT" if older else "HISTORY_ONLY_STATUS_REGRESSION" if regression else "APPLIED"
    e["projection_effect"] = effect
    shipment["events"].append(e)
    state["accepted"].append(e)
    if effect == "APPLIED":
        shipment.update({"status": e["status"], "location": e.get("location", ""),
                         "last_event_at": e["occurred_at"], "last_visible_at": e["visible_at"]})
        state["outbox"].append({"id": "OUT-" + str(len(state["outbox"])),
                                "event_id": e["event_id"], "tenant_id": e["tenant_id"],
                                "shipment_id": e["shipment_id"], "type": "SHIPMENT_CHANGED",
                                "delivery": "LOCAL_MOCK"})
    if e["event_type"] == "EXCEPTION":
        upsert_exception(state, shipment, e["reason"], e["source"])
    audit(state, effect, e["shipment_id"], e)
    return {"result": "accepted", "effect": effect}


def upsert_exception(state: dict, shipment: dict, reason: str, source: str) -> dict:
    key = "|".join((shipment["tenant"], shipment["id"], reason))
    found = next((e for e in state["exceptions"] if e["key"] == key), None)
    if found:
        return found
    found = {"key": key, "shipment_id": shipment["id"], "tenant_id": shipment["tenant"],
             "reason": reason, "source": source, "owner": "Unassigned", "state": "OPEN",
             "comment": "", "detected_at": state["now"]}
    state["exceptions"].append(found)
    return found


def refresh_exceptions(state: dict) -> None:
    now = parse_time(state["now"])
    for s in state["shipments"]:
        if s["status"] == "DELIVERED":
            continue
        if s["last_event_at"] and now - parse_time(s["last_event_at"]) > timedelta(minutes=30):
            upsert_exception(state, s, "STALE_SHIPMENT", s["source"])
        if now > parse_time(s["due_at"]):
            upsert_exception(state, s, "PROMISE_BREACH", s["source"])


def assign_exception(state: dict, key: str, owner: str, comment: str = "") -> bool:
    case = next((e for e in state["exceptions"] if e["key"] == key), None)
    if not case or not owner.strip() or owner == "Unassigned":
        return False
    case.update({"owner": owner, "state": "ACKNOWLEDGED", "comment": comment})
    audit(state, "EXCEPTION_ACKNOWLEDGED", case["shipment_id"] + " by " + owner,
          {"tenant_id": case["tenant_id"]})
    return True


def resolve_exception(state: dict, key: str, comment: str) -> bool:
    case = next((e for e in state["exceptions"] if e["key"] == key), None)
    if not case or case["owner"] == "Unassigned" or not comment.strip():
        return False
    case.update({"state": "RESOLVED", "comment": comment})
    audit(state, "EXCEPTION_RESOLVED", case["shipment_id"] + " by " + case["owner"] + ": " + comment,
          {"tenant_id": case["tenant_id"]})
    return True


def p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(.95 * len(values)) - 1] if values else 0


def metrics(state: dict, tenant: str) -> dict:
    sh = [s for s in state["shipments"] if s["tenant"] == tenant]
    events = [e for e in state["accepted"] if e["tenant_id"] == tenant]
    now = parse_time(state["now"])
    active = [s for s in sh if s["status"] != "DELIVERED" and s["last_event_at"]]
    return {"shipments": len(sh), "delivered": sum(s["status"] == "DELIVERED" for s in sh),
            "stale": sum(now - parse_time(s["last_event_at"]) > timedelta(minutes=30) for s in active),
            "open": sum(e["tenant_id"] == tenant and e["state"] != "RESOLVED" for e in state["exceptions"]),
            "sourceLagP95": p95([max(0, (parse_time(e["ingested_at"]) - parse_time(e["occurred_at"])).total_seconds()) for e in events]),
            "platformLagP95": p95([(parse_time(e["visible_at"]) - parse_time(e["ingested_at"])).total_seconds() for e in events]),
            "freshnessP95": p95([(now - parse_time(s["last_event_at"])).total_seconds() / 60 for s in active]),
            "accepted": len(events), "duplicates": sum(e.get("tenant_id") == tenant for e in state["duplicates"]),
            "quarantine": sum(e.get("tenant_id") == tenant for e in state["quarantine"])}


def sample_event(state: dict, **overrides) -> dict:
    n = len(state["accepted"]) + len(state["duplicates"]) + len(state["quarantine"]) + len(state["buffer"]) + 1
    now = parse_time(state["now"])
    result = {"schema_version": "1.0", "event_id": f"DEMO-{n}", "source_event_id": f"DEMO-SRC-{n}",
              "shipment_id": "SHP-1001", "tenant_id": "Retail Alpha", "source": "Carrier A",
              "event_type": "MILESTONE", "status": "OUT_FOR_DELIVERY",
              "occurred_at": iso(now - timedelta(seconds=20)),
              "ingested_at": iso(now - timedelta(seconds=10)),
              "visible_at": iso(now - timedelta(seconds=5)), "location": "Pune", "sequence": 10}
    result.update(overrides)
    return result


def receive(state: dict, event: dict) -> dict:
    if event.get("source") in state["source_health"] and not state["source_health"][event["source"]]["online"]:
        state["buffer"].append(deepcopy(event))
        audit(state, "BUFFERED_AT_SOURCE", "Synthetic edge buffer pending source recovery", event)
        return {"result": "buffered"}
    result = ingest(state, event)
    refresh_exceptions(state)
    return result


def source_outage(state: dict) -> None:
    state["source_health"]["Carrier A"] = {"online": False,
        "heartbeat": iso(parse_time(state["now"]) - timedelta(minutes=55))}
    audit(state, "SOURCE_OUTAGE_SIMULATED", "Carrier A synthetic heartbeat is 55 minutes old")


def source_recovery(state: dict) -> dict:
    state["source_health"]["Carrier A"] = {"online": True, "heartbeat": state["now"]}
    pending, state["buffer"] = state["buffer"], []
    results = []
    for event in pending:
        e = {**event, "ingested_at": iso(parse_time(state["now"]) - timedelta(seconds=10)),
             "visible_at": iso(parse_time(state["now"]) - timedelta(seconds=5))}
        results.append(ingest(state, e))
    refresh_exceptions(state)
    audit(state, "SOURCE_RECOVERED_SIMULATED", f"Carrier A recovered; released {len(pending)} buffered event(s)")
    return {"released": len(pending), "results": results}


def demo_action(state: dict, action: str) -> str:
    if action == "new":
        event = sample_event(state)
        state["last_good"] = deepcopy(event)
        result = receive(state, event)
    elif action == "duplicate":
        if not state["last_good"]:
            return "Run New milestone first to establish a retryable source event ID."
        event = {**state["last_good"], "event_id": state["last_good"]["event_id"] + "-RETRY"}
        result = receive(state, event)
    elif action == "older":
        event = sample_event(state, occurred_at=iso(parse_time(state["now"]) - timedelta(minutes=100)),
                             status="PICKED_UP", location="Mumbai")
        result = receive(state, event)
    elif action == "invalid":
        event = sample_event(state)
        del event["shipment_id"]
        result = receive(state, event)
    elif action == "wrong_tenant":
        event = sample_event(state, tenant_id="Industrial Beta")
        result = receive(state, event)
    elif action == "outage":
        source_outage(state)
        return "Carrier A is offline with a 55 minute old synthetic heartbeat. Use New milestone to buffer an update, then Recover source."
    elif action == "recover":
        recovery = source_recovery(state)
        return f"Carrier A recovered. Released {recovery['released']} buffered update(s) through validation and deduplication. No missing physical scans were invented."
    else:
        raise ValueError("Unknown demonstration action")
    if result["result"] == "buffered":
        return "Source is offline. Update buffered at the synthetic partner edge. Operational state did not advance."
    if result["result"] == "accepted":
        return event["event_id"] + ": " + result["effect"].replace("_", " ").lower() + ". All downstream notification effects are local mock records."
    if result["result"] == "duplicate":
        return "Duplicate retry suppressed. No second state change or local outbox outcome."
    return "Quarantined: " + result["reason"] + ". Operational state did not change."


def full_scenario(state: dict) -> list[str]:
    return [demo_action(state, action) for action in ("new", "duplicate", "older", "invalid", "outage", "new", "recover")]


def repair_quarantined(state: dict, index: int) -> dict:
    original = state["quarantine"][index]
    if original.get("repaired"):
        return {"result": "already_repaired"}
    repaired = {k: deepcopy(v) for k, v in original.items() if k not in ("validation_error", "repaired")}
    repaired.update({"event_id": original["event_id"] + "-REPAIRED", "shipment_id": "SHP-1001"})
    # The demo only repairs the known missing-ID scenario. Tenant conflicts are
    # deliberately not reassigned across customer boundaries.
    if original.get("tenant_id") != "Retail Alpha" or original.get("shipment_id"):
        return {"result": "manual_review_required"}
    result = receive(state, repaired)
    original["repaired"] = result["result"] in ("accepted", "buffered", "duplicate")
    return result


def tenant_export(state: dict, tenant: str) -> dict:
    return {"disclosure": "Synthetic academic simulation. No DHL live data or AWS deployment.",
            "simulation_clock": state["now"], "selected_tenant": tenant,
            "metrics": metrics(state, tenant),
            "shipments": [s for s in state["shipments"] if s["tenant"] == tenant],
            "accepted_events": [e for e in state["accepted"] if e["tenant_id"] == tenant],
            "duplicates": [e for e in state["duplicates"] if e.get("tenant_id") == tenant],
            "quarantine": [e for e in state["quarantine"] if e.get("tenant_id") == tenant],
            "exceptions": [e for e in state["exceptions"] if e["tenant_id"] == tenant],
            "mock_outbox": [e for e in state["outbox"] if e["tenant_id"] == tenant],
            "audit": [e for e in state["audit"] if not e.get("tenant_id") or e.get("tenant_id") == tenant]}
