"""Rule-state acceptance scenarios; these are synthetic facts, not footage accuracy."""

import importlib.util
import sys
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("tt_referee", Path(__file__).parents[1] / "services/flight/referee.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
Referee, assess_serve = MODULE.Referee, MODULE.assess_serve


def event(i, trigger="incorrect_return", offender="B", **extra):
    return {
        "event_id": f"e{i}",
        "rally_id": f"r{i}",
        "evidence": {
            "trigger": trigger,
            "offender": offender,
            "verified": True,
            "refs": [{"cam_id": "side", "seq": i, "t_source_s": i / 60}],
            **extra,
        },
    }


class RefereeScenarios(unittest.TestCase):
    def test_duplicate_event_and_duplicate_terminal_do_not_score_twice(self):
        r = Referee()
        first = r.submit(event(1))
        self.assertEqual(first, r.submit(event(1)))
        duplicate = event(1)
        duplicate["event_id"] = "other-camera-e1"
        r.submit(duplicate)
        self.assertEqual(r.snapshot()["points"], {"A": 1, "B": 0})
        self.assertEqual(len(r.snapshot()["history"]), 1)

    def test_serve_order_every_two_points_and_let_keeps_server(self):
        r = Referee()
        self.assertEqual(r.snapshot()["server"], "A")
        r.submit(event(1))
        self.assertEqual(r.snapshot()["server"], "A")
        r.submit(event(2, "service_net", otherwise_correct_service=True))
        self.assertEqual(r.snapshot()["server"], "A")
        r.submit(event(3))
        self.assertEqual(r.snapshot()["server"], "B")
        r.submit(event(4))
        r.submit(event(5))
        self.assertEqual(r.snapshot()["server"], "A")

    def test_deuce_and_two_point_margin(self):
        r = Referee(initial_points={"A": 10, "B": 10})
        self.assertEqual(r.snapshot()["server"], "A")
        r.submit(event(1))
        self.assertEqual(r.snapshot()["server"], "B")
        self.assertEqual(r.snapshot()["games"]["A"], 0)
        r.submit(event(2, "incorrect_return", offender="A"))
        self.assertEqual(r.snapshot()["server"], "A")
        r.submit(event(3))
        r.submit(event(4))
        s = r.snapshot()
        self.assertEqual(s["games"], {"A": 1, "B": 0})
        self.assertEqual(s["points"], {"A": 13, "B": 11})
        self.assertEqual(s["server"], "B")
        self.assertEqual(s["status"], "between_games")

    def test_game_match_and_next_game_first_server_alternates(self):
        r = Referee(best_of=3)
        for i in range(11):
            r.submit(event(i))
        self.assertEqual(r.snapshot()["games"]["A"], 1)
        self.assertEqual(r.snapshot()["server"], "B")
        r.submit(event(11))
        self.assertEqual(r.snapshot()["points"], {"A": 1, "B": 0})
        self.assertEqual(r.snapshot()["game_no"], 2)
        for i in range(12, 22):
            r.submit(event(i))
        self.assertEqual(r.snapshot()["match_winner"], "A")
        with self.assertRaises(ValueError):
            r.submit(event(22))

    def test_deciding_game_change_ends_at_five(self):
        r = Referee(best_of=3)
        for i in range(11):
            r.submit(event(i))
        for i in range(11, 22):
            r.submit(event(i, offender="A"))
        for i in range(22, 26):
            r.submit(event(i))
        self.assertFalse(r.snapshot()["ends_swapped"])
        r.submit(event(26))
        self.assertTrue(r.snapshot()["ends_swapped"])

    def test_correction_rebuilds_score_once_with_audit(self):
        r = Referee()
        r.submit(event(1))
        r.submit(event(2))
        c = r.correct("r1", "B", "fix-r1")
        self.assertEqual(c["supersedes"], "e1")
        self.assertEqual(r.snapshot()["points"], {"A": 1, "B": 1})
        r.correct("r1", "B", "fix-r1")
        self.assertEqual(len(r.snapshot()["history"]), 3)
        r.correct("r1", None, "fix-r1-let")
        self.assertEqual(r.snapshot()["points"], {"A": 1, "B": 0})

    def test_correction_can_reopen_match_and_preserves_later_rallies(self):
        r = Referee(best_of=1)
        for i in range(11):
            r.submit(event(i))
        self.assertEqual(r.snapshot()["status"], "match_complete")
        r.correct("r0", "B", "fix")
        self.assertEqual(r.snapshot()["status"], "in_game")
        self.assertEqual(r.snapshot()["games"], {"A": 0, "B": 0})
        self.assertEqual(r.snapshot()["points"], {"A": 10, "B": 1})

    def test_manual_resolution_is_explicit_and_replay_is_idempotent(self):
        r = Referee()
        r.submit({"event_id": "lost", "rally_id": "r1", "type": "ball_dead", "winner": "A"})
        self.assertEqual(r.snapshot()["points"], {"A": 0, "B": 0})
        r.resolve("r1", "B", "manual-1", "Player confirms missed return")
        r.resolve("r1", "B", "manual-1")
        self.assertEqual(r.snapshot()["points"], {"A": 0, "B": 1})
        self.assertEqual(r.snapshot()["history"][-1]["source"], "manual")

    def test_missing_conflicting_or_no_refs_is_review(self):
        for evidence in [
            {},
            {"verified": True, "trigger": "incorrect_return", "offender": "B"},
            {"verified": False, "refs": ["frame"], "trigger": "incorrect_return", "offender": "B"},
            {"verified": True, "refs": ["frame"], "conflicting": True, "trigger": "incorrect_return", "offender": "B"},
        ]:
            r = Referee()
            c = r.submit({"event_id": "e", "rally_id": "r", "evidence": evidence})
            self.assertEqual(c["status"], "review_needed")
            self.assertEqual(r.snapshot()["points"], {"A": 0, "B": 0})

    def test_all_point_triggers(self):
        for trigger, rule in MODULE.POINT_RULES.items():
            with self.subTest(trigger=trigger):
                r = Referee()
                c = r.submit(event(1, trigger))
                self.assertEqual(c["winner"], "A")
                self.assertIn(rule, c["rule_refs"])
                self.assertIsNone(c["probability"])
                self.assertEqual(c["tier"], "BETA")

    def test_net_on_return_is_not_a_let_and_edge_position_does_not_score(self):
        for kind in ["return_net", "edge_position", "side_position", "ball_disappearance"]:
            r = Referee()
            c = r.submit(event(1, kind))
            self.assertEqual(c["status"], "review_needed")

    def test_service_net_prerequisites_and_fault_precedence(self):
        r = Referee()
        self.assertEqual(r.submit(event(1, "service_net"))["status"], "review_needed")
        self.assertEqual(r.submit(event(2, "service_net", otherwise_correct_service=True))["status"], "let")
        self.assertEqual(r.submit(event(3, "incorrect_service"))["status"], "point")
        self.assertEqual(r.submit(event(4, "incorrect_return", let_applies=True))["status"], "let")

    def test_receiver_not_ready_with_attempt_is_not_automatic_let(self):
        r = Referee()
        self.assertEqual(
            r.submit(event(1, "receiver_not_ready", receiver_attempted_return=True))["status"], "review_needed"
        )
        self.assertEqual(r.submit(event(2, "receiver_not_ready", receiver_attempted_return=False))["status"], "let")

    def test_order_correction_retains_earlier_points(self):
        r = Referee()
        r.submit(event(1))
        r.submit(event(2))
        self.assertEqual(r.submit(event(3, "order_correction"))["status"], "let")
        self.assertEqual(r.snapshot()["points"], {"A": 2, "B": 0})
        self.assertEqual(r.snapshot()["server"], "B")

    def test_interruptions_no_automatic_inference(self):
        r = Referee()
        c = r.submit({"event_id": "incomplete", "rally_id": "r1", "type": "recording_ended"})
        self.assertEqual(c["status"], "review_needed")
        self.assertEqual(r.submit(event(2, "official_interruption"))["status"], "let")

    def test_doubles_and_accessibility_unobserved_stay_manual(self):
        r = Referee(mode="doubles")
        self.assertEqual(r.submit(event(1, "incorrect_return"))["status"], "review_needed")
        r.resolve("r1", "A", "manual")
        self.assertEqual(r.snapshot()["points"]["A"], 1)

    def test_invalid_identifiers_and_settings_fail(self):
        for kwargs in [
            {"best_of": 2},
            {"first_server": "X"},
            {"initial_points": {"A": -1, "B": 0}},
            {"initial_points": {"A": 11, "B": 0}},
        ]:
            with self.assertRaises(ValueError):
                Referee(**kwargs)
        with self.assertRaises(ValueError):
            Referee().submit({})
        with self.assertRaises(ValueError):
            Referee().correct("unknown", "A", "fix")

    def test_snapshot_cannot_mutate_state(self):
        r = Referee()
        r.submit(event(1))
        s = r.snapshot()
        s["history"][0]["winner"] = "B"
        s["points"]["A"] = 100
        self.assertEqual(r.snapshot()["history"][0]["winner"], "A")
        self.assertEqual(r.snapshot()["points"]["A"], 1)


class ServeScenarios(unittest.TestCase):
    def assess(self, h, a=(0, 20), **kw):
        opts = dict(calibrated=True, release_observed=True, timing_validated=True, measurement_validated=True)
        opts.update(kw)
        return assess_serve(h, a, **opts)

    def test_height_exact_boundary_is_pass_and_subthreshold_is_fault(self):
        self.assertEqual(self.assess((0.16, 0.16))["height"], "pass")
        self.assertEqual(self.assess((0.11, 0.13))["status"], "toss_fault_supported")
        self.assertEqual(self.assess((0.159, 0.161))["height"], "uncertain")

    def test_angle_boundary_and_uncertainty(self):
        self.assertEqual(self.assess((0.2, 0.22), (30, 30))["angle"], "pass")
        self.assertEqual(self.assess((0.2, 0.22), (30.1, 35))["status"], "toss_fault_supported")
        self.assertEqual(self.assess((0.2, 0.22), (29, 31))["status"], "review_needed")

    def test_missing_measurement_is_not_a_fault(self):
        self.assertEqual(self.assess(None, None)["status"], "review_needed")
        for key in ["calibrated", "release_observed", "timing_validated", "measurement_validated"]:
            self.assertEqual(self.assess((0.11, 0.13), **{key: False})["status"], "unavailable")

    def test_invalid_bounds_and_nan_are_rejected(self):
        for bounds in [(float("nan"), 1), (1, float("inf")), (0.2, 0.1), (-1, 0.2), "unknown"]:
            self.assertEqual(self.assess(bounds)["height"], "unavailable")

    def test_toss_pass_does_not_establish_full_serve_legality(self):
        s = self.assess((0.2, 0.22))
        self.assertEqual(s["status"], "toss_checks_pass")
        self.assertEqual(s["full_service_legality"], "unverified")
        self.assertFalse(s["official_angle_estimator_verified"])

    def test_disability_relaxation_requires_official(self):
        s = self.assess((0.1, 0.11), relaxation=True)
        self.assertEqual(s["status"], "official_input_required")
        self.assertEqual(s["rule_refs"], ["2.6.7"])


if __name__ == "__main__":
    unittest.main()
