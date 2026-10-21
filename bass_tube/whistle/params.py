"""Dimensions of an experimental, removable fipple head.

All dimensions are millimetres.  The tube's upper end is the local z = 0
datum: the existing tube enters the socket below that plane, and the new
resonator cavity is above it.  None of these dimensions establishes that a
printed head will self-oscillate or be in tune; voicing needs measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from numbers import Real


class WhistleParamsError(ValueError):
    """A head would have an invalid dimension or an obstructed passage."""


@dataclass(frozen=True, slots=True)
class WhistleHeadParams:
    """Manufacturing dimensions, deliberately separate from TubeParams.

    ``chamber_height_mm`` locates the windway floor above the tube datum.
    The jet travels in +x, the window opens in +z, and the resonator leaves
    in -z.  The female socket includes an annular stop at z = 0.  Its eight
    millimetres of overlap belong to the existing tube and must not be
    counted again as added acoustic length.

    The removable lid sits on flat side rails.  Clamp or seal that joint
    during experiments; the CAD does not model a snap fit or a gasket.
    """

    tube_outer_diameter_mm: float = 19.5
    tube_bore_diameter_mm: float = 15.5
    socket_clearance_mm: float = 0.13
    socket_depth_mm: float = 8.0
    wall_mm: float = 2.0
    windway_width_mm: float = 8.0
    windway_height_mm: float = 0.6
    windway_length_mm: float = 12.0
    window_length_mm: float = 8.0
    labium_offset_mm: float = 0.0
    edge_thickness_mm: float = 0.3
    blade_angle_deg: float = 25.0
    chamber_height_mm: float = 12.0
    lid_thickness_mm: float = 2.0
    lid_lateral_clearance_mm: float = 0.15

    def __post_init__(self) -> None:
        reasons: list[str] = []
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                reasons.append(f"{field.name} must be a finite number")
        if reasons:
            raise WhistleParamsError("; ".join(reasons))

        signed = {"labium_offset_mm"}
        nonnegative = {"socket_clearance_mm", "lid_lateral_clearance_mm"}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in signed:
                continue
            if field.name in nonnegative:
                if value < 0.0:
                    reasons.append(f"{field.name} must be nonnegative")
            elif value <= 0.0:
                reasons.append(f"{field.name} must be positive")
        if reasons:
            raise WhistleParamsError("; ".join(reasons))

        if self.tube_bore_diameter_mm >= self.tube_outer_diameter_mm:
            reasons.append("the tube bore must be smaller than its outer diameter")
        if not 0.0 < self.blade_angle_deg < 90.0:
            reasons.append("blade_angle_deg must be between 0 and 90 degrees")
        if self.chamber_height_mm <= 3.0 * self.wall_mm:
            reasons.append("chamber_height_mm must exceed three wall thicknesses")
        if self.edge_thickness_mm > self.windway_height_mm:
            reasons.append("edge_thickness_mm must not exceed the windway height")
        if abs(self.labium_offset_mm) >= (
            self.windway_height_mm + self.edge_thickness_mm
        ) / 2.0:
            reasons.append("the labium edge must intersect the nominal jet height")
        if self.lid_lateral_clearance_mm >= self.wall_mm / 2.0:
            reasons.append("lid clearance must leave at least half of each sealing rail")
        if self.windway_width_mm + 2.0 * self.wall_mm >= self.socket_outer_diameter_mm:
            reasons.append("the windway and its side walls must fit across the socket body")
        if self.wind_inlet_x_mm > -self.socket_outer_diameter_mm / 2.0:
            reasons.append("the windway must extend beyond the round body to expose its inlet")
        edge_top = self.labium_center_z_mm + self.edge_thickness_mm / 2.0
        edge_bottom = self.labium_center_z_mm - self.edge_thickness_mm / 2.0
        if edge_top >= self.body_top_z_mm:
            reasons.append("the labium bevel must rise to a thicker backing")
        if edge_bottom <= self.chamber_height_mm - self.wall_mm:
            reasons.append("the labium underside must clear the chamber roof level")
        if reasons:
            raise WhistleParamsError("; ".join(reasons))

    @property
    def socket_inner_diameter_mm(self) -> float:
        return self.tube_outer_diameter_mm + self.socket_clearance_mm

    @property
    def socket_outer_diameter_mm(self) -> float:
        return self.socket_inner_diameter_mm + 2.0 * self.wall_mm

    @property
    def window_start_x_mm(self) -> float:
        return -self.window_length_mm / 2.0

    @property
    def window_end_x_mm(self) -> float:
        return self.window_length_mm / 2.0

    @property
    def wind_inlet_x_mm(self) -> float:
        return self.window_start_x_mm - self.windway_length_mm

    @property
    def jet_center_z_mm(self) -> float:
        return self.chamber_height_mm + self.windway_height_mm / 2.0

    @property
    def labium_center_z_mm(self) -> float:
        return self.jet_center_z_mm + self.labium_offset_mm

    @property
    def body_top_z_mm(self) -> float:
        return self.chamber_height_mm + self.windway_height_mm + self.lid_thickness_mm

    @property
    def blade_run_mm(self) -> float:
        """Horizontal run of the upper bevel, measured from the finite edge."""
        edge_top = self.labium_center_z_mm + self.edge_thickness_mm / 2.0
        return (self.body_top_z_mm - edge_top) / math.tan(math.radians(self.blade_angle_deg))

    @property
    def labium_back_x_mm(self) -> float:
        return self.window_end_x_mm + self.blade_run_mm

    @property
    def nominal_head_length_mm(self) -> float:
        """Geometric height to the labium; not a calibrated acoustic correction."""
        return self.labium_center_z_mm
