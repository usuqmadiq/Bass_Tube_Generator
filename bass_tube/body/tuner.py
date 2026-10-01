"""Выдвижная трубка подстройки: царга в канал открытого конца и фланец-упор.

Печатается отдельно, фланец на столе, царга вверх. Фланец шире канала,
поэтому трубка не проваливается в корпус. Вложенный кусок царги в длину
воздушного пути не считается: воздух идёт внутри трубки.
"""

from __future__ import annotations

import cadquery as cq

from bass_tube.acoustics.trim import TrimPlan
from bass_tube.body.tube import BodyError, TubeBody

_OVERSHOOT_MM = 0.5


def build_tuner_body(plan: TrimPlan) -> TubeBody:
    """Строит полую трубку подстройки по плану хода.

    Принимает TrimPlan. Фланец лежит на z = 0, царга растёт вверх, канал
    сквозной и чуть продлён за торцы, чтобы разрез не шёл по плоскости.
    Возвращает TubeBody. Если булева операция потеряла тело, поднимает BodyError.
    """
    try:
        flange = cq.Solid.makeCylinder(
            plan.flange_diameter_mm / 2.0,
            plan.flange_mm,
            cq.Vector(0.0, 0.0, 0.0),
            cq.Vector(0.0, 0.0, 1.0),
        )
        tenon = cq.Solid.makeCylinder(
            plan.tenon_diameter_mm / 2.0,
            plan.tenon_length_mm,
            cq.Vector(0.0, 0.0, plan.flange_mm),
            cq.Vector(0.0, 0.0, 1.0),
        )
        outer = flange.fuse(tenon)
        height = plan.flange_mm + plan.tenon_length_mm
        bore = cq.Solid.makeCylinder(
            plan.bore_diameter_mm / 2.0,
            height + 2.0 * _OVERSHOOT_MM,
            cq.Vector(0.0, 0.0, -_OVERSHOOT_MM),
            cq.Vector(0.0, 0.0, 1.0),
        )
        shape = outer.cut(bore).clean()
    except Exception as exc:
        raise BodyError(f"Трубка подстройки не построилась: {exc}") from exc

    solids = cq.Workplane("XY").add(shape).solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise BodyError("Трубка подстройки не собралась в одно тело.")

    return TubeBody(
        solid=cq.Workplane("XY").add(shape),
        axis_length_mm=height,
        outer_diameter_mm=plan.flange_diameter_mm,
        bore_diameter_mm=plan.bore_diameter_mm,
        seat_outer_diameter_mm=plan.tenon_diameter_mm,
        seat_bore_diameter_mm=plan.bore_diameter_mm,
        base_height_mm=plan.flange_mm,
    )
