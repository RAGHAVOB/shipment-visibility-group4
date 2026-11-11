"""Behavioral checks for the synthetic Python event engine, without Streamlit."""
from copy import deepcopy
from datetime import timedelta
import json
import unittest

import engine as E


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.state = E.create_state()

    def test_01_seed_matches_supplied_expected_metrics(self):
        expected = json.loads((E.DATA_DIR / "expected_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(len(self.state["shipments"]), 8)
        self.assertEqual(len(self.state["accepted"]), 17)
        for tenant, values in expected["by_tenant"].items():
            self.assertEqual(E.metrics(self.state, tenant), values)

    def test_02_new_milestone_advances_once(self):
        result = E.receive(self.state, E.sample_event(self.state))
        self.assertEqual(result, {"result": "accepted", "effect": "APPLIED"})
        self.assertEqual(self.state["shipments"][0]["status"], "OUT_FOR_DELIVERY")
        self.assertEqual(len(self.state["outbox"]), 18)

    def test_03_retry_identity_survives_new_transport_id(self):
        event = deepcopy(self.state["accepted"][0])
        event["event_id"] = "NEW-TRANSPORT-ID"
        before = len(self.state["outbox"])
        self.assertEqual(E.ingest(self.state, event)["result"], "duplicate")
        self.assertEqual(len(self.state["outbox"]), before)
        self.assertEqual(len(self.state["accepted"]), 17)

    def test_04_older_event_preserves_history_without_regression(self):
        event = E.sample_event(self.state, status="PICKED_UP", occurred_at=E.iso(E.NOW - timedelta(minutes=100)))
        self.assertEqual(E.receive(self.state, event)["effect"], "HISTORY_ONLY_OLDER_EVENT")
        self.assertEqual(self.state["shipments"][0]["status"], "AT_HUB")
        self.assertEqual(self.state["shipments"][0]["events"][-1]["event_id"], event["event_id"])

    def test_05_newer_backward_milestone_does_not_regress(self):
        result = E.receive(self.state, E.sample_event(self.state, status="MANIFESTED"))
        self.assertEqual(result["effect"], "HISTORY_ONLY_STATUS_REGRESSION")
        self.assertEqual(self.state["shipments"][0]["status"], "AT_HUB")

    def test_06_malformed_record_is_quarantined_without_seen_key(self):
        event = E.sample_event(self.state)
        del event["shipment_id"]
        self.assertEqual(E.receive(self.state, event)["result"], "quarantined")
        self.assertEqual(len(self.state["accepted"]), 17)
        self.assertNotIn((event["tenant_id"], event["source"], event["source_event_id"]), self.state["seen"])

    def test_07_wrong_tenant_cannot_change_shipments(self):
        result = E.receive(self.state, E.sample_event(self.state, tenant_id="Industrial Beta"))
        self.assertEqual(result["result"], "quarantined")
        self.assertIn("tenant mismatch", result["reason"])
        self.assertEqual(self.state["shipments"][0]["status"], "AT_HUB")

    def test_08_unknown_source_and_future_clock_are_rejected(self):
        self.assertEqual(E.ingest(self.state, E.sample_event(self.state, source="Unregistered"))["result"], "quarantined")
        self.assertEqual(E.ingest(self.state, E.sample_event(self.state, occurred_at=E.iso(E.NOW + timedelta(hours=1))))["result"], "quarantined")

    def test_09_invalid_or_timezone_free_timestamp_rejected(self):
        self.assertEqual(E.ingest(self.state, E.sample_event(self.state, occurred_at="invalid"))["result"], "quarantined")
        self.assertEqual(E.ingest(self.state, E.sample_event(self.state, occurred_at="2026-11-11T09:00:00"))["result"], "quarantined")

    def test_10_case_requires_owner_and_resolution_evidence(self):
        case = self.state["exceptions"][0]
        self.assertFalse(E.resolve_exception(self.state, case["key"], "Done"))
        self.assertFalse(E.assign_exception(self.state, case["key"], "Unassigned"))
        self.assertTrue(E.assign_exception(self.state, case["key"], "Asha Mehta", "Investigating"))
        self.assertFalse(E.resolve_exception(self.state, case["key"], "  "))
        self.assertTrue(E.resolve_exception(self.state, case["key"], "Carrier confirmed the missing scan"))
        self.assertEqual(case["state"], "RESOLVED")
        self.assertEqual(case["owner"], "Asha Mehta")

    def test_11_delivered_shipment_leaves_stale_denominator(self):
        E.receive(self.state, E.sample_event(self.state, status="DELIVERED"))
        m = E.metrics(self.state, "Retail Alpha")
        self.assertEqual((m["delivered"], m["stale"]), (2, 2))

    def test_12_outage_buffers_without_operational_update(self):
        E.source_outage(self.state)
        self.assertEqual(E.receive(self.state, E.sample_event(self.state))["result"], "buffered")
        self.assertEqual(len(self.state["buffer"]), 1)
        self.assertEqual(len(self.state["accepted"]), 17)
        self.assertEqual(self.state["shipments"][0]["status"], "AT_HUB")

    def test_13_recovery_flushes_once_and_repeated_recovery_is_safe(self):
        E.source_outage(self.state)
        E.receive(self.state, E.sample_event(self.state))
        self.assertEqual(E.source_recovery(self.state)["released"], 1)
        self.assertEqual(len(self.state["accepted"]), 18)
        self.assertEqual(self.state["buffer"], [])
        self.assertEqual(E.source_recovery(self.state)["released"], 0)
        self.assertEqual(len(self.state["accepted"]), 18)

    def test_14_full_scenario_matches_documented_outcomes(self):
        log = E.full_scenario(self.state)
        self.assertEqual(len(log), 7)
        self.assertEqual((len(self.state["accepted"]), len(self.state["duplicates"]), len(self.state["quarantine"])), (20, 1, 1))
        self.assertEqual(len(self.state["outbox"]), 19)
        self.assertEqual(self.state["buffer"], [])
        self.assertTrue(self.state["source_health"]["Carrier A"]["online"])

    def test_15_repaired_invalid_record_preserves_source_identity(self):
        E.demo_action(self.state, "invalid")
        original = deepcopy(self.state["quarantine"][0])
        self.assertEqual(E.repair_quarantined(self.state, 0)["result"], "accepted")
        self.assertEqual(self.state["accepted"][-1]["source_event_id"], original["source_event_id"])
        self.assertEqual(self.state["quarantine"][0]["event_id"], original["event_id"])
        self.assertTrue(self.state["quarantine"][0]["repaired"])

    def test_16_workspace_export_contains_only_selected_customer_records(self):
        exported = E.tenant_export(self.state, "Industrial Beta")
        self.assertEqual(len(exported["shipments"]), 2)
        self.assertEqual(len(exported["accepted_events"]), 4)
        self.assertTrue(all(e["tenant_id"] == "Industrial Beta" for e in exported["accepted_events"]))
        json.dumps(exported)  # Exports must not leak non-serializable internal sets.

    def test_17_fresh_sessions_have_no_shared_mutable_state(self):
        other = E.create_state()
        E.demo_action(self.state, "new")
        E.source_outage(self.state)
        self.assertEqual(len(other["accepted"]), 17)
        self.assertEqual(other["shipments"][0]["status"], "AT_HUB")
        self.assertTrue(other["source_health"]["Carrier A"]["online"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
