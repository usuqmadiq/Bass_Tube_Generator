"""Печатные детали слайдера: выдвижной конец или семейство подвижных U-колен.

Выдвижной конец — царга с фланцем, как трубка подстройки: печатается
стоя, фланец на столе. U-семейство — царги на местах гнёзд, дуги 180°
снизу и высокий цоколь как у трубы: выпуклая оболочка столбов от стола
до центров колен. Несколько колен стоят на общем цоколе. Вложенный кусок
царги в длину воздушного пути не считается: воздух идёт внутри вставки.
"""

from __future__ import annotations

import math

import cadquery as cq

from bass_tube.acoustics.slider import SliderPlan, is_u_family, slider_leg_points
from bass_tube.acoustics.trim import TrimPlan
from bass_tube.body.parts import hull_base_solid
from bass_tube.body.tuner import build_tuner_body
from bass_tube.body.tube import BodyError, TubeBody
from bass_tube.constants import SLIDER_END
from bass_tube.layout.centerline import Turn, Vec3

_OVERSHOOT_MM = 0.5


def build_slider_body(
    plan: SliderPlan,
    turn_radius_mm: float,
    columns: tuple[tuple[float, float], ...] = (),
    base_height_mm: float | None = None,
) -> TubeBody:
    """Строит отдельную деталь слайдера по плану хода.

    Принимает план слайдера, радиус колена корпуса, необязательные центры
    прямых укладки и необязательную высоту цоколя (центры нижних колен,
    как у трубы). Для выдвижного конца отдаёт царгу с фланцем, как трубку
    подстройки. Для семейства U — царги на местах гнёзд, дуги снизу и
    высокий цоколь. Возвращает TubeBody. Если булева операция потеряла
    тело, поднимает BodyError.
    """
    if plan.kind == SLIDER_END:
        return build_tuner_body(_end_as_trim(plan))
    if is_u_family(plan.kind):
        height = plan.flange_mm if base_height_mm is None else base_height_mm
        return _build_u_family(plan, turn_radius_mm, columns, height)
    raise BodyError(f"Схема слайдера «{plan.kind}» не печатается.")


def _end_as_trim(plan: SliderPlan) -> TrimPlan:
    """Переводит выдвижной конец в план трубки подстройки.

    Принимает план слайдера схемы end. Геометрия царги та же: фланец,
    перекрытие, ход. Возвращает TrimPlan для build_tuner_body.
    """
    return TrimPlan(
        upper_note=plan.upper_note,
        lower_note=plan.lower_note,
        extra_length_mm=plan.extra_length_mm,
        overlap_mm=plan.overlap_mm,
        flange_mm=plan.flange_mm,
        tenon_diameter_mm=plan.tenon_diameter_mm,
        bore_diameter_mm=plan.bore_diameter_mm,
        flange_diameter_mm=plan.flange_diameter_mm,
        tenon_length_mm=plan.tenon_length_mm,
    )


def _build_u_family(
    plan: SliderPlan,
    turn_radius_mm: float,
    columns: tuple[tuple[float, float], ...],
    base_height_mm: float,
) -> TubeBody:
    """Собирает одно или несколько подвижных U-колен на высоком цоколе.

    Принимает план, радиус колена, центры прямых и высоту цоколя до центров
    дуг — ту же, что у трубы. Дуги лежат в вертикальных плоскостях пар
    царг, царги растут вверх. Цоколь — выпуклая оболочка столбов от стола.
    Канал сквозной и чуть продлён за торцы. Возвращает TubeBody. Если тело
    развалилось, поднимает BodyError.
    """
    radius = turn_radius_mm
    points = slider_leg_points(plan, radius, columns)
    pairs = _u_pairs(points)
    center_z = base_height_mm
    tenon_r = plan.tenon_diameter_mm / 2.0
    bore_r = plan.bore_diameter_mm / 2.0
    outline_r = plan.flange_diameter_mm / 2.0 + 0.05
    try:
        outer = hull_base_solid(points, base_height_mm, outline_r)
        for left, right in pairs:
            bend = _u_bend_pair(left, right, radius, center_z, tenon_r)
            outer = outer.fuse(bend)
            outer = outer.fuse(_tenon_at(left, center_z, tenon_r, plan.tenon_length_mm))
            outer = outer.fuse(_tenon_at(right, center_z, tenon_r, plan.tenon_length_mm))
        bore = _u_family_channel(plan, pairs, radius, center_z, bore_r)
        shape = outer.cut(bore).clean()
    except Exception as exc:
        raise BodyError(f"U-слайдер не построился: {exc}") from exc

    solids = cq.Workplane("XY").add(shape).solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise BodyError("U-слайдер не собрался в одно тело.")

    return TubeBody(
        solid=cq.Workplane("XY").add(shape),
        axis_length_mm=plan.tenon_length_mm * len(points) + math.pi * radius * len(pairs),
        outer_diameter_mm=plan.flange_diameter_mm,
        bore_diameter_mm=plan.bore_diameter_mm,
        seat_outer_diameter_mm=plan.tenon_diameter_mm,
        seat_bore_diameter_mm=plan.bore_diameter_mm,
        base_height_mm=base_height_mm,
    )


