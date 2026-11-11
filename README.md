# Streamlit shipment visibility dashboard

This is a real interactive Streamlit application for the Group 4 academic submission. It uses the same canonical synthetic records as the offline HTML demonstration. It has no live shipment feeds, DHL affiliation, AWS deployment, actual outbound notifications or enterprise authentication.

## Run locally

On Windows you may double-click `START_DASHBOARD.cmd` after extracting this folder. It creates a local environment and runs the commands below. Keep the launcher window open while presenting.

Use Python 3.11 or later. Open a terminal in this folder and run:

```text
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local address printed by Streamlit, normally `http://localhost:8501`. The application does not need secrets, API keys, a cloud subscription or a database. A public deployment must include `app.py`, `engine.py`, `requirements.txt` and the entire `data` directory. The entry point is `app.py`.

The dependency is pinned to Streamlit 1.67.0. Pandas is supplied as a Streamlit dependency. All core event logic uses Python's standard library. No Plotly dependency is needed.

## Publish a shareable Streamlit link

Upload this folder's contents to an authorized GitHub repository, including the complete `data/` folder and `.streamlit/config.toml`. Sign in at `https://share.streamlit.io/`, connect that GitHub account, choose Create app, select the repository and branch, and set the main file path to `app.py`. Choose a supported Python version of 3.11 or later. No secrets are needed. Make the application public if your evaluator should open it without an invitation. Verify the returned `streamlit.app` URL before putting it in the report. See the parent package's `09_Streamlit_Deployment.md` for details.

## Demonstrate the scenario

1. Start with Retail Alpha and explain the three clocks. Partner delay is occurrence to ingestion, platform delay is ingestion to visibility, and active event age is the fixed simulation clock minus the latest effective occurrence time.
2. In Event laboratory click New milestone. SHP-1001 advances to out for delivery. Click Duplicate retry and show that no second state or mock outbox effect occurs.
3. Click Older update. Its pickup record enters shipment history while the current state stays out for delivery.
4. Click Invalid event. The missing ID record enters quarantine. Repair the known missing-ID scenario and replay it. The original is retained and the stable source event identity is preserved. Wrong tenant event demonstrates a manifest/customer mismatch and is not automatically reassigned across customers.
5. Click Source outage, then New milestone. Carrier A turns offline, its synthetic heartbeat becomes 55 minutes old, and one update enters the edge buffer without changing operational state. Click Recover source. The buffered update passes through the same validation and idempotency path and the buffer clears. Recovery does not invent unreported physical scans.
6. Open Exception work queue. Choose a named owner, enter an action note and submit Assign or acknowledge. Add closure evidence and submit Resolve with note. An unassigned case or empty resolution note cannot resolve.
7. Switch customer workspaces. Shipment views, metrics and audit downloads filter to that synthetic customer. This view filter is not authentication or a security boundary.
8. Download current shipments CSV, accepted events CSV or workspace audit JSON. Reset before the next demonstration.

Reset and run full scenario performs the complete seven-step event sequence deterministically. It resets the original seed first and finishes with 20 accepted events, one duplicate retry, one quarantined input, 19 local mock outbox records and an empty source buffer across the complete session.

## Data and reproducibility

The fixed clock is 11 November 2026, 10:00 UTC / 15:30 IST. Initial data has **8 synthetic shipments and 17 events** across two customers. Each Streamlit browser connection receives its own `st.session_state` state object. A reset, expired session or server restart discards changes. No global mutable event store or shared cache is used.

| Seed metric | Retail Alpha | Industrial Beta |
| --- | ---: | ---: |
| Shipments | 6 | 2 |
| Delivered | 1 | 0 |
| Stale active shipments | 3 | 0 |
| Unresolved cases | 5 | 1 |
| Accepted events | 13 | 4 |
| Partner delay P95 | 5 min | 1 min |
| Platform delay P95 | 7 sec | 5 sec |
| Active event age P95 | 70 min | 21 min |

P95 uses the nearest rank. The timestamps are chosen inputs, not measured operating performance. The small dataset has no statistical relationship to the financial workbook's annual planning volume. See `data/DATA_DICTIONARY.md` and `data/expected_metrics.json` for definitions. The data folder includes manifests, events and source registry in CSV and JSON.

## Verify

```text
python -m unittest -v test_engine.py
python -m unittest -v test_app.py
```

The 17 engine checks cover seed compatibility, accepted updates, duplicate/outbox behavior, older history, regression prevention, malformed and wrong-tenant input, unknown source and timestamp validation, ownership and evidence requirements, freshness, outage buffering, recovery, full-scenario outcomes, stable repair identity, tenant-filtered exports and independent state objects. They do not prove production security, service levels or actual AWS behavior.

All 17 engine checks and four official Streamlit AppTest widget checks passed during authoring. The widget tests exercise event controls, buffering and recovery, customer selection, and named exception closure through actual Streamlit callbacks. The application server also returned HTTP 200 for its page and health check. Browser visual inspection of the Streamlit version was unavailable after browser control stopped, so these checks do not assert pixel-level browser layout verification.

## Scope of the proposed architecture

The target design uses partner adapters, API Gateway / Lambda intake, SQS FIFO, schema validation and durable idempotency, DynamoDB transactional projection and outbox, EventBridge subscribers, workflow and S3 archival. The Streamlit app simulates selected behavior using Python data structures. Publishing this dashboard online does not deploy that AWS architecture.

The status ranking simplifies one forward shipment journey. Production needs source authority rules, multi-leg lifecycle handling, returns and approved corrections. Manual closures remain closed until Reset; a deployed operating system must re-evaluate continuing conditions and apply a controlled re-opening policy. Further requirements include server-side authorization, privacy/retention controls, durable storage, reconciliation, production load and recovery tests and actual partner integration rights.
