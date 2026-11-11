"""Streamlit control tower with synthetic, session-local shipment events."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta, timezone
import csv
import io
import json

import pandas as pd
import streamlit as st

import engine as E

st.set_page_config(page_title="Shipment Visibility | Group 4", page_icon="🚚", layout="wide")
st.markdown("""<style>
  .block-container {padding-top:2rem; padding-bottom:3rem; max-width:1550px;}
  h1 {letter-spacing:-0.04em; color:#102d40;}
  h2,h3 {color:#18394b;}
  [data-testid="stMetric"] {background:#f0f6f6; padding:1rem; border-radius:.5rem;}
  [data-testid="stMetricLabel"] {font-size:.9rem;}
  [data-testid="stMetricValue"] {color:#086f64;}
  [data-testid="stSidebar"] {background:#edf3f5;}
  div.stButton > button {min-height:2.7rem;}
</style>""", unsafe_allow_html=True)

if "visibility_state" not in st.session_state:
    st.session_state.visibility_state = E.create_state()
if "tenant" not in st.session_state:
    st.session_state.tenant = "Retail Alpha"
if "last_message" not in st.session_state:
    st.session_state.last_message = "Ready. Seed events have populated the dashboard. No live events are arriving."
if "scenario_log" not in st.session_state:
    st.session_state.scenario_log = []


def do_action(action: str) -> None:
    state = st.session_state.visibility_state
    st.session_state.last_message = E.demo_action(state, action)
    if action not in ("outage", "recover", "wrong_tenant"):
        st.session_state.tenant = "Retail Alpha"


def reset_demo() -> None:
    st.session_state.visibility_state = E.create_state()
    st.session_state.last_message = "Reset to the original synthetic dataset. Session changes were discarded."
    st.session_state.scenario_log = []
    # Clear scenario-specific form values while retaining the workspace widget.
    for key in list(st.session_state.keys()):
        if key.startswith(("case_owner_", "case_note_", "selected_shipment")):
            del st.session_state[key]


def run_scenario() -> None:
    reset_demo()
    st.session_state.tenant = "Retail Alpha"
    st.session_state.scenario_log = E.full_scenario(st.session_state.visibility_state)
    st.session_state.last_message = "Scenario completed. One retry was suppressed, one invalid event was quarantined and one source-buffered update recovered."


def update_case(key: str, action: str, owner_widget: str, note_widget: str) -> None:
    state = st.session_state.visibility_state
    note = st.session_state.get(note_widget, "")
    owner = st.session_state.get(owner_widget, "Unassigned")
    if action == "assign":
        ok = E.assign_exception(state, key, owner, note)
        st.session_state.last_message = ("Case acknowledged by " + owner + ". No external notification was sent."
                                         if ok else "Select a named owner before assigning a case.")
    else:
        ok = E.resolve_exception(state, key, note)
        st.session_state.last_message = ("Case resolved with the named owner and action evidence preserved in the local audit."
                                         if ok else "Assign this case first and enter an action note before resolving.")


def repair_event(index: int) -> None:
    result = E.repair_quarantined(st.session_state.visibility_state, index)
    st.session_state.last_message = "Repair replay result: " + result["result"].replace("_", " ") + ". The original quarantine record is retained."


def label(value: str) -> str:
    return value.replace("_", " ").title()


def local_time(value: str) -> str:
    return E.parse_time(value).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%H:%M:%S IST")


def csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b"No records\n"
    fields = list(dict.fromkeys(k for row in rows for k in row))
    result = io.StringIO()
    writer = csv.DictWriter(result, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return result.getvalue().encode("utf-8-sig")


state = st.session_state.visibility_state
with st.sidebar:
    st.markdown("### Group 4 control tower")
    st.selectbox("Customer workspace", ["Retail Alpha", "Industrial Beta"], key="tenant")
    st.caption("The workspace filter illustrates a view boundary. It is not authentication or an authorization control.")
    st.divider()
    st.markdown("**Fixed simulation clock**")
    st.write("11 November 2026")
    st.write("15:30 IST / 10:00 UTC")
    st.caption("Timestamps and metric values are reproducible chosen inputs. No production latency is being measured.")
    st.button("Reset demonstration", key="reset_sidebar", on_click=reset_demo, width="stretch")
    st.divider()
    st.markdown("**Session scope**")
    st.caption("Each browser connection has its own Streamlit session state. There is no shared database, persistent shipment store or live carrier connection. A new session starts with the seed data.")

tenant = st.session_state.tenant
m = E.metrics(state, tenant)
shipments = [s for s in state["shipments"] if s["tenant"] == tenant]
events = [e for e in state["accepted"] if e["tenant_id"] == tenant]
cases = [e for e in state["exceptions"] if e["tenant_id"] == tenant]

st.caption("LOGISTICS AND SUPPLY CHAIN  /  SCENARIO A")
st.title("End to end shipment visibility")
st.write("A control tower for event freshness, trustworthy tracking history and accountable exception handling.")
st.warning("Academic demonstration: every shipment, partner, person and result below is synthetic. This proposed DHL Supply Chain India pilot is unaffiliated with DHL. The Streamlit app is interactive, but it has no DHL live data, AWS services or actual outbound notifications.")

row = st.columns(3)
row[0].metric("Shipments", m["shipments"], help=f"Includes {m['delivered']} delivered shipment(s).")
row[1].metric("Stale active shipments", m["stale"], help="Latest effective event age exceeds 30 minutes. Delivered shipments are excluded.")
row[2].metric("Unresolved exceptions", m["open"], help="Open and acknowledged cases. Resolved cases remain in audit history.")
row = st.columns(3)
row[0].metric("Partner delay P95", f"{m['sourceLagP95'] / 60:.1f} min", help="Ingested timestamp minus source occurrence timestamp, for accepted events.")
row[1].metric("Platform delay P95", f"{m['platformLagP95']:.0f} sec", help="Visible timestamp minus ingested timestamp, for accepted events.")
row[2].metric("Active event age P95", f"{m['freshnessP95']:.0f} min", help="Fixed simulation time minus latest effective occurred timestamp, excluding delivered shipments.")
st.caption("Three separate clocks: partner delay, platform processing delay and current shipment event age. P95 uses the nearest rank. Fast processing cannot recover a physical scan a partner has not supplied.")
st.info(st.session_state.last_message)

operations, laboratory, exceptions_tab, downloads, limits = st.tabs(["Shipment operations", "Event laboratory", "Exception work queue", "Data and downloads", "Architecture and limits"])

with operations:
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.subheader("Shipment operations")
        rows = []
        for s in shipments:
            age = (E.parse_time(state["now"]) - E.parse_time(s["last_event_at"])).total_seconds() / 60
            promise = "Delivered" if s["status"] == "DELIVERED" else "Breached" if E.parse_time(state["now"]) > E.parse_time(s["due_at"]) else "Within window"
            rows.append({"Shipment": s["id"], "Route": s["origin"] + " to " + s["destination"],
                         "Status": label(s["status"]), "Event age min": round(age, 1),
                         "Promise IST": local_time(s["due_at"]), "Promise state": promise})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"{len(events)} accepted events in {tenant}. Promise breaches are deterministic due-time rules, not predicted ETA.")
        status_counts = Counter(label(s["status"]) for s in shipments)
        st.markdown("#### Shipments by latest status")
        st.bar_chart(pd.DataFrame({"Status": list(status_counts), "Shipments": list(status_counts.values())}).set_index("Status"), color="#08786b")
    with right:
        st.subheader("Shipment history")
        selected = st.selectbox("Select shipment", [s["id"] for s in shipments], key="selected_shipment_" + tenant)
        s = next(s for s in shipments if s["id"] == selected)
        st.write(f"**{s['origin']} to {s['destination']}**")
        st.caption("Current projection: " + label(s["status"]) + ". Latest effective source event " + local_time(s["last_event_at"]) + ".")
        for e in sorted(s["events"], key=lambda e: E.parse_time(e["occurred_at"]), reverse=True):
            with st.container(border=True):
                st.markdown("**" + label(e["status"]) + (" / " + label(e["reason"]) if e.get("reason") else "") + "**")
                st.write(e["source"] + " at " + local_time(e["occurred_at"]))
                lag = (E.parse_time(e["ingested_at"]) - E.parse_time(e["occurred_at"])).total_seconds()
                platform = (E.parse_time(e["visible_at"]) - E.parse_time(e["ingested_at"])).total_seconds()
                st.caption(f"Partner delay {lag / 60:.1f} min. Platform delay {platform:.0f} sec. {label(e['projection_effect'])}.")

with laboratory:
    st.subheader("Event processing laboratory")
    st.write("The milestone controls target Retail Alpha shipment SHP-1001. Run each step manually, or reset and run the complete scenario.")
    controls = [("1 New milestone", "new"), ("2 Duplicate retry", "duplicate"),
                ("3 Older update", "older"), ("4 Invalid event", "invalid"),
                ("5 Source outage", "outage"), ("6 Recover source", "recover"),
                ("Wrong tenant event", "wrong_tenant")]
    for start in range(0, len(controls), 4):
        cols = st.columns(4)
        for col, (caption, action) in zip(cols, controls[start:start + 4]):
            col.button(caption, key="action_" + action, on_click=do_action, args=(action,), width="stretch")
    st.button("Reset and run full scenario", key="full_scenario", on_click=run_scenario, type="primary")
    st.caption("The full scenario resets the seed, then applies: milestone, duplicate retry, older update, invalid input, outage, buffered update and recovery.")
    if st.session_state.scenario_log:
        with st.expander("Scenario outcome log", expanded=True):
            for number, message in enumerate(st.session_state.scenario_log, 1):
                st.write(f"{number}. {message}")
    source_col, quality_col = st.columns(2, gap="large")
    with source_col:
        st.markdown("### Partner feed health")
        source_rows = [{"Source": name, "Connectivity": "Connected" if h["online"] else "Simulated outage",
                        "Heartbeat age min": round((E.parse_time(state["now"]) - E.parse_time(h["heartbeat"])).total_seconds() / 60)}
                       for name, h in state["source_health"].items()]
        st.dataframe(pd.DataFrame(source_rows), hide_index=True, width="stretch")
        st.metric("Synthetic edge buffer", len(state["buffer"]), help="Buffered events are held at a simulated source boundary while Carrier A is offline.")
        st.caption("During a source outage, press New milestone to buffer an update. Recovery releases the buffer through validation and deduplication. A healthy heartbeat proves connectivity, not shipment scan completeness.")
    with quality_col:
        st.markdown("### Data quality controls")
        st.write(f"**{m['duplicates']}** retry record(s) suppressed. **{m['quarantine']}** record(s) quarantined in this workspace.")
        for index, e in enumerate(state["quarantine"]):
            if e.get("tenant_id") != tenant:
                continue
            with st.container(border=True):
                st.write("**" + e.get("event_id", "Unknown event") + "**")
                st.error(e["validation_error"])
                if e.get("repaired"):
                    st.caption("Repair replay submitted. Original input retained.")
                elif not e.get("shipment_id") and e.get("tenant_id") == "Retail Alpha":
                    st.button("Repair known missing ID and replay", key="repair_" + str(index),
                              on_click=repair_event, args=(index,))
                else:
                    st.caption("Manual review required. Tenant conflicts are not reassigned across customers.")
        if not m["quarantine"]:
            st.caption("No quarantined events. Invalid event demonstrates a missing shipment ID; Wrong tenant event demonstrates a manifest/customer mismatch.")
    st.markdown("#### Accepted events by source")
    source_counts = Counter(e["source"] for e in events)
    st.bar_chart(pd.DataFrame({"Source": list(source_counts), "Accepted events": list(source_counts.values())}).set_index("Source"), color="#244a62")

with exceptions_tab:
    st.subheader("Exception work queue")
    st.write("Each shipment and reason creates one case. A named owner and an action note are required for defensible closure. Existing cases remain available for review after a new scan.")
    for i, case in enumerate(cases):
        with st.expander(f"{case['shipment_id']} — {label(case['reason'])} — {label(case['state'])}", expanded=case["state"] != "RESOLVED"):
            st.caption("Source context: " + case["source"] + ". Current owner: " + case["owner"] + ".")
            owner_key, note_key = "case_owner_" + case["key"], "case_note_" + case["key"]
            owners = ["Unassigned", "Asha Mehta", "Rohan Desai", "Priya Rao"]
            if owner_key not in st.session_state:
                st.session_state[owner_key] = case["owner"]
            if note_key not in st.session_state:
                st.session_state[note_key] = case["comment"]
            with st.form("case_form_" + case["key"]):
                st.selectbox("Named owner", owners, key=owner_key)
                st.text_input("Action taken or resolution evidence", key=note_key)
                first, second = st.columns(2)
                first.form_submit_button("Assign or acknowledge", on_click=update_case,
                                         args=(case["key"], "assign", owner_key, note_key), width="stretch")
                second.form_submit_button("Resolve with note", on_click=update_case,
                                          args=(case["key"], "resolve", owner_key, note_key), width="stretch")
    st.caption("Synthetic names are role-play examples. No emails, SMS, carrier requests or customer messages are sent. Production needs automated condition reconciliation and an approved re-opening policy.")

with downloads:
    st.subheader("Data and audit downloads")
    exported = E.tenant_export(state, tenant)
    a, b, c = st.columns(3)
    a.download_button("Download workspace audit JSON", json.dumps(exported, indent=2),
                      "synthetic_visibility_audit.json", "application/json", width="stretch")
    b.download_button("Download accepted events CSV", csv_bytes(events),
                      "synthetic_accepted_events.csv", "text/csv", width="stretch")
    c.download_button("Download current shipments CSV", csv_bytes([{k: v for k, v in s.items() if k != "events"} for s in shipments]),
                      "synthetic_current_shipments.csv", "text/csv", width="stretch")
    st.markdown("#### Processing and ownership audit")
    audit_rows = list(reversed(exported["audit"]))
    st.dataframe(pd.DataFrame(audit_rows), hide_index=True, width="stretch")
    st.markdown("#### Original seed and expected values")
    st.caption("These downloads contain both synthetic customer workspaces, intentionally disclosed as a public teaching dataset.")
    seed_files = ["synthetic_manifest.csv", "synthetic_events.csv", "synthetic_sources.csv", "synthetic_events.json", "expected_metrics.json", "DATA_DICTIONARY.md"]
    for start in range(0, len(seed_files), 3):
        cols = st.columns(3)
        for col, name in zip(cols, seed_files[start:start + 3]):
            col.download_button(name, (E.DATA_DIR / name).read_bytes(), name,
                                key="seed_download_" + name, width="stretch")

with limits:
    st.subheader("Proposed architecture and demonstration limits")
    st.markdown("""
**Target cloud flow:** partner adapters and API Gateway / Lambda intake, SQS FIFO,
validation and durable idempotency, DynamoDB transactional projection and outbox,
EventBridge subscribers, exception workflow, and S3 archival.

This Streamlit app demonstrates selected event and operating behavior. Its Python
lists and per-session state do not implement durable transactions, real cloud
queues, enterprise identity or actual notifications. Serving the dashboard online
does not establish that the proposed AWS architecture has been deployed.

**Important scope limits**

- Every record and source heartbeat is synthetic. Timestamp differences are chosen inputs, not measured service levels.
- The fixed clock makes results reproducible. The small sample has no statistical relationship to the financial model's annual planning volume.
- Customer selection filters the view. Server-side object authorization, authentication and production isolation are not implemented.
- Each browser session starts its own state. Reset or session expiry discards changes. No shared durable data store is connected.
- The simplified rank assumes a single forward shipment journey. Production needs leg-specific milestones, source authority rules, returns and approved corrections.
- Case closure remains closed until Reset. Production needs ongoing condition checks and a controlled re-opening policy.
- No load, disaster recovery, provider configuration, partner timeliness, security or production cost claim is validated by this demonstration.
""")
    st.markdown("#### Reproducible seed metrics")
    st.json(json.loads((E.DATA_DIR / "expected_metrics.json").read_text(encoding="utf-8")))

st.caption("Group 4 course project demonstration. Synthetic data only. No affiliation with DHL. No live tracking or external messages.")