def _u_pairs(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    """Режет список царг на пары одного U-колена.

    Принимает центры царг по ходу канала. Возвращает кортеж пар (левая,
    правая). Нечётное число точек отвергает BodyError.
    """
    if len(points) < 2 or len(points) % 2 != 0:
        raise BodyError("U-слайдеру нужны пары царг.")
    return tuple((points[index], points[index + 1]) for index in range(0, len(points), 2))


def _tenon_at(
    point: tuple[float, float],
    center_z: float,
    tenon_r: float,
    length_mm: float,
) -> cq.Solid:
    """Цилиндр царги вверх от конца дуги.

    Принимает центр прямой в плане, высоту центра колена, радиус царги
    и её длину. Возвращает солид.
    """
    base = cq.Vector(point[0], point[1], center_z)
    return cq.Solid.makeCylinder(tenon_r, length_mm, base, cq.Vector(0.0, 0.0, 1.0))


def _u_bend_pair(
    left: tuple[float, float],
    right: tuple[float, float],
    radius_mm: float,
    center_z: float,
    section_radius_mm: float,
) -> cq.Solid:
    """Наружная дуга одного U между двумя царгами.

    Принимает центры пары, радиус оси, высоту центра колена и радиус сечения.
    Возвращает солид протяжки.
    """
    return _sweep_turn(_u_turn_pair(left, right, radius_mm, center_z), section_radius_mm)


def _u_family_channel(
    plan: SliderPlan,
    pairs: tuple[tuple[tuple[float, float], tuple[float, float]], ...],
    radius_mm: float,
    center_z: float,
    bore_radius_mm: float,
) -> cq.Solid:
    """Сквозной канал U-слайдера: царги и дуги, с продлением торцов.

    Принимает план, пары царг, радиус оси, высоту центра колена и радиус
    канала. Возвращает солид для вычитания.
    """
    height = plan.tenon_length_mm + 2.0 * _OVERSHOOT_MM
    up = cq.Vector(0.0, 0.0, 1.0)
    bore: cq.Solid | None = None
    for left, right in pairs:
        for point in (left, right):
            base = cq.Vector(point[0], point[1], center_z - _OVERSHOOT_MM)
            piece = cq.Solid.makeCylinder(bore_radius_mm, height, base, up)
            bore = piece if bore is None else bore.fuse(piece)
        bend = _sweep_turn(_u_turn_pair(left, right, radius_mm, center_z), bore_radius_mm)
        bore = bend if bore is None else bore.fuse(bend)
    if bore is None:
        raise BodyError("У U-слайдера нет канала.")
    return bore


def _u_turn_pair(
    left: tuple[float, float],
    right: tuple[float, float],
    radius_mm: float,
    center_z: float,
) -> Turn:
    """Дуга оси одного U в координатах печатной детали.

    Принимает центры пары, радиус оси и высоту центра колена. Обход снизу
    от первой царги ко второй, как нижнее колено трубы. Возвращает Turn.
    """
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    span = math.hypot(dx, dy)
    if span < 1e-9:
        raise BodyError("Царги U-слайдера совпали: дугу некуда класть.")
    axis_u = Vec3(dx / span, dy / span, 0.0)
    center = Vec3(
        (left[0] + right[0]) / 2.0,
        (left[1] + right[1]) / 2.0,
        center_z,
    )
    length = math.pi * radius_mm
    return Turn(
        length_mm=length,
        s_start_mm=0.0,
        s_end_mm=length,
        center=center,
        radius_mm=radius_mm,
        axis_u=axis_u,
        angle_start=math.pi,
        angle_end=2.0 * math.pi,
    )


def _sweep_turn(turn: Turn, radius_mm: float) -> cq.Solid:
    """Круг, протянутый по дуге 180°.

    Принимает дугу оси и радиус сечения. Возвращает солид.
    """
    start = cq.Vector(turn.point(0.0).x, turn.point(0.0).y, turn.point(0.0).z)
    middle = turn.point(turn.length_mm / 2.0)
    end = turn.point(turn.length_mm)
    path = cq.Wire.assembleEdges(
        [
            cq.Edge.makeThreePointArc(
                start,
                cq.Vector(middle.x, middle.y, middle.z),
                cq.Vector(end.x, end.y, end.z),
            )
        ]
    )
    tangent = turn.tangent(0.0)
    profile = cq.Wire.makeCircle(
        radius_mm,
        start,
        cq.Vector(tangent.x, tangent.y, tangent.z),
    )
    return cq.Solid.sweep(profile, [], path, makeSolid=True, isFrenet=False)
