"""Проверка стыка механики головки и расчёта длины существующей трубы."""

import contextlib
import io
import json
import unittest

from bass_tube import tube_params
from bass_tube.acoustics.tuning import resolve_tuning
from bass_tube.whistle.__main__ import main
from bass_tube.whistle.acoustics import WhistleAcousticsError
from bass_tube.whistle.params import WhistleHeadParams
from bass_tube.whistle.planning import (
    plan_existing_tube, plan_uniform_whistle, uniform_body_length_mm,
)


class WhistlePlanningTests(unittest.TestCase):
    def test_existing_tube_keeps_physical_length_and_counts_socket_once(self):
        params = tube_params(note="C2", max_height_mm=250, max_width_mm=150,
                             max_depth_mm=150, head_reserve_mm=35, gap_mm=1)
        head = WhistleHeadParams()
        length = resolve_tuning(params).body_length_mm
        report = plan_existing_tube(params, head, termination="stopped")
        self.assertAlmostEqual(report["body_length_mm"], length)
        self.assertAlmostEqual(
            sum(section["length_mm"] for section in report["bore_sections"]),
            length + head.nominal_head_length_mm,
        )
        self.assertAlmostEqual(report["passive_frequency_hz"], 343000 / (4 * (length + head.nominal_head_length_mm)), places=7)
        self.assertFalse(report["head_calibrated"])

    def test_target_inverse_accounts_for_the_added_head(self):
        head = WhistleHeadParams(windway_height_mm=0.8, window_length_mm=12)
        for termination in ("open", "stopped"):
            with self.subTest(termination=termination):
                length = uniform_body_length_mm(80, head, termination=termination, mouth_correction_mm=30)
                report = plan_uniform_whistle(length, head, termination=termination, mouth_correction_mm=30)
                self.assertAlmostEqual(report["passive_frequency_hz"], 80, places=7)

    def test_mismatched_seat_is_rejected(self):
        with self.assertRaises(WhistleAcousticsError):
            params = tube_params(note="C2", max_height_mm=250, max_width_mm=150,
                                 max_depth_mm=150, head_reserve_mm=35, gap_mm=1)
            plan_existing_tube(params, WhistleHeadParams(tube_outer_diameter_mm=22))

    def test_cli_two_independent_voices_and_model_status(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["--target-hz", "80", "--second-target-hz", "82", "--termination", "stopped"])
        result = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "experimental_unvoiced")
        self.assertEqual(len(result["voices"]), 2)
        self.assertAlmostEqual(result["pair"]["beat_hz"], 2, places=7)
        self.assertFalse(result["pair"]["common_supply_manifold"])
        self.assertNotIn("exports", result)


if __name__ == "__main__":
    unittest.main()
