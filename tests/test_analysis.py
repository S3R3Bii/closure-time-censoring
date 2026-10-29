import sys
import unittest
from pathlib import Path
from fractions import Fraction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analysis import curve, restricted_mean, metrics, observations


class SurvivalBoundaries(unittest.TestCase):
    def test_day_zero_closures(self):
        obs = [(1, 0, 3, 0, True), (1, 2, 3, 2, True)]
        self.assertEqual(restricted_mean(curve(obs), 3), 1)

    def test_event_precedes_same_day_censor(self):
        obs = [(1, 1, 1, 1, True), (1, None, 1, 1, False)]
        self.assertEqual(curve(obs)[1][1:], (2, 1, 1, Fraction(1, 2)))

    def test_known_curve_and_fair_target(self):
        obs = [(2, 1, 5, 1, True), (1, 4, 5, 4, True), (1, None, 5, 5, False)]
        m = metrics(obs, curve(obs), 3)
        self.assertEqual(m["rmst"], 2)
        self.assertEqual(m["benchmark"], 2)
        self.assertEqual(m["completed_capped"], Fraction(5, 3))
        self.assertEqual(m["completed_uncapped"], 2)

    def test_unsupported_positive_tail(self):
        obs = [(5, None, 1, 1, False)]
        self.assertIsNone(restricted_mean(curve(obs), 3))
        self.assertEqual(restricted_mean(curve(obs), 2), 2)
        self.assertIsNone(metrics(obs, curve(obs), 3)["completed_capped"])

    def test_zero_tail_remains_estimable(self):
        self.assertEqual(restricted_mean(curve([(5, 1, 1, 1, True)]), 28), 1)

    def test_status_endpoint_and_last_day_cutoff(self):
        cells = [
            {
                "count": "2",
                "created_day": "28",
                "closure_delay_cell": "3",
                "status_category": "other",
            }
        ]
        self.assertEqual(observations(cells, 35, "date_only"), [(2, 3, 8, 3, True)])
        self.assertEqual(
            observations(cells, 35, "closed_status_and_date"), [(2, None, 8, 8, False)]
        )

    def test_later_benchmark_inside_observation_bounds(self):
        obs = [(1, 2, 4, 2, True), (2, 20, 5, 5, False), (3, None, 8, 8, False)]
        m = metrics(obs, curve(obs), 14)
        self.assertLessEqual(m["lower_bound"], m["benchmark"])
        self.assertLessEqual(m["benchmark"], m["upper_bound"])


if __name__ == "__main__":
    unittest.main()
