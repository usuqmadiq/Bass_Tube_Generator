"""Независимые физические ориентиры для лабиального пассивного резонатора."""

import math
import unittest
from dataclasses import replace

from bass_tube.params import tube_params
from bass_tube.whistle.acoustics import (
    BoreSection, WhistleAcousticsError, estimate_airflow, estimate_pair,
    first_resonance_hz, ideal_effective_length_mm, sections_for_tube,
    sound_speed_m_s, straight_length_for_frequency_mm,
)


class WhistleAcousticsTests(unittest.TestCase):
    def test_first_modes_are_half_and_quarter_wave_not_dc(self):
        for termination, expected in (("open", 171.5), ("stopped", 85.75)):
            with self.subTest(termination=termination):
                self.assertAlmostEqual(first_resonance_hz([BoreSection(1000, 30)], termination), expected, places=7)
                self.assertAlmostEqual(ideal_effective_length_mm(expected, termination), 1000, places=8)

    def test_sectioning_does_not_change_uniform_cylinder(self):
        pieces = [BoreSection(50, 24) for _ in range(20)]
        for termination in ("open", "stopped"):
            end = 6 if termination == "open" else 0
            whole = first_resonance_hz([BoreSection(1000, 24)], termination, 23, end)
            self.assertAlmostEqual(first_resonance_hz(pieces, termination, 23, end), whole, places=7)

    def test_open_outlet_correction_is_virtual_length(self):
        self.assertAlmostEqual(first_resonance_hz([BoreSection(1000, 20)], "open", 0, 25), 343000 / 2050, places=7)

    def test_inverse_agrees_with_lumped_mouth_boundary(self):
        for termination in ("open", "stopped"):
            for mouth in (0, 10, 60, 400):
                with self.subTest(termination=termination, mouth=mouth):
                    end = 8 if termination == "open" else 0
                    length = straight_length_for_frequency_mm(80, termination, mouth, end)
                    actual = first_resonance_hz([BoreSection(length, 25)], termination, mouth, end)
                    self.assertAlmostEqual(actual, 80, places=7)
                    k = 2 * math.pi * 80 / 343000
                    self.assertAlmostEqual(k * (length + end) + math.atan(k * mouth), math.pi if termination == "open" else math.pi / 2, places=10)

    def test_narrow_neck_finds_low_mode_instead_of_higher_root(self):
        # Закрытая широкая полость + узкое открытое горло: низкая мода Гельмгольца.
        sections = [BoreSection(100, 2), BoreSection(100, 100)]
        fundamental = first_resonance_hz(sections, "stopped")
        lumped_limit = 343000 / (2 * math.pi) * math.sqrt((2 / 100) ** 2 / (100 * 100))
        self.assertLess(fundamental, 15)
        self.assertAlmostEqual(fundamental, lumped_limit, delta=0.01)
        self.assertLess(first_resonance_hz(sections, "stopped", 20), fundamental)

    def test_open_stepped_profile_matches_analytic_characteristic(self):
        # Для двух открытых секций: B=j(cos(kL1)sin(kL2)/S2 + sin(kL1)cos(kL2)/S1).
        sections = [BoreSection(100, 8), BoreSection(900, 32)]
        result = first_resonance_hz(sections)
        k = 2 * math.pi * result / 343000
        scaled_b = math.cos(k * 100) * math.sin(k * 900) + 16 * math.sin(k * 100) * math.cos(k * 900)
        self.assertAlmostEqual(scaled_b, 0, places=8)
        self.assertGreater(result, 343000 / (4 * 1000))
        self.assertLess(result, 343000 / (2 * 1000))

    def test_reversing_open_profile_preserves_its_spectrum(self):
        # Обе границы одинаково открыты: направление прохода матриц не меняет моды.
        sections = [BoreSection(300, 50), BoreSection(80, 3), BoreSection(120, 25)]
        self.assertAlmostEqual(first_resonance_hz(sections),
                               first_resonance_hz(reversed(sections)), places=7)

    def test_tube_profile_uses_physical_geometry_and_no_membrane_corrections(self):
        params = tube_params(body_length_mm=1000, outer_diameter_mm=30,
                             max_height_mm=320, max_width_mm=400, max_depth_mm=40,
                             head_reserve_mm=35, gap_mm=2)
        sections = sections_for_tube(params, 1000)
        self.assertEqual(len(sections), 66)
        self.assertAlmostEqual(sum(s.length_mm for s in sections), 1000)
        self.assertEqual(sections[0].diameter_mm, params.seat_bore_diameter_mm)
        self.assertEqual(sections[-1].diameter_mm, params.bore_diameter_mm)
        shifted = replace(params, delta_head_mm=99, delta_bends_mm=30, delta_out_mm=70)
        self.assertEqual(sections_for_tube(shifted, 1000), sections)
        with self.assertRaises(WhistleAcousticsError):
            sections_for_tube(replace(params, hole_count=1), 1000)
        with self.assertRaises(WhistleAcousticsError):
            sections_for_tube(replace(params, slider_kind="end", slider_semitones=1), 1000)

    def test_flow_units_and_mean_velocity_are_separate(self):
        estimate = estimate_airflow(135, 25, 0.6, velocity_coefficient=1,
                                   frequency_hz=80, cutup_mm=12.5)
        self.assertAlmostEqual(estimate.estimated_center_velocity_m_s, 15)
        self.assertAlmostEqual(estimate.flow_l_min, 13.5)
        self.assertAlmostEqual(estimate.theta, 15)
        self.assertAlmostEqual(estimate.strouhal, 1 / 15)
        nonuniform = estimate_airflow(135, 25, 0.6, velocity_coefficient=1,
                                     mean_to_center_ratio=2 / 3, frequency_hz=80, cutup_mm=12.5)
        self.assertAlmostEqual(nonuniform.flow_l_min, 9)
        self.assertEqual(nonuniform.theta, estimate.theta)
        off = estimate_airflow(0, 25, 0.6, frequency_hz=80, cutup_mm=12.5)
        self.assertEqual(off.flow_l_min, 0)
        self.assertIsNone(off.strouhal)

    def test_pair_beating_and_detuning(self):
        pair = estimate_pair(80, 82, 13.5, 13.5)
        self.assertEqual(pair.beat_hz, 2)
        self.assertAlmostEqual(pair.detuning_cents, 42.7486916769)
        self.assertEqual(pair.total_flow_l_min, 27)
        self.assertEqual(estimate_pair(82, 80).beat_hz, 2)
        self.assertLess(estimate_pair(82, 80).detuning_cents, 0)

    def test_temperature_and_invalid_inputs(self):
        self.assertAlmostEqual(sound_speed_m_s(0), 331.3)
        self.assertAlmostEqual(sound_speed_m_s(20), 343.21, delta=0.01)
        for invalid in (-1, 0, math.nan, math.inf, True):
            with self.subTest(invalid=invalid), self.assertRaises(WhistleAcousticsError):
                BoreSection(invalid, 20)
        calls = [lambda: first_resonance_hz([]),
                 lambda: first_resonance_hz(None),
                 lambda: first_resonance_hz([BoreSection(100, 20)], "closed"),
                 lambda: first_resonance_hz([BoreSection(100, 20)], mouth_correction_mm=-1),
                 lambda: first_resonance_hz([BoreSection(100, 20)], "stopped", end_correction_mm=1),
                 lambda: first_resonance_hz([BoreSection(100, 20)], c=math.nan),
                 lambda: sound_speed_m_s(-273.15), lambda: estimate_pair(0, 82),
                 lambda: estimate_pair(80, 82, math.inf),
                 lambda: estimate_airflow(-1, 25, 0.6),
                 lambda: estimate_airflow(100, 25, 0.6, frequency_hz=80),
                 lambda: estimate_airflow(100, 25, 0.6, velocity_coefficient=1.1)]
        for call in calls:
            with self.assertRaises(WhistleAcousticsError):
                call()


if __name__ == "__main__":
    unittest.main()
