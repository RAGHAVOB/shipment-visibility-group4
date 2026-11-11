"""Streamlit widget integration checks using the official AppTest harness."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class DashboardAppTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(str(Path(__file__).resolve().parent / "app.py"), default_timeout=30).run()
        self.assertEqual(len(self.app.exception), 0)

    def click(self, key):
        self.app.button(key=key).click().run()
        self.assertEqual(len(self.app.exception), 0)

    def test_seed_metrics_and_current_duplicate_older_invalid_controls(self):
        values = {m.label: m.value for m in self.app.metric}
        self.assertEqual(values["Shipments"], "6")
        self.assertEqual(values["Platform delay P95"], "7 sec")
        self.click("action_new")
        self.assertEqual(self.app.session_state["visibility_state"]["shipments"][0]["status"], "OUT_FOR_DELIVERY")
        self.click("action_duplicate")
        self.assertEqual(len(self.app.session_state["visibility_state"]["duplicates"]), 1)
        self.click("action_older")
        self.assertEqual(self.app.session_state["visibility_state"]["accepted"][-1]["projection_effect"], "HISTORY_ONLY_OLDER_EVENT")
        self.click("action_invalid")
        self.assertEqual(len(self.app.session_state["visibility_state"]["quarantine"]), 1)

    def test_outage_and_recovery_widgets_buffer_and_release(self):
        self.click("action_outage")
        self.click("action_new")
        self.assertEqual(len(self.app.session_state["visibility_state"]["buffer"]), 1)
        self.assertEqual(len(self.app.session_state["visibility_state"]["accepted"]), 17)
        self.click("action_recover")
        self.assertEqual(len(self.app.session_state["visibility_state"]["buffer"]), 0)
        self.assertEqual(len(self.app.session_state["visibility_state"]["accepted"]), 18)

    def test_complete_scenario_and_workspace_widgets(self):
        self.click("full_scenario")
        state = self.app.session_state["visibility_state"]
        self.assertEqual((len(state["accepted"]), len(state["duplicates"]), len(state["quarantine"])), (20, 1, 1))
        self.app.selectbox(key="tenant").set_value("Industrial Beta").run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(next(m.value for m in self.app.metric if m.label == "Shipments"), "2")

    def test_case_form_assignment_and_resolution(self):
        case = self.app.session_state["visibility_state"]["exceptions"][0]
        owner_key, note_key = "case_owner_" + case["key"], "case_note_" + case["key"]
        self.app.selectbox(key=owner_key).set_value("Asha Mehta")
        self.app.text_input(key=note_key).set_value("Carrier contacted")
        next(b for b in self.app.button if b.label == "Assign or acknowledge").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["visibility_state"]["exceptions"][0]["owner"], "Asha Mehta")
        self.app.text_input(key=note_key).set_value("Carrier confirmed verified scan")
        next(b for b in self.app.button if b.label == "Resolve with note").click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state["visibility_state"]["exceptions"][0]["state"], "RESOLVED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
