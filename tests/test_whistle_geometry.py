"""CAD smoke checks for the experimental fipple cartridge (stdlib unittest)."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import cadquery as cq

from bass_tube.whistle.geometry import build_head
from bass_tube.whistle.params import WhistleHeadParams, WhistleParamsError


class WhistleGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.params = WhistleHeadParams()
        cls.parts = build_head(cls.params)

    def assert_air(self, point: tuple[float, float, float]) -> None:
        probe = cq.Vector(*point)
        self.assertFalse(self.parts.body.val().isInside(probe), point)
        self.assertFalse(self.parts.lid.val().isInside(probe), point)

    def test_two_printable_solids_and_no_overlap(self) -> None:
        for part in (self.parts.body, self.parts.lid):
            self.assertEqual(len(part.solids().vals()), 1)
            self.assertTrue(part.val().isValid())
            self.assertGreater(part.val().Volume(), 0.0)
        overlap = self.parts.body.val().intersect(self.parts.lid.val()).Volume()
        self.assertLess(abs(overlap), 1e-7)
        for part in self.parts.print_parts().values():
            self.assertAlmostEqual(part.val().BoundingBox().zmin, 0.0, places=6)

    def test_socket_fits_tube_and_has_a_real_stop(self) -> None:
        p = self.params
        body = self.parts.body.val()
        self.assertAlmostEqual(p.socket_inner_diameter_mm, 19.63)
        self.assertAlmostEqual(body.BoundingBox().zmin, -8.0, places=6)
        for z in (-7.9, -4.0, -0.1):
            self.assert_air((p.tube_outer_diameter_mm / 2.0 - 0.01, 0.0, z))
        wall_mid = (p.tube_outer_diameter_mm + p.tube_bore_diameter_mm) / 4.0
        self.assertTrue(body.isInside(cq.Vector(wall_mid, 0.0, 0.1)))
        for z in (-7.9, -4.0, -0.1, 0.1, 4.0, 8.0, 10.0, 12.3, 14.5, 15.0):
            self.assert_air((0.0, 0.0, z))

    def test_windway_has_floor_roof_and_open_outlet(self) -> None:
        p = self.params
        for fraction in (0.01, 0.25, 0.5, 0.75, 0.99):
            x = p.wind_inlet_x_mm + fraction * p.windway_length_mm
            self.assert_air((x, 0.0, p.jet_center_z_mm))
            self.assertTrue(self.parts.body.val().isInside(cq.Vector(x, 0.0, p.chamber_height_mm - 0.1)))
            self.assertTrue(self.parts.lid.val().isInside(cq.Vector(x, 0.0, p.chamber_height_mm + p.windway_height_mm + 0.1)))
        self.assert_air((p.window_start_x_mm + 0.1, 0.0, p.jet_center_z_mm))

    def test_labium_is_a_finite_edge_with_air_above_and_below(self) -> None:
        p = self.params
        x = p.window_end_x_mm + 0.05
        z = p.labium_center_z_mm
        self.assertTrue(self.parts.body.val().isInside(cq.Vector(x, 0.0, z)))
        self.assert_air((p.window_end_x_mm - 0.05, 0.0, z))
        self.assert_air((x, 0.0, z - p.edge_thickness_mm / 2.0 - 0.1))
        self.assert_air((x, 0.0, z + p.edge_thickness_mm / 2.0 + 0.1))

    def test_step_roundtrip_and_stl_export(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            for name, part in self.parts.print_parts().items():
                step = root / f"{name}.step"
                stl = root / f"{name}.stl"
                cq.exporters.export(part, str(step))
                cq.exporters.export(part, str(stl), tolerance=0.03, angularTolerance=0.1)
                restored = cq.importers.importStep(str(step))
                self.assertEqual(len(restored.solids().vals()), 1)
                self.assertTrue(restored.val().isValid())
                self.assertGreater(stl.stat().st_size, 100)

    def test_nondefault_dimensions_keep_all_passages_connected(self) -> None:
        variant = WhistleHeadParams(
            windway_width_mm=10.0,
            windway_height_mm=0.8,
            window_length_mm=10.0,
            chamber_height_mm=14.0,
            blade_angle_deg=30.0,
            labium_offset_mm=0.1,
        )
        parts = build_head(variant)
        self.assertTrue(parts.body.val().isValid())
        self.assertAlmostEqual(parts.nominal_head_length_mm, 14.5)


class WhistleParameterTests(unittest.TestCase):
    def test_invalid_geometry_is_rejected_before_cad(self) -> None:
        invalid = (
            {"windway_height_mm": math.nan},
            {"window_length_mm": math.inf},
            {"socket_depth_mm": 0.0},
            {"socket_clearance_mm": -0.1},
            {"tube_bore_diameter_mm": 20.0},
            {"wall_mm": 0.0},
            {"chamber_height_mm": 3.0},
            {"blade_angle_deg": 90.0},
            {"labium_offset_mm": 1.0},
            {"edge_thickness_mm": 1.0},
            {"windway_width_mm": 30.0},
            {"windway_length_mm": 1.0},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(WhistleParamsError):
                WhistleHeadParams(**values)


if __name__ == "__main__":
    unittest.main()
