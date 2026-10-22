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

    ``channel_depth_mm`` (0 — same as the flue) cuts the windway deeper than
    the flue: a lid then carries an insert that leaves exactly its own flue
    height, so a kit of lids tunes h without reprinting the body.  The
    labium stays aligned to the jet of ``windway_height_mm``.
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
    channel_depth_mm: float = 0.0

    def __post_init__(self) -> None:
        reasons: list[str] = []
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                reasons.append(f"{field.name} must be a finite number")
        if reasons:
            raise WhistleParamsError("; ".join(reasons))

        signed = {"labium_offset_mm"}
        nonnegative = {"socket_clearance_mm", "lid_lateral_clearance_mm", "channel_depth_mm"}
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
        if 0.0 < self.channel_depth_mm < self.windway_height_mm:
            reasons.append("channel_depth_mm must not be shallower than the flue")
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
    def channel_depth_resolved_mm(self) -> float:
        """Depth of the windway cut in the body: the deepest lid flue."""
        return max(self.channel_depth_mm, self.windway_height_mm)

    @property
    def body_top_z_mm(self) -> float:
        return self.chamber_height_mm + self.channel_depth_resolved_mm + self.lid_thickness_mm

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


def voice_frequency_estimate_hz(tube) -> float:
    """Ориентир основного тона голоса до точного строя, Гц.

    Принимает объект с полями TubeParams. У ноты — её частота по A4. У длины
    — идеальный столб: c/(4L) у заглушённого конца, c/(2L) у открытого, где
    L — корпус плюс шейка головки около 12,5 мм. Этого хватает, чтобы
    подобрать окно: оно округляется до 0,5 мм. Возвращает герцы.
    """
    if tube.note:
        from bass_tube.acoustics.notes import midi_number, parse_note_name

        midi = midi_number(parse_note_name(tube.note))
        return tube.a4_hz * 2.0 ** ((midi - 69) / 12.0)
    length = float(tube.body_length_mm or 0.0) + 12.5
    if tube.termination == "stopped":
        return tube.speed_of_sound_m_s * 1000.0 / (4.0 * length)
    return tube.speed_of_sound_m_s * 1000.0 / (2.0 * (length + tube.delta_out_mm))


def cutup_for_pressure_mm(
    frequency_hz: float,
    pressure_pa: float,
    theta: float,
    velocity_coefficient: float = 0.8,
    density_kg_m3: float = 1.2,
) -> float:
    """Окно до кромки W, при котором струя на давлении P даёт число θ на частоте f.

    θ = U/(f·W), U = Cv·√(2P/ρ). Возвращает миллиметры без округления.
    """
    velocity = velocity_coefficient * math.sqrt(2.0 * pressure_pa / density_kg_m3)
    return velocity / (theta * frequency_hz) * 1000.0


def flue_for_tube(tube) -> tuple[float, float]:
    """Щель h и окно W голоса: заданные или подобранные по давлению дутья.

    Принимает объект с полями TubeParams. Пустое окно — W при θ ≈ 11 на
    давлении whistle_blow_pressure_pa и ориентире основного тона, округлённое
    до 0,5 мм в пределах 6…36 мм. Пустая щель — W/12, до 0,1 мм, в пределах
    0,6…2,5 мм: длинная тонкая струя (W/h > 15) теряет силу. Возвращает (h, W).
    """
    from bass_tube.constants import (
        WHISTLE_AUTO_CUTUP_LIMITS_MM,
        WHISTLE_AUTO_FLUE_LIMITS_MM,
        WHISTLE_CUTUP_TO_FLUE,
        WHISTLE_THETA_TARGET,
    )

    cutup = tube.whistle_cutup_mm
    if cutup is None:
        raw = cutup_for_pressure_mm(
            voice_frequency_estimate_hz(tube),
            tube.whistle_blow_pressure_pa,
            WHISTLE_THETA_TARGET,
        )
        low, high = WHISTLE_AUTO_CUTUP_LIMITS_MM
        cutup = min(max(round(raw * 2.0) / 2.0, low), high)
    height = tube.whistle_windway_height_mm
    if height is None:
        low, high = WHISTLE_AUTO_FLUE_LIMITS_MM
        height = min(max(round(cutup / WHISTLE_CUTUP_TO_FLUE, 1), low), high)
    return float(height), float(cutup)


def head_for_tube(tube) -> WhistleHeadParams:
    """Размеры боковой головки для уже проверенного набора параметров трубы.

    Принимает объект с полями TubeParams (утиная типизация сохраняет этот
    модуль чистым от импорта ядра). Гнездо — по концу под модуль с зазором
    гнезда свистка, глубина — посадка. Щель и окно — из flue_for_tube.
    Канал корпуса режется на самую глубокую щель набора крышек, лабиум
    стоит на струе расчётной щели. Возвращает WhistleHeadParams; его
    проверка поднимает WhistleParamsError.
    """
    height, cutup = flue_for_tube(tube)
    kit = tuple(tube.whistle_lid_kit_mm)
    return WhistleHeadParams(
        tube_outer_diameter_mm=tube.seat_outer_diameter_mm,
        tube_bore_diameter_mm=tube.seat_bore_diameter_mm,
        socket_clearance_mm=tube.whistle_socket_clearance_mm,
        socket_depth_mm=tube.seat_length_mm,
        windway_width_mm=tube.whistle_windway_width_mm,
        windway_height_mm=height,
        windway_length_mm=tube.whistle_windway_length_mm,
        window_length_mm=cutup,
        labium_offset_mm=tube.whistle_labium_offset_mm,
        edge_thickness_mm=tube.whistle_edge_thickness_mm,
        channel_depth_mm=max((height, *kit)),
    )
