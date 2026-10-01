"""Полое тело трубы вдоль осевой линии и экспорт одной детали.

Канал — половина внутреннего диаметра, стенка одна и та же по всей оси.
У мембраны посадка под модуль, за ней конический переходник к трубе, если
диаметры разные. Внутри воздуха ступеньки нет. Снизу цоколь с плоским дном
для печати, в нём спрятаны нижние развороты. Торцы остаются кольцом стенки,
канал сквозной. При включённых разрезах корпус режется на куски стола
со стыками «папа — мама» без зазора. Игровые отверстия, если они
есть, вырезаются цилиндром сквозь стенку наружу вязанки.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cadquery as cq

from bass_tube.acoustics.slider import SliderPlan, skip_turns_after_straights
from bass_tube.body.parts import (
    base_outline_radius_mm,
    base_parts,
    bore_parts,
    hull_base_solid,
    outer_parts,
)
from bass_tube.layout.centerline import AxisFrame, Centerline, Straight, Turn, Vec3
from bass_tube.layout.coil import Coil
from bass_tube.layout.columns import Point2
from bass_tube.layout.holes import PlacedHole, hole_cutters
from bass_tube.params import TubeParams
from bass_tube.section import bore_radius_at, outer_radius_at


class BodyError(ValueError):
    """Тело трубы не построилось или не экспортировалось. Текст — причина."""


@dataclass(eq=False)
class TubeBody:
    """Одна цельная деталь вдоль оси.

    solid — тело CadQuery. axis_length_mm — длина кривой оси. Диаметры —
    номинал трубы и конца под модуль. base_height_mm — высота цоколя.
    """

    solid: cq.Workplane
    axis_length_mm: float
    outer_diameter_mm: float
    bore_diameter_mm: float
    seat_outer_diameter_mm: float
    seat_bore_diameter_mm: float
    base_height_mm: float


def build_tube_body(
    centerline: Centerline,
    coil: Coil,
    params: TubeParams,
    holes: tuple[PlacedHole, ...] = (),
    slider: SliderPlan | None = None,
) -> TubeBody:
    """Строит полую трубу по оси, укладке и параметрам сечения.

    Принимает осевую линию, укладку (для цоколя), проверенные параметры,
    уже привязанные игровые отверстия и необязательный план слайдера.
    Сливает наружные куски участков, отдельным шагом добавляет цоколь,
    вычитает канал, затем дырки наружу через стенку. При U-колене последние
    нижние колена слайдера не печатаются: туда вставляется отдельная деталь.
    Возвращает TubeBody. Если кривая оси не совпала с длиной, канал вышел
    глухим или деталь развалилась, поднимает BodyError.
    """
    length = _axis_wire(centerline).Length()
    if abs(length - centerline.length_mm) > 1e-6:
        raise BodyError(
            f"Длина кривой оси {_format_mm(length)} мм не совпала с осью "
            f"{_format_mm(centerline.length_mm)} мм."
        )
    skip = skip_turns_after_straights(slider, coil.straight_count)

    try:
        shape = _fuse_checked(
            outer_parts(centerline, params, skip),
            _wall_points(centerline, params, skip),
        )
        base = base_parts(coil, params)
        if base:
            shape = shape.fuse(*base).clean()
        for piece in bore_parts(centerline, params, skip):
            shape = shape.cut(piece)
        shape = shape.clean()
        shape = _cut_finger_holes(shape, centerline, params, holes)
    except BodyError:
        raise
    except Exception as exc:
        raise BodyError(f"Полый канал вдоль оси не построился: {exc}") from exc

    solid = cq.Workplane("XY").add(shape)
    _require_one_open_tube(solid, centerline, params, skip)
    return TubeBody(
        solid=solid,
        axis_length_mm=length,
        outer_diameter_mm=params.outer_diameter_mm,
        bore_diameter_mm=params.bore_diameter_mm,
        seat_outer_diameter_mm=params.seat_outer_diameter_mm,
        seat_bore_diameter_mm=params.seat_bore_diameter_mm,
        base_height_mm=coil.base_height_mm,
    )


@dataclass(frozen=True, slots=True)
class BodyVoice:
    """Один канал в общей детали из нескольких труб.

    centerline — ось канала в координатах детали. params — сечение и стык.
    holes — дырки на этом канале. skip_turns_after — номера прямых перед
    коленами, которые не печатаются (слайдер U).
    """

    centerline: Centerline
    params: TubeParams
    holes: tuple[PlacedHole, ...] = ()
    skip_turns_after: tuple[int, ...] = ()


def build_joined_body(
    voices: tuple[BodyVoice, ...],
    base_points: tuple[Point2, ...],
    base_height_mm: float,
) -> TubeBody:
    """Одна деталь из нескольких независимых каналов на общем цоколе.

    Принимает каналы, центры всех прямых для общего цоколя и его высоту.
    Сливает наружные стенки всех каналов, добавляет цоколь по выпуклой
    оболочке всех прямых — он же перемычка между трубами, — потом
    вырезает каждый канал и его дырки. Каналы внутри не соединяются.
    Возвращает TubeBody с сечением первого канала. Если деталь не
    сложилась в одно тело или канал вышел глухим, поднимает BodyError.
    """
    if not voices:
        raise BodyError("Нет ни одного канала для общей детали.")
    lengths = []
    for voice in voices:
        length = _axis_wire(voice.centerline).Length()
        if abs(length - voice.centerline.length_mm) > 1e-6:
            raise BodyError(
                f"Длина кривой оси {_format_mm(length)} мм не совпала с осью "
                f"{_format_mm(voice.centerline.length_mm)} мм."
            )
        lengths.append(length)
    first = voices[0].params
    try:
        outer: list[cq.Solid] = []
        walls: list[tuple[cq.Vector, cq.Vector]] = []
        for voice in voices:
            outer.extend(outer_parts(voice.centerline, voice.params, voice.skip_turns_after))
            walls.extend(_wall_points(voice.centerline, voice.params, voice.skip_turns_after))
        shape = _fuse_checked(outer, walls)
        if base_height_mm > 0.0 and len(base_points) >= 2:
            shape = shape.fuse(
                hull_base_solid(base_points, base_height_mm, base_outline_radius_mm(first))
            ).clean()
        for voice in voices:
            for piece in bore_parts(voice.centerline, voice.params, voice.skip_turns_after):
                shape = shape.cut(piece)
        shape = shape.clean()
        for voice in voices:
            shape = _cut_finger_holes(shape, voice.centerline, voice.params, voice.holes)
    except BodyError:
        raise
    except Exception as exc:
        raise BodyError(f"Общая деталь каналов не построилась: {exc}") from exc

    solid = cq.Workplane("XY").add(shape)
    for voice in voices:
        _require_one_open_tube(solid, voice.centerline, voice.params, voice.skip_turns_after)
    return TubeBody(
        solid=solid,
        axis_length_mm=sum(lengths),
        outer_diameter_mm=first.outer_diameter_mm,
        bore_diameter_mm=first.bore_diameter_mm,
        seat_outer_diameter_mm=first.seat_outer_diameter_mm,
        seat_bore_diameter_mm=first.seat_bore_diameter_mm,
        base_height_mm=base_height_mm,
    )


def export_tube_body(
    body: TubeBody,
    step_path: str | Path,
    stl_path: str | Path,
    stl_tolerance_mm: float = 0.25,
    stl_angular_tolerance: float = 0.15,
) -> None:
    """Пишет одну деталь в STEP и STL.

    Принимает тело, пути двух файлов и допуски сетки STL в миллиметрах и
    радианах. STEP хранит твёрдое тело, STL — сетку поверхности для печати.
    Создаёт каталоги. Ничего не возвращает. Если запись не удалась,
    поднимает BodyError.
    """
    step = Path(step_path)
    stl = Path(stl_path)
    step.parent.mkdir(parents=True, exist_ok=True)
    stl.parent.mkdir(parents=True, exist_ok=True)
    try:
        cq.exporters.export(body.solid, str(step))
        cq.exporters.export(
            body.solid,
            str(stl),
            tolerance=stl_tolerance_mm,
            angularTolerance=stl_angular_tolerance,
        )
    except Exception as exc:
        raise BodyError(f"Деталь не записалась в STEP или STL: {exc}") from exc


def load_tube_step(step_path: str | Path) -> cq.Workplane:
    """Читает деталь обратно из STEP.

    Принимает путь к файлу. Возвращает Workplane с телом из файла.
    Если файл не читается, поднимает BodyError.
    """
    try:
        return cq.importers.importStep(str(step_path))
    except Exception as exc:
        raise BodyError(f"STEP не прочитался: {exc}") from exc


def _cut_finger_holes(
    shape,
    centerline: Centerline,
    params: TubeParams,
    holes: tuple[PlacedHole, ...],
):
    """Вырезает игровые отверстия сквозь стенку наружу.

    Принимает солид, ось, параметры и привязанные дырки. Каждая дырка —
    цилиндр от канала через стенку по направлению наружу вязанки.
    Возвращает солид. Если вырезание сломалось, поднимает BodyError.
    """
    if not holes:
        return shape
    try:
        for start, direction, radius, length in hole_cutters(centerline, params, holes):
            cutter = cq.Solid.makeCylinder(
                radius,
                length,
                _vector(start),
                cq.Vector(direction.x, direction.y, direction.z),
            )
            shape = shape.cut(cutter)
        return shape.clean()
    except Exception as exc:
        raise BodyError(f"Отверстия не вырезались: {exc}") from exc


def _fuse(solids: list[cq.Solid]) -> cq.Shape:
    """Сливает куски в одно тело.

    Принимает непустой список солидов. Возвращает их объединение
    с убранными лишними швами.
    """
    first, *rest = solids
    if not rest:
        return first
    return first.fuse(*rest).clean()


def _fuse_checked(
    solids: list[cq.Solid],
    walls: list[tuple[cq.Vector, cq.Vector]],
) -> cq.Shape:
    """Сливает наружные куски и проверяет, что ни один участок не пропал.

    Принимает куски и пары точек середины стенки (по паре на участок оси).
    Слияние всех кусков разом быстрое, но на плотной паре вязанок OCC
    изредка молча выбрасывает целые прямые и колена. Тогда куски сливаются
    по одному. Возвращает тело. Если стенки нет и после этого, поднимает
    BodyError.
    """
    shape = _fuse(solids)
    if not _missing_walls(shape, walls):
        return shape
    shape = solids[0]
    for piece in solids[1:]:
        shape = shape.fuse(piece)
    shape = shape.clean()
    missing = _missing_walls(shape, walls)
    if missing:
        raise BodyError(f"Наружная стенка не сложилась: пропало участков оси — {missing}.")
    return shape


def _wall_points(
    centerline: Centerline,
    params: TubeParams,
    skip_turns_after: tuple[int, ...] = (),
) -> list[tuple[cq.Vector, cq.Vector]]:
    """Точки середины стенки на середине каждого участка оси.

    Принимает ось, параметры и номера прямых перед коленами слайдера,
    которые не печатаются (их пропускает). Для каждого участка берёт две
    противоположные горизонтальные точки на середине толщины стенки: дырка
    вырезает стенку только с одной стороны. Возвращает список пар векторов.
    """
    skipped = {2 * index + 1 for index in skip_turns_after}
    points: list[tuple[cq.Vector, cq.Vector]] = []
    for index, primitive in enumerate(centerline.primitives):
        if index in skipped:
            continue
        frame = centerline.sample(primitive.s_start_mm + primitive.length_mm / 2.0)
        radius = (bore_radius_at(params, frame.s_mm) + outer_radius_at(params, frame.s_mm)) / 2.0
        first = offset_point(frame, radius)
        second = offset_point(frame, -radius)
        points.append((_vector(first), _vector(second)))
    return points


def _missing_walls(shape, walls: list[tuple[cq.Vector, cq.Vector]]) -> int:
    """Сколько участков оси остались без стенки.

    Принимает тело и пары точек середины стенки. Участок цел, если хотя
    бы одна точка пары внутри материала. Возвращает число пустых участков.
    """
    return sum(
        1
        for first, second in walls
        if not shape.isInside(first, 1e-4) and not shape.isInside(second, 1e-4)
    )


def _axis_wire(centerline: Centerline) -> cq.Wire:
    """Собирает кривую оси из примитивов.

    Принимает осевую линию. Прямую превращает в отрезок, дугу 180° — в дугу
    по началу, середине и концу. Возвращает одну кривую; по ней мерится длина.
    Если участки не сшились, поднимает BodyError.
    """
    edges: list[cq.Edge] = []
    for primitive in centerline.primitives:
        start = _vector(primitive.point(0.0))
        end = _vector(primitive.point(primitive.length_mm))
        if isinstance(primitive, Straight):
            edges.append(cq.Edge.makeLine(start, end))
        elif isinstance(primitive, Turn):
            mid = _vector(primitive.point(primitive.length_mm / 2.0))
            edges.append(cq.Edge.makeThreePointArc(start, mid, end))
        else:
            raise BodyError("На оси встретился участок, который не прямая и не дуга.")
    try:
        return cq.Wire.assembleEdges(edges)
    except Exception as exc:
        raise BodyError(f"Ось не собралась в одну кривую: {exc}") from exc


def _require_one_open_tube(
    solid: cq.Workplane,
    centerline: Centerline,
    params: TubeParams,
    skip_turns_after: tuple[int, ...] = (),
) -> None:
    """Проверяет, что сборка дала одну полую деталь.

    Принимает тело, ось, параметры и номера прямых перед пропущенными
    коленами слайдера. В посадке, на середине оси (если она не на
    пропущенном колене) и у выхода канал должен быть пустым, середина
    стенки — материалом, тело — одним валидным солидом. Ничего не возвращает.
    Иначе поднимает BodyError.
    """
    solids = solid.solids().vals()
    if len(solids) != 1 or not solids[0].isValid():
        raise BodyError("Сборка не дала одно целое тело.")

    shape = solids[0]
    for station in _wall_stations(centerline, params, skip_turns_after):
        frame = centerline.sample(station)
        if shape.isInside(_vector(frame.point)):
            raise BodyError("Канал получился заглушённым.")

    middle_s = _wall_stations(centerline, params, skip_turns_after)[0]
    middle = centerline.sample(middle_s)
    wall_radius = (
        bore_radius_at(params, middle.s_mm) + outer_radius_at(params, middle.s_mm)
    ) / 2.0
    if not shape.isInside(_vector(offset_point(middle, wall_radius))):
        raise BodyError("Стенка не легла на ось канала.")
    missing = _missing_walls(shape, _wall_points(centerline, params, skip_turns_after))
    if missing:
        raise BodyError(f"Стенка канала пропала на участках оси: {missing}.")


def _wall_stations(
    centerline: Centerline,
    params: TubeParams,
    skip_turns_after: tuple[int, ...],
) -> tuple[float, ...]:
    """Координаты s, где проверяют, что канал пустой и стенка на месте.

    Принимает ось, параметры и номера прямых перед пропущенными коленами.
    Берёт точку на первой прямой после стыка, середину оси (если она не
    на пропущенном колене — тогда середину первой прямой) и середину
    последней прямой. Возвращает кортеж координат.
    """
    first = min(params.joint_length_mm + 5.0, centerline.length_mm / 2.0)
    last_straight = next(
        primitive
        for primitive in reversed(centerline.primitives)
        if isinstance(primitive, Straight)
    )
    last = (last_straight.s_start_mm + last_straight.s_end_mm) / 2.0
    mid = centerline.length_mm / 2.0
    for skip in skip_turns_after:
        turn_index = 2 * skip + 1
        if turn_index < len(centerline.primitives):
            skipped = centerline.primitives[turn_index]
            if skipped.s_start_mm - 1e-9 <= mid <= skipped.s_end_mm + 1e-9:
                mid = first
                break
    return (first, mid, last)


def offset_point(frame: AxisFrame, radius_mm: float) -> Vec3:
    """Точка сечения на заданном расстоянии от оси, в горизонтальную сторону.

    Принимает кадр оси и радиус в миллиметрах. Сдвигает точку кадра
    перпендикулярно касательной: поперёк плоскости дуги, у вертикальной
    прямой — по оси x. Возвращает Vec3.
    """
    tangent = frame.tangent
    side_x, side_y = tangent.y, -tangent.x
    norm = (side_x * side_x + side_y * side_y) ** 0.5
    if norm < 1e-9:
        side_x, side_y, norm = 1.0, 0.0, 1.0
    return Vec3(
        frame.point.x + side_x / norm * radius_mm,
        frame.point.y + side_y / norm * radius_mm,
        frame.point.z,
    )


def _vector(point: Vec3) -> cq.Vector:
    """Вектор CadQuery из точки оси.

    Принимает Vec3. Возвращает Vector.
    """
    return cq.Vector(point.x, point.y, point.z)


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
