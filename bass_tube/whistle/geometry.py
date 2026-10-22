"""Printable experimental fipple head with a removable windway lid.

This is geometric prototyping, not a claim of successful acoustic voicing.
The head has one resonator, one exposed window and one separate wind inlet.
Two copies therefore still need two feeds or an external wind splitter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq

from bass_tube.whistle.params import WhistleHeadParams

Point3 = tuple[float, float, float]
_OVERSHOOT_MM = 0.5


class WhistleGeometryError(ValueError):
    """The proposed head is invalid, disconnected, or blocks an intended port."""


@dataclass(frozen=True)
class HeadParts:
    """Two solids in assembly coordinates and their geometric reference points.

    The body bottom is at ``-socket_depth_mm``; its annular tube stop is at
    z = 0.  The lid's underside sets the windway ceiling.  ``print_parts``
    moves each part independently onto z = 0 without changing orientation.
    ``nominal_head_length_mm`` is a geometric height, not a measured end
    correction and not the length of the breath supply channel.
    """

    body: cq.Workplane
    lid: cq.Workplane
    params: WhistleHeadParams
    tube_port: Point3
    wind_inlet: Point3
    window_center: Point3
    labium_edge_center: Point3
    nominal_head_length_mm: float

    def assembled_shape(self) -> cq.Compound:
        """Keep the lid removable instead of fusing the mating surfaces."""
        return cq.Compound.makeCompound([self.body.val(), self.lid.val()])

    def print_parts(self) -> dict[str, cq.Workplane]:
        """Separate, socket-down body and flat lid, each based at z = 0."""
        return {
            "body": self.body.translate((0.0, 0.0, self.params.socket_depth_mm)),
            "lid": self.lid.translate((0.0, 0.0, -self.lid.val().BoundingBox().zmin)),
        }


def build_head(params: WhistleHeadParams | None = None) -> HeadParts:
    """Build a socket, chamber, upward window, finite labium and windway lid.

    The horizontal windway exits at the upstream side of the window.  Its
    jet meets a 0.3 mm thick edge by default.  An upper bevel rises away
    from that edge; the hollow under the blade joins the tube below.
    The windway is exposed for cleaning/finishing when the lid is removed.
    Use a temporary clamp or sealed mating face when testing the assembly.
    """
    p = params if params is not None else WhistleHeadParams()
    if not isinstance(p, WhistleHeadParams):
        raise TypeError("params must be WhistleHeadParams")

    radius = p.socket_outer_diameter_mm / 2.0
    half_width = p.windway_width_mm / 2.0
    half_outer_width = half_width + p.wall_mm
    x_in = p.wind_inlet_x_mm
    x_mouth = p.window_start_x_mm
    x_edge = p.window_end_x_mm
    x_back = p.labium_back_x_mm
    z_floor = p.chamber_height_mm
    z_roof = z_floor + p.channel_depth_resolved_mm
    z_top = p.body_top_z_mm
    z_edge_low = p.labium_center_z_mm - p.edge_thickness_mm / 2.0
    z_edge_high = p.labium_center_z_mm + p.edge_thickness_mm / 2.0
    z_chamber = z_floor - p.wall_mm
    z_pocket = z_floor - 2.0 * p.wall_mm
    z_full_cheek = z_floor - 3.0 * p.wall_mm
    eps = _OVERSHOOT_MM

    # Round socket/neck.  Sloping cheeks support the longer windway and
    # blade backing.  Their lower footprint is contained in the cylinder.
    round_body = cq.Solid.makeCylinder(
        radius,
        p.socket_depth_mm + z_top,
        cq.Vector(0.0, 0.0, -p.socket_depth_mm),
    )
    anchor = math.sqrt(radius * radius - half_outer_width * half_outer_width) * 0.95
    cheek = _prism_xz(
        [
            (-anchor, 0.0),
            (anchor, 0.0),
            (max(anchor, x_back + p.wall_mm), z_full_cheek),
            (max(anchor, x_back + p.wall_mm), z_top),
            (min(-anchor, x_in), z_top),
            (min(-anchor, x_in), z_full_cheek),
        ],
        2.0 * half_outer_width,
    )
    shape = round_body.fuse(cheek).clean()

    # Socket ends exactly at the tube datum.  The smaller neck bore makes
    # an annular stop there; the eight millimetres of overlap add no neck.
    socket = cq.Solid.makeCylinder(
        p.socket_inner_diameter_mm / 2.0,
        p.socket_depth_mm + eps,
        cq.Vector(0.0, 0.0, -p.socket_depth_mm - eps),
    )
    neck = cq.Solid.makeCylinder(
        p.tube_bore_diameter_mm / 2.0,
        z_chamber + eps,
        cq.Vector(0.0, 0.0, -eps),
    )
    # The small rectangular pocket beneath the edge overlaps the neck.
    # Its flat ceiling forms the blade underside, leaving a finite edge.
    under_blade = _box(x_mouth, x_back, -half_width, half_width, z_pocket, z_edge_low)
    window = _box(x_mouth, x_edge, -half_width, half_width, z_pocket, z_top + eps)
    windway = _box(x_in - eps, x_mouth + eps, -half_width, half_width, z_floor, z_top + eps)
    lid_pocket = _box(
        x_in - eps,
        x_mouth,
        -half_outer_width - p.lid_lateral_clearance_mm,
        half_outer_width + p.lid_lateral_clearance_mm,
        z_roof,
        z_top + eps,
    )
    bevel = _prism_xz(
        [
            (x_edge, z_edge_high),
            (x_back, z_top),
            (x_back, z_top + eps),
            (x_edge, z_top + eps),
        ],
        p.windway_width_mm,
    )
    for cutter in (socket, neck, under_blade, window, windway, lid_pocket, bevel):
        shape = shape.cut(cutter)
    shape = shape.clean()

    body = cq.Workplane("XY").add(shape)
    lid = build_lid(p, p.windway_height_mm)
    result = HeadParts(
        body=body,
        lid=lid,
        params=p,
        tube_port=(0.0, 0.0, 0.0),
        wind_inlet=(x_in, 0.0, p.jet_center_z_mm),
        window_center=(0.0, 0.0, p.jet_center_z_mm),
        labium_edge_center=(x_edge, 0.0, p.labium_center_z_mm),
        nominal_head_length_mm=p.nominal_head_length_mm,
    )
    _validate_parts(result)
    return result


def build_lid(params: WhistleHeadParams, flue_mm: float) -> cq.Workplane:
    """Крышка, которая оставляет в канале корпуса щель flue_mm.

    Принимает размеры головы и щель. Пластина ложится на рельсы на глубине
    канала; если канал глубже щели, снизу у неё вставка шириной канала минус
    зазор на сторону — её нижняя грань и есть потолок щели. Координаты
    сборочные, как у корпуса. Возвращает одну деталь. Если щель не больше
    нуля или глубже канала, поднимает WhistleGeometryError.
    """
    from bass_tube.constants import WHISTLE_LID_INSERT_CLEARANCE_MM

    p = params
    depth = p.channel_depth_resolved_mm
    if not 0.0 < flue_mm <= depth + 1e-9:
        raise WhistleGeometryError(
            f"Щель крышки {flue_mm:g} мм вне канала корпуса глубиной {depth:g} мм."
        )
    half_width = p.windway_width_mm / 2.0
    half_outer_width = half_width + p.wall_mm
    z_floor = p.chamber_height_mm
    z_roof = z_floor + depth
    x_in, x_mouth = p.wind_inlet_x_mm, p.window_start_x_mm
    shape = _box(x_in, x_mouth, -half_outer_width, half_outer_width, z_roof, p.body_top_z_mm)
    if depth - flue_mm > 1e-6:
        insert_half = half_width - WHISTLE_LID_INSERT_CLEARANCE_MM
        insert = _box(x_in, x_mouth, -insert_half, insert_half, z_floor + flue_mm, z_roof + 0.01)
        shape = shape.fuse(insert).clean()
    return cq.Workplane("XY").add(shape)


def lid_kit(params: WhistleHeadParams, flues_mm) -> dict[float, cq.Workplane]:
    """Набор сменных крышек в печатном виде: потолок щели на столе.

    Принимает размеры головы и щели набора. Каждая крышка стоит на столе
    гранью, которая образует потолок щели: это самая гладкая поверхность
    FDM. Щели глубже канала пропускаются. Возвращает {щель: деталь}.
    """
    kit: dict[float, cq.Workplane] = {}
    for flue in sorted(set(float(item) for item in flues_mm)):
        if flue > params.channel_depth_resolved_mm + 1e-9:
            continue
        lid = build_lid(params, flue)
        kit[flue] = lid.translate((0.0, 0.0, -lid.val().BoundingBox().zmin))
    return kit


def _validate_parts(parts: HeadParts) -> None:
    """Check topology and meaningful passages, rather than only bounding boxes."""
    for name, part in (("body", parts.body), ("lid", parts.lid)):
        solids = part.solids().vals()
        if len(solids) != 1 or not solids[0].isValid() or solids[0].Volume() <= 0.0:
            raise WhistleGeometryError(f"{name} is not one valid solid")

    p = parts.params
    body = parts.body.val()
    lid = parts.lid.val()
    # Probe the assembled windway, the vertical acoustic passage, and the
    # free window immediately before the labium.  Neither printed piece
    # may block these centre lines.
    air_points: list[Point3] = []
    for fraction in (0.02, 0.25, 0.5, 0.75, 0.98):
        air_points.append(
            (p.wind_inlet_x_mm + p.windway_length_mm * fraction, 0.0, p.jet_center_z_mm)
        )
        air_points.append(
            (0.0, 0.0, -p.socket_depth_mm + fraction * (p.body_top_z_mm + p.socket_depth_mm))
        )
    air_points.append((p.window_end_x_mm - 0.1, 0.0, p.labium_center_z_mm))
    for point in air_points:
        vector = cq.Vector(*point)
        if body.isInside(vector) or lid.isInside(vector):
            raise WhistleGeometryError(f"an intended air passage is blocked at {point}")

    material_points = (
        (p.socket_inner_diameter_mm / 2.0 + p.wall_mm / 2.0, 0.0, -p.socket_depth_mm / 2.0),
        ((p.tube_bore_diameter_mm + p.tube_outer_diameter_mm) / 4.0, 0.0, 0.1),
        (p.window_end_x_mm + min(0.05, p.blade_run_mm / 4.0), 0.0, p.labium_center_z_mm),
        # The chamber under a longer bevel must retain a real floor even
        # when that pocket extends beyond the round neck.
        (p.labium_back_x_mm - min(0.1, p.blade_run_mm / 4.0), 0.0, p.chamber_height_mm - 2.5 * p.wall_mm),
    )
    for point in material_points:
        if not body.isInside(cq.Vector(*point)):
            raise WhistleGeometryError(f"a socket wall, stop or labium is missing at {point}")


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _prism_xz(points: list[tuple[float, float]], width_mm: float) -> cq.Solid:
    return cq.Workplane("XZ").polyline(points).close().extrude(width_mm / 2.0, both=True).val()
