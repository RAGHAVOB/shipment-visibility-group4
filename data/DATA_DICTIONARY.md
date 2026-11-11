# Synthetic demonstration data dictionary

All records were created for this academic scenario. No interview, shipment extract, DHL internal telemetry, vendor quotation or performance measurement underlies these records. ISO 8601 timestamp strings use UTC. The interface formats times in Asia/Kolkata. The simulation clock is fixed at 2026-11-11T10:00:00Z.

## Shipment manifest

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Synthetic shipment identifier, for example SHP-1001 |
| `tenant` | string | Synthetic customer workspace label; corresponds to event `tenant_id` |
| `origin` | string | Illustrative Indian origin city |
| `destination` | string | Illustrative Indian destination city |
| `due_at` | UTC timestamp | Planned delivery promise, used for deterministic breach checks |
| `source` | string | Principal partner feed used for stale-case ownership context |

Manifest `id` and event `shipment_id` intentionally refer to the same canonical shipment. Production would require a governed cross-reference mapping from carrier tracking numbers, supplier orders, warehouse IDs and customer references.

## Canonical shipment event

| Field | Type and requirement | Meaning |
| --- | --- | --- |
| `schema_version` | string, required | `1.0` for this demonstration |
| `event_id` | string, required | Local transport / record ID; a retried source event can have a new record ID |
| `source_event_id` | string, required | Stable partner event identity used for deduplication |
| `shipment_id` | string, required | Canonical shipment identifier matching the manifest |
| `tenant_id` | string, required | Customer workspace label matching the manifest owner |
| `source` | enumeration, required | Carrier A, Warehouse W1, Supplier S1 or Customer POD |
| `event_type` | enumeration, required | `MILESTONE` or `EXCEPTION` |
| `status` | enumeration, required | MANIFESTED, PICKED_UP, IN_TRANSIT, AT_HUB, OUT_FOR_DELIVERY or DELIVERED |
| `occurred_at` | UTC timestamp, required | When the physical/business event reportedly happened |
| `ingested_at` | UTC timestamp, required | When the event reached the illustrative ingestion boundary |
| `visible_at` | UTC timestamp, required | When the event became query-visible in the illustrative projection |
| `location` | string, optional | Illustrative city or hub label |
| `sequence` | integer, optional | Demonstration sequence metadata; not used as a global ordering guarantee |
| `reason` | string, required for exception | Demonstration reason such as MISSED_CONNECTION |

The UTC timestamps and delay differences are chosen inputs, not clocks measured by this program. A real implementation must preserve source event time separately from server receipt and projection timestamps, synchronize clocks, and validate event semantics.

## Processing policy

The engine validates required fields, schema version, shipment and tenant match, registered source, event type, status and timestamps. It rejects a visible time preceding ingestion and a source event more than five minutes ahead of ingestion. The skew tolerance is illustrative. Small negative source delay caused by tolerated skew is clamped to zero in the summary metric; the seed records have no negative delay.

Deduplication key is `tenant_id + source + source_event_id`. Only a valid accepted event enters the seen-key set. A quarantined record can therefore be repaired and replayed with the same source identity. A repaired input receives a new local event ID while the invalid original remains in quarantine.

Each accepted event enters history. An older occurrence time or a backwards status rank cannot regress the operational projection. An effective event updates the latest status, location and effective occurrence time and adds one local mock outbox record. The forward rank simplifies a single journey and does not authorize a production policy for returns, corrections or multiple transport legs.

## Derived exception and quality records

| Field | Meaning |
| --- | --- |
| `projection_effect` | APPLIED, HISTORY_ONLY_OLDER_EVENT or HISTORY_ONLY_STATUS_REGRESSION |
| `validation_error` | Quarantine reason; invalid events do not update operational state |
| exception `key` | Tenant + shipment + reason, preventing duplicate cases for the same reason |
| exception `state` | OPEN, ACKNOWLEDGED or RESOLVED |
| exception `owner` | Synthetic person selected by the demonstrator, initially Unassigned |
| exception `comment` | Local action note required for resolution |
| outbox `delivery` | LOCAL_MOCK, explicitly not an external notification |

Stale shipment cases arise if the latest effective event is older than 30 minutes for an undelivered shipment. Promise breaches arise if `due_at` has passed without a delivered milestone. Feed heartbeat is independent of those shipment rules. Existing cases remain visible even after a fresh event so an operator can review and close them. Production would need condition reconciliation and controlled re-opening.

## Source registry

The registry supplies `source_id`, `source_name`, `synthetic`, `role`, `interface`, `heartbeat_at`, `initial_state` and `production_contract`. The interfaces are proposed examples rather than existing DHL integration claims. All source heartbeats start two minutes before the simulation clock. The outage action moves Carrier A heartbeat to 55 minutes before the clock, marks it offline and buffers new carrier events locally. Recovery resets its heartbeat, marks it online and submits the buffer through the same validation and deduplication path.

## Expected metrics

`expected_metrics.json` is generated by the same engine from the original seed. `sourceLagP95` and `platformLagP95` are seconds; `freshnessP95` is minutes. Remaining fields are counts. The UI converts source delay to minutes. P95 is the nearest-rank observation at `ceil(0.95*N)` in an ascending sort. All summary metrics are tenant-filtered. Delivered shipments remain in shipment and accepted-event counts and leave active-freshness and stale counts. Open cases include acknowledged cases and exclude resolved cases.
